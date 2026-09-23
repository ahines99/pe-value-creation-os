"""Outbound network allow-list (PVC-094).

Every outbound HTTP client in the application is built here. Requests to hosts not on the allow-list fail
before any bytes leave the process. Production additionally enforces the same list at the network layer
(infra/terraform/modules/pvc/network.tf).
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import httpx

DEFAULT_ALLOWED = ("api.anthropic.com",)


class EgressDenied(PermissionError):
    pass


def allowed_hosts() -> set[str]:
    extra = os.environ.get("PVC_EGRESS_ALLOWLIST", "")
    return {h.strip().lower() for h in (*DEFAULT_ALLOWED, *extra.split(",")) if h.strip()}


def check_url(url: str) -> None:
    host = (urlsplit(url).hostname or "").lower()
    hosts = allowed_hosts()
    if not any(host == h or (h.startswith("*.") and host.endswith(h[1:])) for h in hosts):
        raise EgressDenied(f"Outbound request to {host!r} is not on the egress allow-list")


def _hook(request: httpx.Request) -> None:
    check_url(str(request.url))


def checked_client(**kwargs: Any) -> httpx.Client:
    hooks = kwargs.pop("event_hooks", {})
    hooks.setdefault("request", []).append(_hook)
    return httpx.Client(event_hooks=hooks, **kwargs)


def checked_async_client(**kwargs: Any) -> httpx.AsyncClient:
    async def ahook(request: httpx.Request) -> None:
        check_url(str(request.url))

    hooks = kwargs.pop("event_hooks", {})
    hooks.setdefault("request", []).append(ahook)
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
