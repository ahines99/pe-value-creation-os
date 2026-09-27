"""Model client for judgment steps (PVC-072, PVC-074).

`AnthropicJsonClient` calls Claude through the official SDK with a JSON-schema output format, a cached static
system prompt, and server-side refusal fallbacks. Outages (connection errors, rate limits, 5xx) and refusals
become `ModelUnavailable`, which the workflow turns into a pause rather than a guess. `ScriptedLLMClient` is
the test double.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from ..egress import check_url
from ..observability import get_logger, metrics, span

log = get_logger(__name__)
_usage_context: ContextVar[tuple[Any, Any, str] | None] = ContextVar("model_usage_context", default=None)


@contextmanager
def usage_scope(repo: Any, state: Any, actor: str) -> Iterator[None]:
    """Attach every call attempt to append-only run audit, including rejected output."""
    token = _usage_context.set((repo, state, actor))
    try:
        yield
    finally:
        _usage_context.reset(token)


def _audit_usage(usage: Usage | None, purpose: str, error: str | None = None) -> None:
    from ..domain.models import AuditEvent

    context = _usage_context.get()
    if context is None:
        return
    repo, state, actor = context
    repo.append_audit(
        AuditEvent(
            run_id=state.run_id,
            company_id=state.company_id,
            actor=actor,
            step=f"model:{purpose}",
            event_type="model_usage",
            created_at=datetime.now(UTC),
            payload={
                "call_id": str(uuid.uuid4()),
                "purpose": purpose,
                "usage_complete": usage is not None,
                "error": error,
                "model": usage.model if usage else None,
                "input_tokens": usage.input_tokens if usage else 0,
                "output_tokens": usage.output_tokens if usage else 0,
                "cache_read_input_tokens": usage.cache_read_input_tokens if usage else 0,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens if usage else 0,
                "cache_creation_1h_input_tokens": usage.cache_creation_1h_input_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
                "cost_usd": usage.cost_usd if usage else 0,
                "pricing_known": usage.pricing_known if usage else False,
                "cost_basis": "token estimate; not a billing reconciliation",
            },
        )
    )


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
    cache_creation_input_tokens: int = 0
    cache_creation_1h_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens

    @property
    def pricing_known(self) -> bool:
        return self.model in PRICES or self.model.startswith("scripted")

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICES.get(self.model, (5.0, 25.0))
        return round(
            (
                self.input_tokens * pin
                + self.cache_read_input_tokens * pin * 0.1
                + self.output_tokens * pout
                + (self.cache_creation_input_tokens - self.cache_creation_1h_input_tokens) * pin * 1.25
                + self.cache_creation_1h_input_tokens * pin * 2
            )
            / 1_000_000,
            6,
        )


class LLMClient(Protocol):
    model: str

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, purpose: str, max_tokens: int = 16000
    ) -> tuple[dict[str, Any], Usage]: ...


def _record(usage: Usage, purpose: str) -> None:
    _audit_usage(usage, purpose)
    metrics().model_tokens.add(usage.input_tokens, {"model": usage.model, "direction": "input", "purpose": purpose})
    metrics().model_tokens.add(usage.output_tokens, {"model": usage.model, "direction": "output", "purpose": purpose})
    for direction in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        metrics().model_tokens.add(
            getattr(usage, direction), {"model": usage.model, "direction": direction, "purpose": purpose}
        )
    metrics().model_cost.add(usage.cost_usd, {"model": usage.model, "purpose": purpose})
    log.info(
        "model_call",
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cost_usd=usage.cost_usd,
        event_type=purpose,
    )


class AnthropicJsonClient:
    def __init__(self, model: str | None = None, client: Any = None, *, use_fallbacks: bool = True):
        self.model = model or os.environ.get("PVC_MODEL", DEFAULT_MODEL)
        self.use_fallbacks = use_fallbacks
        self.usage_ledger: list[dict[str, Any]] = []
        if client is None:
            import anthropic

            check_url("https://api.anthropic.com")
            # Hidden SDK retries cannot expose attempt-level usage. Workflow retries
            # are observable and every received response is accounted before parsing.
            client = anthropic.Anthropic(max_retries=0, timeout=120.0)
        self.client = client

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, purpose: str, max_tokens: int = 16000
    ) -> tuple[dict[str, Any], Usage]:
        import anthropic

        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "high"},
        )
        with span(f"model:{purpose}", model=self.model):
            try:
                if self.use_fallbacks:
                    resp = self.client.beta.messages.create(
                        betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                    )
                else:
                    resp = self.client.messages.create(**kwargs)
            except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
                _audit_usage(None, purpose, type(e).__name__)
                self.usage_ledger.append({"purpose": purpose, "usage": None, "error": type(e).__name__})
                raise ModelUnavailable(f"{type(e).__name__}") from e
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    _audit_usage(None, purpose, f"HTTP {e.status_code}")
                    self.usage_ledger.append({"purpose": purpose, "usage": None, "error": f"HTTP {e.status_code}"})
                    raise ModelUnavailable(f"HTTP {e.status_code}") from e
                raise
        u = resp.usage
        usage = Usage(
            model=getattr(resp, "model", self.model),
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_input_tokens=u.cache_read_input_tokens or 0,
            cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            cache_creation_1h_input_tokens=getattr(getattr(u, "cache_creation", None), "ephemeral_1h_input_tokens", 0)
            or 0,
        )
        self.usage_ledger.append({"purpose": purpose, "usage": usage, "stop_reason": resp.stop_reason})
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
    usage_ledger: list[dict[str, Any]] = field(default_factory=list)

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, purpose: str, max_tokens: int = 16000
    ) -> tuple[dict[str, Any], Usage]:
        self.prompts.append({"system": system, "user": user, "schema": schema, "purpose": purpose})
        if not self.responses:
            _audit_usage(None, purpose, "no scripted response")
            self.usage_ledger.append({"purpose": purpose, "usage": None, "error": "no scripted response"})
            raise ModelUnavailable("no scripted response")
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            _audit_usage(None, purpose, type(nxt).__name__)
            self.usage_ledger.append({"purpose": purpose, "usage": None, "error": type(nxt).__name__})
            raise nxt
        if callable(nxt):
            nxt = nxt(system, user)
        usage = Usage(model=self.model, input_tokens=len(system + user) // 4, output_tokens=len(json.dumps(nxt)) // 4)
        _record(usage, purpose)
        self.usage_ledger.append({"purpose": purpose, "usage": usage, "stop_reason": "end_turn"})
        return nxt, usage
