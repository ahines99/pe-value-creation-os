"""Model client for judgment steps (PVC-072, PVC-074).

`AnthropicJsonClient` calls Claude through the official SDK with a JSON-schema output format, a cached static
system prompt, and server-side refusal fallbacks. Outages (connection errors, rate limits, 5xx) and refusals
become `ModelUnavailable`, which the workflow turns into a pause rather than a guess. `ScriptedLLMClient` is
the test double.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..egress import check_url
from ..observability import get_logger, metrics, span

log = get_logger(__name__)

DEFAULT_MODEL = "claude-opus-5"
# USD per million tokens (input, output) for cost estimates; cache reads billed at ~0.1x input.
PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0)}


class ModelUnavailable(RuntimeError):
    """The model could not produce a usable answer (outage, rate limit, refusal, or malformed output)."""


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICES.get(self.model, (5.0, 25.0))
        return round((self.input_tokens * pin + self.cache_read_input_tokens * pin * 0.1
                      + self.output_tokens * pout) / 1_000_000, 6)


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any], *, purpose: str,
                      max_tokens: int = 16000) -> tuple[dict[str, Any], Usage]: ...


def _record(usage: Usage, purpose: str) -> None:
    metrics().model_tokens.add(usage.input_tokens, {"model": usage.model, "direction": "input", "purpose": purpose})
    metrics().model_tokens.add(usage.output_tokens, {"model": usage.model, "direction": "output", "purpose": purpose})
    metrics().model_cost.add(usage.cost_usd, {"model": usage.model, "purpose": purpose})
    log.info("model_call", model=usage.model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
             cost_usd=usage.cost_usd, event_type=purpose)


class AnthropicJsonClient:
    def __init__(self, model: str | None = None, client: Any = None, *, use_fallbacks: bool = True):
        self.model = model or os.environ.get("PVC_MODEL", DEFAULT_MODEL)
        self.use_fallbacks = use_fallbacks
        if client is None:
            import anthropic

            check_url("https://api.anthropic.com")
            client = anthropic.Anthropic(max_retries=2, timeout=120.0)
        self.client = client

    def complete_json(self, system: str, user: str, schema: dict[str, Any], *, purpose: str,
                      max_tokens: int = 16000) -> tuple[dict[str, Any], Usage]:
        import anthropic

        kwargs: dict[str, Any] = dict(
            model=self.model, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "high"},
        )
        with span(f"model:{purpose}", model=self.model):
            try:
                if self.use_fallbacks:
                    resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                            fallbacks="default", **kwargs)
                else:
                    resp = self.client.messages.create(**kwargs)
            except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
                raise ModelUnavailable(f"{type(e).__name__}") from e
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    raise ModelUnavailable(f"HTTP {e.status_code}") from e
                raise
        u = resp.usage
        usage = Usage(model=getattr(resp, "model", self.model), input_tokens=u.input_tokens,
                      output_tokens=u.output_tokens, cache_read_input_tokens=u.cache_read_input_tokens or 0)
        _record(usage, purpose)
        if resp.stop_reason == "refusal":
            raise ModelUnavailable("refusal")
        if resp.stop_reason == "max_tokens":
            raise ModelUnavailable("output truncated at max_tokens")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError as e:
            raise ModelUnavailable("malformed JSON output") from e


@dataclass
class ScriptedLLMClient:
    """Test double: returns queued responses (dicts) or raises queued exceptions, recording every prompt."""

    responses: list[Any] = field(default_factory=list)
    model: str = "scripted"
    prompts: list[dict[str, Any]] = field(default_factory=list)

    def complete_json(self, system: str, user: str, schema: dict[str, Any], *, purpose: str,
                      max_tokens: int = 16000) -> tuple[dict[str, Any], Usage]:
        self.prompts.append({"system": system, "user": user, "schema": schema, "purpose": purpose})
        if not self.responses:
            raise ModelUnavailable("no scripted response")
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        if callable(nxt):
            nxt = nxt(system, user)
        usage = Usage(model=self.model, input_tokens=len(system + user) // 4, output_tokens=len(json.dumps(nxt)) // 4)
        _record(usage, purpose)
        return nxt, usage
