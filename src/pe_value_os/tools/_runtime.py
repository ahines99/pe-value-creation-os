"""Shared runtime for MCP tools (PVC-050).

- `get_ctx()` returns the application RunContext (tests inject one with `set_ctx`).
- `governed(...)` wraps a tool: maps domain errors to `ToolError`, records metrics and a trace span, and writes
  an audit event for mutating tools. It also records the tool's parameter names for strict argument checking.
- `StrictArguments` middleware rejects `tools/call` requests carrying arguments a tool does not declare, so a
  caller cannot smuggle server-owned fields (for example `baseline_value`) that would otherwise be ignored.
"""

from __future__ import annotations

import functools
import inspect
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from .. import security
from ..adapters.repositories import Conflict, NotFound
from ..domain.baselines import MetricUnavailable
from ..domain.dataset import CompanyData
from ..domain.models import AuditEvent
from ..domain.policies import PolicyViolation
from ..observability import get_logger, metrics, span
from ..workflows.steps import RunContext

log = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., Any])

TOOL_PARAMS: dict[str, frozenset[str]] = {}
_ctx: RunContext | None = None
_lock = threading.Lock()
_cache: dict[str, tuple[float, CompanyData]] = {}
CACHE_TTL_S = 60.0


def set_ctx(ctx: RunContext | None) -> None:
    global _ctx
    _ctx = ctx
    _cache.clear()


def get_ctx() -> RunContext:
    global _ctx
    with _lock:
        if _ctx is None:
            from ..app import build_context

            _ctx = build_context(actor="mcp")
        return _ctx


def company_data(company_id: str) -> CompanyData:
    """Scope-checked, briefly cached company data."""
    security.require(company_id)
    now = time.monotonic()
    hit = _cache.get(company_id)
    if hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    ctx = get_ctx()
    # Evidence is registered only for onboarded companies; reads for others still work but cannot be cited.
    data = ctx.adapter.load(company_id, sink=ctx.repo if _onboarded(company_id) else None)
    _cache[company_id] = (now, data)
    return data


def _onboarded(company_id: str) -> bool:
    try:
        get_ctx().repo.get_company(company_id)
        return True
    except NotFound:
        return False


def actor() -> str:
    p = security.current_principal()
    return p.subject if p else "anonymous"


def audit(company_id: str, tool: str, event_type: str, run_id: str | None = None, **payload: Any) -> None:
    get_ctx().repo.append_audit(AuditEvent(run_id=run_id, company_id=company_id, step=f"tool:{tool}", actor=actor(),
                                           event_type=event_type, created_at=datetime.now(UTC), payload=payload))


def governed(name: str, *, mutating: bool = False) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        TOOL_PARAMS[name] = frozenset(inspect.signature(fn).parameters)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            outcome = "ok"
            t0 = time.perf_counter()
            try:
                with span(f"tool:{name}", tool_name=name):
                    return fn(*args, **kwargs)
            except security.ScopeError as e:
                outcome = "denied"
                raise ToolError(f"Access denied: {e}") from e
            except NotFound as e:
                outcome = "not_found"
                raise ToolError(f"Not found: {e}") from e
            except (MetricUnavailable, PolicyViolation, Conflict, ValueError, ValidationError) as e:
                outcome = "rejected"
                raise ToolError(f"{type(e).__name__}: {e}") from e
            finally:
                metrics().tool_calls.add(1, {"tool": name, "outcome": outcome, "mutating": mutating})
                log.info("tool_call", tool_name=name, status=outcome,
                         duration_ms=round((time.perf_counter() - t0) * 1000, 2))

        return wrapper  # type: ignore[return-value]

    return deco


class StrictArguments:
    """Context middleware: reject undeclared tool arguments with INVALID_PARAMS."""

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        if getattr(ctx, "method", None) == "tools/call":
            params = ctx.params or {}
            if not isinstance(params, dict):
                params = getattr(params, "model_dump", lambda: {})()
            tool = params.get("name")
            args = params.get("arguments") or {}
            allowed = TOOL_PARAMS.get(tool or "")
            if allowed is not None:
                extra = sorted(set(args) - allowed)
                if extra:
                    raise MCPError(-32602, f"Tool {tool!r} does not accept arguments {extra}; server-owned "
                                           "fields such as baseline values are derived from company data")
        return await call_next(ctx)
