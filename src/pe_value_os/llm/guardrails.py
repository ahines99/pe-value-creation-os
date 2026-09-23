"""Guardrails for model output (PVC-072, PVC-073).

`unsupported_numbers` finds numbers in model-written text that do not appear in the tool outputs the model was
given (allowing for the rounding shown in the text, and percent formatting). Proposals or narratives that
introduce new numbers are rejected: the model supplies judgment, never arithmetic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

NUM = re.compile(r"(?<![\w.])-?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|[kKmM](?![a-zA-Z]))?")
STRUCTURAL = {Decimal(x) for x in (*range(0, 13), 24, 30, 60, 90, 100, 365)}


def _parse(token: str) -> tuple[Decimal, int] | None:
    t = token.replace("$", "").replace(",", "").replace(" ", "")
    mult = Decimal(1)
    if t.endswith("%"):
        t, mult = t[:-1], Decimal("0.01")
    elif t[-1:] in "kK":
        t, mult = t[:-1], Decimal(1000)
    elif t[-1:] in "mM":
        t, mult = t[:-1], Decimal(1_000_000)
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    places = len(t.split(".")[1]) if "." in t else 0
    # precision of the value in its own units, after scaling
    scale = 2 if mult < 1 else 0  # percent: two extra decimal places in fraction units
    return v * mult, places + scale if mult <= 1 else -(len(str(int(mult))) - 1) + places


def source_numbers(obj: Any) -> list[Decimal]:
    out: list[Decimal] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list | tuple):
            for v in x:
                walk(v)
        elif isinstance(x, bool):
            return
        elif isinstance(x, int | float | Decimal):
            out.append(Decimal(str(x)))
        elif isinstance(x, str):
            for m in NUM.finditer(x):
                p = _parse(m.group())
                if p:
                    out.append(p[0])

    walk(obj)
    return out


def unsupported_numbers(text: str, sources: Iterable[Decimal]) -> list[str]:
    src = list(sources)
    bad = []
    for m in NUM.finditer(text):
        token = m.group()
        p = _parse(token)
        if p is None:
            continue
        v, places = p
        if v in STRUCTURAL or (Decimal(1990) <= v <= Decimal(2100) and places == 0):
            continue
        q = Decimal(1).scaleb(-places) if places >= 0 else Decimal(10) ** (-places)
        if not any(abs(s - v) <= q / 2 or abs(abs(s) - abs(v)) <= q / 2 for s in src):
            bad.append(token.strip())
    return bad
