"""Guardrails for model output (PVC-072, PVC-073).

`unsupported_numbers` finds quantities in model-written text that do not appear in the tool outputs the model was
given, allowing for the rounding shown in the text. Proposals or narratives that introduce new numbers are
rejected: the model supplies judgment, never arithmetic.

Recognised forms:
- digits with optional sign, currency, thousands separators and decimals: `-$1,234.5`
- scale suffixes and words: `3.5k`, `$2M`, `$1.2bn`, `$3.5 million`, `4 thousand`
- percentages and basis points: `12%`, `12 percent`, `50 bps`
- numbers written as words: `two million`, `twenty-five percent`, `half a million`
- multiplier claims: `3x`, `double`, `tripling`, `fivefold`

Small bare integers (0-12 and a few calendar counts) and bare four-digit years are structural and allowed.
A number written with an explicit minus sign must match a source value with the same sign.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

SCALE_WORDS = {
    "thousand": 3,
    "k": 3,
    "million": 6,
    "mn": 6,
    "mm": 6,
    "m": 6,
    "billion": 9,
    "bn": 9,
    "b": 9,
    "trillion": 12,
}
NUM = re.compile(
    r"(?<![\w.])(?P<sign>-)?(?P<cur>\$)?(?P<num>\d[\d,]*(?:\.\d+)?)"
    r"(?:\s?(?P<pct>%|percent\b|per\s?cent\b|bps\b|basis\s+points\b)"
    r"|\s?(?P<scale>thousand|million|billion|trillion|mn|mm|bn)\b"
    r"|(?P<short>[kKmMbB])(?![a-zA-Z])"
    r"|(?P<times>x)\b)?",
    re.IGNORECASE,
)
STRUCTURAL = {Decimal(x) for x in (*range(0, 13), 24, 30, 60, 90, 100, 365)}

SMALL = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen".split()
    )
}
TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
WORD_SCALES = {"hundred": 2, "thousand": 3, "million": 6, "billion": 9, "trillion": 12}
WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
MULTIPLIER = re.compile(
    r"\b(?P<w>doubl(?:e[sd]?|ing)|tripl(?:e[sd]?|ing)|quadrupl(?:e[sd]?|ing)|halv(?:e[sd]?|ing)"
    r"|(?P<n>two|three|four|five|six|seven|eight|nine|ten)fold)\b(?![- ]?count)",
    re.IGNORECASE,
)
MULTIPLIER_VALUES: dict[str, Decimal] = {
    "doubl": Decimal(2),
    "tripl": Decimal(3),
    "quadrupl": Decimal(4),
    "halv": Decimal("0.5"),
}


@dataclass(frozen=True)
class Quantity:
    text: str
    value: Decimal
    tolerance: Decimal
    signed: bool = False  # an explicit minus sign: the sign must match
    relative: bool = False  # multiplier claim: tolerance is relative to the value
    plain: bool = False  # bare integer with no currency, unit or scale


def _half_unit(places: int) -> Decimal:
    return Decimal(1).scaleb(-places) / 2


def _digit_quantities(text: str) -> list[Quantity]:
    out = []
    for m in NUM.finditer(text):
        raw = m.group("num").replace(",", "")
        try:
            v = Decimal(raw)
        except InvalidOperation:
            continue
        places = len(raw.split(".")[1]) if "." in raw else 0
        pct, scale, short, times = m.group("pct"), m.group("scale"), m.group("short"), m.group("times")
        if times:
            out.append(Quantity(m.group().strip(), v, Decimal("0.05"), relative=True))
            continue
        exp = 0
        if pct:
            exp = -4 if pct.lower().startswith(("bps", "basis")) else -2
        elif scale:
            exp = SCALE_WORDS[scale.lower()]
        elif short:
            exp = SCALE_WORDS[short.lower()]
        value = -v.scaleb(exp) if m.group("sign") else v.scaleb(exp)
        plain = not (m.group("sign") or m.group("cur") or pct or scale or short) and places == 0
        out.append(
            Quantity(m.group().strip(), value, _half_unit(places - exp), signed=bool(m.group("sign")), plain=plain)
        )
    return out


def _word_quantities(text: str) -> list[Quantity]:
    """Numbers spelled out in words, e.g. 'two million', 'twenty-five percent', 'half a million'."""
    words = [(m.group().lower(), m.start(), m.end()) for m in WORD.finditer(text)]
    out: list[Quantity] = []
    i = 0
    while i < len(words):
        parts = words[i][0].split("-")
        if not (
            parts[0] in SMALL
            or parts[0] in TENS
            or parts[0] == "half"
            or (parts[0] in ("a", "an") and i + 1 < len(words) and words[i + 1][0] in WORD_SCALES)
        ):
            i += 1
            continue
        start, total, current, smallest, seen, j = words[i][1], Decimal(0), Decimal(0), 0, False, i
        fraction = False  # 'half a million' is stated to one decimal place of its scale
        while j < len(words):
            w = words[j][0]
            tokens = w.split("-")
            if all(t in SMALL or t in TENS for t in tokens):
                current += sum(Decimal(SMALL.get(t, TENS.get(t, 0))) for t in tokens)
                seen = True
            elif w == "half":
                current += Decimal("0.5")
                seen = fraction = True
            elif w in ("a", "an") and j + 1 < len(words) and words[j + 1][0] in WORD_SCALES:
                current = current or Decimal(1)
            elif (
                w == "and"
                and seen
                and j + 1 < len(words)
                and (words[j + 1][0].split("-")[0] in SMALL or words[j + 1][0].split("-")[0] in TENS)
            ):
                pass
            elif w in WORD_SCALES and (seen or current):
                exp = WORD_SCALES[w]
                if exp == 2:
                    current = (current or Decimal(1)) * 100
                else:
                    total += (current or Decimal(1)).scaleb(exp)
                    current = Decimal(0)
                smallest = exp
                seen = True
            else:
                break
            j += 1
        if not seen:
            i += 1
            continue
        value, exp = total + current, smallest if not current else 0
        exp -= 1 if fraction else 0
        end = words[j - 1][2]
        if (
            j < len(words)
            and words[j][0] in ("percent", "per")
            and (words[j][0] == "percent" or (j + 1 < len(words) and words[j + 1][0] == "cent"))
        ):
            value, exp = value.scaleb(-2), exp - 2
            end = words[j + (0 if words[j][0] == "percent" else 1)][2]
            j += 1 if words[j][0] == "percent" else 2
        plain = value == value.to_integral_value() and exp == 0 and value <= 12
        out.append(Quantity(text[start:end], value, _half_unit(-exp), plain=plain))
        i = j
    return out


def _multiplier_quantities(text: str) -> list[Quantity]:
    out = []
    for m in MULTIPLIER.finditer(text):
        if m.group("n"):
            v = Decimal(SMALL[m.group("n").lower()])
        else:
            v = next(Decimal(val) for stem, val in MULTIPLIER_VALUES.items() if m.group("w").lower().startswith(stem))
        out.append(Quantity(m.group(), v, Decimal("0.05"), relative=True))
    return out


def quantities(text: str) -> list[Quantity]:
    return _digit_quantities(text) + _word_quantities(text) + _multiplier_quantities(text)


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
            out.extend(q.value for q in quantities(x))

    walk(obj)
    return out


def _supported(q: Quantity, src: list[Decimal]) -> bool:
    for s in src:
        if q.relative:
            if s and abs(s - q.value) <= abs(q.value) * q.tolerance:
                return True
            continue
        if abs(s - q.value) <= q.tolerance:
            return True
        if not q.signed and abs(abs(s) - q.value) <= q.tolerance:
            return True  # "a loss of $1.2M" citing a negative source value
    return False


def unsupported_numbers(text: str, sources: Iterable[Decimal]) -> list[str]:
    src = list(sources)
    bad = []
    for q in quantities(text):
        if q.plain and (q.value in STRUCTURAL or Decimal(1990) <= q.value <= Decimal(2100)):
            continue
        if not _supported(q, src):
            bad.append(q.text)
    return bad
