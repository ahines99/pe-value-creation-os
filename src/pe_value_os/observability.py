"""Logging, tracing and metrics (PVC-100, PVC-101, PVC-102).

Logs are structured JSON. Every field passes through an allow-list: fields not on it are replaced by a short
SHA-256 hash, so financial values, customer names and document text cannot reach logs even by accident
(PVC-095). Traces follow run -> step -> tool -> model spans. Metrics use OpenTelemetry instruments; when no
exporter is configured they are recorded in-process (tests read them with an in-memory reader).
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from typing import Any

SAFE_KEYS = frozenset(
    {
        "event",
        "level",
        "timestamp",
        "logger",
        "logger_name",
        "run_id",
        "company_id",
        "step",
        "tool_name",
        "status",
        "duration_ms",
        "event_type",
        "evidence_ids",
        "count",
        "error_type",
        "attempt",
        "worker_id",
        "policy_version",
        "calc_version",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "approval_id",
        "plan_id",
        "opportunity_id",
        "kpi_id",
        "schema_version",
        "http_method",
        "path",
        "status_code",
        "decision",
        "branch",
        "reason_code",
        "lever",
        "analysis",
        "sufficient",
        "actor_type",
        "retries",
        "timeout_s",
        "service",
        "environment",
        "trace_id",
        "span_id",
        "notification_id",
        "channel",
        "rows",
        "gaps",
        "result",
        "principal_type",
        "version",
    }
)


def _hash(value: Any) -> str:
    return "h:" + hashlib.sha256(repr(value).encode()).hexdigest()[:12]


def redact(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Pass allow-listed fields through; hash everything else."""
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if k in SAFE_KEYS:
            out[k] = v if isinstance(v, str | int | float | bool | type(None) | list | tuple) else str(v)
        else:
            out[k] = _hash(v)
    return out


def _redact_processor(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> Mapping[str, Any]:
    return redact(event_dict)


_configured = False


def configure_logging(level: str | None = None, stream: Any = None) -> None:
    global _configured
    import structlog

    lvl = getattr(logging, (level or os.environ.get("PVC_LOG_LEVEL", "INFO")).upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(lvl),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stderr),
        cache_logger_on_first_use=False,
    )
    _configured = True


def get_logger(name: str = "pe_value_os") -> Any:
    try:
        import structlog
    except ImportError:  # pragma: no cover - observability extra not installed
        return _StdlibLogger(logging.getLogger(name))
    if not _configured:
        configure_logging()
    # Initial values keep the proxy lazy, so later configure_logging() calls (tests, CLI) take effect.
    return structlog.get_logger(logger_name=name)


class _StdlibLogger:  # pragma: no cover - fallback only
    def __init__(self, logger: logging.Logger):
        self._l = logger

    def _log(self, level: int, event: str, **kw: Any) -> None:
        self._l.log(level, "%s %s", event, redact(kw))

    def info(self, event: str, **kw: Any) -> None:
        self._log(logging.INFO, event, **kw)

    def warning(self, event: str, **kw: Any) -> None:
        self._log(logging.WARNING, event, **kw)

    def error(self, event: str, **kw: Any) -> None:
        self._log(logging.ERROR, event, **kw)

    def debug(self, event: str, **kw: Any) -> None:
        self._log(logging.DEBUG, event, **kw)


# --- tracing -----------------------------------------------------------------------------------------------
def _tracer() -> Any:
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover
        return None
    return trace.get_tracer("pe_value_os")


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    tracer = _tracer()
    if tracer is None:  # pragma: no cover
        yield None
        return
    safe = {k: (v if isinstance(v, str | int | float | bool) else str(v)) for k, v in redact(attrs).items()}
    with tracer.start_as_current_span(name, attributes=safe) as s:
        yield s


def configure_tracing(exporter: Any = None, service_name: str = "pe-value-os") -> Any:
    """Install a tracer provider. With no exporter, uses OTLP/HTTP when OTEL_EXPORTER_OTLP_ENDPOINT is set."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


# --- metrics -----------------------------------------------------------------------------------------------
class Metrics:
    """OpenTelemetry instruments for run, step, tool, model and approval metrics (PVC-102)."""

    def __init__(self, meter: Any = None):
        if meter is None:
            from opentelemetry import metrics

            meter = metrics.get_meter("pe_value_os")
        self.runs = meter.create_counter("pvc.runs", description="Run outcomes by status")
        self.step_duration = meter.create_histogram("pvc.step.duration", unit="ms", description="Step latency")
        self.tool_calls = meter.create_counter("pvc.tool.calls", description="MCP tool calls by outcome")
        self.model_tokens = meter.create_counter("pvc.model.tokens", description="Model tokens by direction")
        self.model_cost = meter.create_counter("pvc.model.cost_usd", description="Estimated model cost in USD")
        self.http_requests = meter.create_counter("pvc.http.requests", description="HTTP requests by status class")
        self.http_duration = meter.create_histogram("pvc.http.duration", unit="ms", description="HTTP latency")
        self.approval_turnaround = meter.create_histogram(
            "pvc.approval.turnaround", unit="h", description="Hours from approval request to decision"
        )
        self.approval_decisions = meter.create_counter(
            "pvc.approval.decisions", description="Approval decisions; changed=true when the human edited the plan"
        )
        self.adapter_errors = meter.create_counter("pvc.adapter.errors", description="Source adapter failures")
        self.kpi_off_track = meter.create_counter("pvc.kpi.off_track", description="KPI off-track alerts")
        self.runs_stuck = meter.create_gauge(
            "pvc.runs.stuck", description="Runs in 'running' state longer than the stuck threshold"
        )
        self.source_age = meter.create_gauge(
            "pvc.source.age_days", description="Days between a dataset's as_of and the reference date"
        )
        self.approvals_pending_oldest = meter.create_gauge(
            "pvc.approvals.pending_oldest", unit="h", description="Age of the oldest pending approval"
        )


_metrics: Metrics | None = None


def metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


def configure_metrics(reader: Any = None, service_name: str = "pe-value-os") -> Any:
    """Install a meter provider (tests pass an InMemoryMetricReader) and rebuild instruments."""
    global _metrics
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource

    readers = [reader] if reader is not None else []
    if reader is None and os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
    provider = MeterProvider(resource=Resource.create({"service.name": service_name}), metric_readers=readers)
    otel_metrics.set_meter_provider(provider)
    _metrics = Metrics(provider.get_meter("pe_value_os"))
    return provider


class RequestMetricsMiddleware:
    """ASGI middleware: request count by status class and latency, for the availability SLO (PVC-140)."""

    def __init__(self, app: Any, service: str):
        self.app, self.service = app, service

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        status = {"code": 500}
        t0 = time.perf_counter()

        async def send_wrapper(message: Any) -> None:
            if message.get("type") == "http.response.start":
                status["code"] = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            attrs = {"service": self.service, "status_class": f"{status['code'] // 100}xx"}
            metrics().http_requests.add(1, attrs)
            metrics().http_duration.record((time.perf_counter() - t0) * 1000, attrs)


@contextmanager
def timed() -> Iterator[dict[str, float]]:
    box = {"ms": 0.0}
    t0 = time.perf_counter()
    try:
        yield box
    finally:
        box["ms"] = round((time.perf_counter() - t0) * 1000, 2)
