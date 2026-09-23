"""Notification delivery (PVC-123, PVC-064).

Channels are configured by a human through environment/secret configuration. No MCP tool or model can send
messages: delivery happens only in the worker, only to the configured channel, and only for read-only digests
and escalations. Webhook hosts are checked against the egress allow-list (PVC-094).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .adapters.repositories import Repository
from .domain.kpi_models import Notification
from .domain.runs import ApprovalRecord
from .egress import checked_client


class Notifier(Protocol):
    channel: str

    def deliver(self, repo: Repository, n: Notification) -> None: ...

    def escalate(self, repo: Repository, approval: ApprovalRecord, contact: str) -> None: ...


class OutboxNotifier:
    """Writes messages to a local outbox directory (dev, tests, and air-gapped deployments)."""

    channel = "outbox"

    def __init__(self, directory: Path | str):
        self.dir = Path(directory)

    def _write(self, name: str, payload: dict[str, str]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def deliver(self, repo: Repository, n: Notification) -> None:
        self._write(n.notification_id, {"company_id": n.company_id, "subject": n.subject, "body": n.body})

    def escalate(self, repo: Repository, approval: ApprovalRecord, contact: str) -> None:
        self._write(
            f"escalation-{approval.approval_id}",
            {
                "to": contact,
                "company_id": approval.company_id,
                "run_id": approval.run_id,
                "subject": "Plan approval overdue",
                "body": f"Approval {approval.approval_id} has been pending since {approval.requested_at.isoformat()}.",
            },
        )


class WebhookNotifier:
    """Posts to a human-configured incoming webhook (for example a Slack channel)."""

    channel = "webhook"

    def __init__(self, url: str):
        self.url = url

    def _post(self, text: str) -> None:
        with checked_client(timeout=10) as client:
            client.post(self.url, json={"text": text}).raise_for_status()

    def deliver(self, repo: Repository, n: Notification) -> None:
        self._post(f"*{n.subject}* ({n.company_id})\n{n.body}")

    def escalate(self, repo: Repository, approval: ApprovalRecord, contact: str) -> None:
        self._post(f"Plan approval overdue for {approval.company_id} (run {approval.run_id}); escalated to {contact}.")


def notifier_from_env() -> Notifier:
    url = os.environ.get("PVC_NOTIFY_WEBHOOK_URL")
    if url:
        return WebhookNotifier(url)
    return OutboxNotifier(os.environ.get("PVC_OUTBOX_DIR", "var/outbox"))


def mark_delivered(n: Notification) -> Notification:
    return n.model_copy(update={"delivered_at": datetime.now(UTC), "status": "delivered"})
