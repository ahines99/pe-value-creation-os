"""Build ops/observability/grafana/pvc-overview.json (PVC-103).

Form choices: headline numbers are stat tiles; trends are single-axis time series (never dual-axis; tokens and
cost are separate panels). Series colors follow a fixed categorical order keyed to the entity (a status never
changes color when a filter removes others). Threshold colors use the reserved status palette only.

    python scripts/build_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[1] / "ops" / "observability" / "grafana" / "pvc-overview.json"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
DS = {"type": "prometheus", "uid": "${datasource}"}
STEPS = [
    "intake",
    "data_sufficiency",
    "diagnostics",
    "value_modeling",
    "evidence_review",
    "prioritization",
    "roadmap_100_day",
    "human_approval",
]
_id = 0


def pid() -> int:
    global _id
    _id += 1
    return _id


def color_overrides(names: list[str], field: str) -> list[dict[str, Any]]:
    return [
        {
            "matcher": {"id": "byName", "options": n},
            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}],
        }
        for n, c in zip(names, CAT, strict=False)
    ]


def stat(title: str, expr: str, unit: str, x: int, steps: list[tuple[float | None, str]], desc: str) -> dict[str, Any]:
    return {
        "id": pid(),
        "type": "stat",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": {"h": 4, "w": 6, "x": x, "y": 0},
        "targets": [{"refId": "A", "expr": expr, "datasource": DS}],
        "options": {
            "colorMode": "background",
            "graphMode": "none",
            "textMode": "value_and_name",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "decimals": 2,
                "thresholds": {"mode": "absolute", "steps": [{"value": v, "color": c} for v, c in steps]},
            },
            "overrides": [],
        },
    }


def series(
    title: str,
    targets: list[tuple[str, str]],
    unit: str,
    pos: tuple[int, int, int, int],
    desc: str,
    stack: bool = False,
    colors: list[str] | None = None,
    fixed: dict[str, str] | None = None,
) -> dict[str, Any]:
    x, y, w, h = pos
    overrides = color_overrides(colors or [], "") if colors else []
    for name, c in (fixed or {}).items():
        overrides.append(
            {
                "matcher": {"id": "byName", "options": name},
                "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}],
            }
        )
    return {
        "id": pid(),
        "type": "timeseries",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [
            {"refId": chr(65 + i), "expr": e, "legendFormat": leg, "datasource": DS}
            for i, (e, leg) in enumerate(targets)
        ],
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "lineWidth": 2,
                    "fillOpacity": 0,
                    "pointSize": 8,
                    "showPoints": "never",
                    "axisPlacement": "left",
                    "stacking": {"mode": "normal" if stack else "none"},
                    "drawStyle": "bars" if stack else "line",
                    "gradientMode": "none",
                },
                "color": {"mode": "palette-classic"},
            },
            "overrides": overrides,
        },
    }


def build() -> dict[str, Any]:
    panels = [
        stat(
            "API availability (30d)",
            '1 - sum(increase(pvc_http_requests_total{status_class="5xx"}[30d])) / sum(increase(pvc_http_requests_total[30d]))',
            "percentunit",
            0,
            [(None, CRITICAL), (0.99, WARNING), (0.995, GOOD)],
            "Share of MCP and approval-API requests without a 5xx. SLO 99.5% (docs/slo.md).",
        ),
        stat(
            "Stuck runs",
            "max(pvc_runs_stuck)",
            "none",
            6,
            [(None, GOOD), (1, CRITICAL)],
            "Runs in 'running' for more than 30 minutes. Runbook: docs/runbooks/stuck-run.md",
        ),
        stat(
            "Oldest pending approval",
            "max(pvc_approvals_pending_oldest_hours)",
            "h",
            12,
            [(None, GOOD), (72, WARNING), (120, CRITICAL)],
            "Escalation fires at the policy expiry (120 h).",
        ),
        stat(
            "Human override rate (30d)",
            'sum(increase(pvc_approval_decisions_total{changed="true"}[30d])) / sum(increase(pvc_approval_decisions_total[30d]))',
            "percentunit",
            18,
            [(None, GOOD), (0.3, WARNING), (0.5, SERIOUS)],
            "Share of approval decisions where the approver edited the plan. Rising values mean recommendations need review.",
        ),
        series(
            "Run outcomes per hour",
            [
                (f'sum(increase(pvc_runs_total{{status="{s}"}}[1h]))', s)
                for s in ("complete", "awaiting_approval", "needs_evidence", "rejected", "failed")
            ],
            "short",
            (0, 4, 12, 8),
            "Runs reaching each state. 'failed' uses the critical status color.",
            stack=True,
            colors=["complete", "awaiting_approval", "needs_evidence", "rejected"],
            fixed={"failed": CRITICAL},
        ),
        series(
            "Step latency p95",
            [
                (
                    f'histogram_quantile(0.95, sum by (le) (rate(pvc_step_duration_milliseconds_bucket{{step="{s}"}}[15m])))',
                    s,
                )
                for s in STEPS[:-1]
            ],
            "ms",
            (12, 4, 12, 8),
            "SLO: p95 below 5 s for every automated step.",
            colors=STEPS[:-1],
        ),
        series(
            "HTTP 5xx ratio",
            [
                (
                    f'sum(rate(pvc_http_requests_total{{service="{s}",status_class="5xx"}}[5m])) / '
                    f'sum(rate(pvc_http_requests_total{{service="{s}"}}[5m]))',
                    s,
                )
                for s in ("mcp", "api")
            ],
            "percentunit",
            (0, 12, 8, 8),
            "Error-budget burn source.",
            colors=["mcp", "api"],
        ),
        series(
            "Tool calls by outcome",
            [
                (f'sum(rate(pvc_tool_calls_total{{outcome="{o}"}}[5m]))', o)
                for o in ("ok", "rejected", "not_found", "denied")
            ],
            "reqps",
            (8, 12, 8, 8),
            "'denied' spikes may indicate probing across companies.",
            colors=["ok", "rejected", "not_found", "denied"],
        ),
        series(
            "Adapter errors",
            [("sum by (step) (increase(pvc_adapter_errors_total[1h]))", "{{step}}")],
            "short",
            (16, 12, 8, 8),
            "Source-system failures by workflow step.",
        ),
        series(
            "Model tokens per hour",
            [(f'sum(increase(pvc_model_tokens_total{{direction="{d}"}}[1h]))', d) for d in ("input", "output")],
            "short",
            (0, 20, 8, 8),
            "Judgment-step usage (PVC_PROPOSER=model).",
            colors=["input", "output"],
        ),
        series(
            "Model cost per day (USD)",
            [("sum(increase(pvc_model_cost_usd_total[1d]))", "cost")],
            "currencyUSD",
            (8, 20, 8, 8),
            "Estimated from token usage and list prices.",
            colors=["cost"],
        ),
        series(
            "Approval turnaround",
            [
                ("histogram_quantile(0.5, sum by (le) (rate(pvc_approval_turnaround_hours_bucket[1d])))", "p50"),
                ("histogram_quantile(0.9, sum by (le) (rate(pvc_approval_turnaround_hours_bucket[1d])))", "p90"),
            ],
            "h",
            (16, 20, 8, 8),
            "Hours from approval request to human decision.",
            colors=["p50", "p90"],
        ),
        series(
            "KPI off-track alerts",
            [(f'sum(increase(pvc_kpi_off_track_total{{rule="{r}"}}[1d]))', r) for r in ("threshold", "trend")],
            "short",
            (0, 28, 12, 8),
            "Deterministic variance alerts from the KPI monitoring job.",
            colors=["threshold", "trend"],
        ),
    ]
    return {
        "uid": "pvc-overview",
        "title": "PE Value Creation OS - overview",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "tags": ["pvc"],
        "time": {"from": "now-7d", "to": "now"},
        "refresh": "1m",
        "templating": {"list": [{"name": "datasource", "type": "datasource", "query": "prometheus"}]},
        "panels": panels,
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
