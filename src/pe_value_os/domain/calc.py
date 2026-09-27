"""Shared calculation helpers: month arithmetic, ARR ledger, rounding, and metric results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean, pstdev
from typing import Any

from pydantic import BaseModel, Field

from .source_models import CustomerArrMonth, PnLAccount, PnLLine

RATIO_Q = Decimal("0.0001")
MONEY_Q = Decimal("0.01")
ZERO = Decimal(0)


class MetricUnavailable(ValueError):
    """The metric cannot be computed from the available data."""


def q_ratio(x: Decimal) -> Decimal:
    return x.quantize(RATIO_Q, rounding=ROUND_HALF_UP)


def q_money(x: Decimal) -> Decimal:
    return x.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def month_of(d: date) -> date:
    return date(d.year, d.month, 1)


def months_between(a: date, b: date) -> int:
    """Whole months from a to b (b - a)."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def month_range(start: date, end: date) -> list[date]:
    """Inclusive list of month starts from start to end."""
    out, m = [], month_of(start)
    while m <= end:
        out.append(m)
        m = add_months(m, 1)
    return out


def quarter_start(d: date) -> date:
    return date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)


def is_quarter_end_window(d: date) -> bool:
    """True if d falls in the second half (day 16 onward) of a calendar quarter's final month."""
    return d.month in (3, 6, 9, 12) and d.day >= 16


class MetricValue(BaseModel):
    name: str
    value: Decimal | None
    unit: str
    period_start: date | None = None
    period_end: date | None = None
    variant: str
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class ArrLedger:
    """Customer x month ARR matrix built from CustomerArrMonth rows (duplicate rows are summed)."""

    def __init__(self, rows: Iterable[CustomerArrMonth]):
        self.by_customer: dict[str, dict[date, Decimal]] = defaultdict(dict)
        months: set[date] = set()
        for r in rows:
            cur = self.by_customer[r.customer_id].get(r.month, ZERO)
            self.by_customer[r.customer_id][r.month] = cur + r.arr
            months.add(r.month)
        self.months = sorted(months)

    @property
    def first_month(self) -> date:
        return self.months[0]

    @property
    def last_month(self) -> date:
        if not self.months:
            raise MetricUnavailable("No ARR data")
        return self.months[-1]

    def arr(self, customer_id: str, m: date) -> Decimal:
        return self.by_customer.get(customer_id, {}).get(m, ZERO)

    def total(self, m: date) -> Decimal:
        return sum((v.get(m, ZERO) for v in self.by_customer.values()), ZERO)

    def active(self, m: date) -> list[str]:
        return [c for c, v in self.by_customer.items() if v.get(m, ZERO) > 0]

    def last_arr_before(self, customer_id: str, m: date) -> Decimal:
        prior = [mm for mm in self.by_customer.get(customer_id, {}) if mm < m]
        return self.by_customer[customer_id][max(prior)] if prior else ZERO

    def bridge(self, start: date, end: date, customers: set[str] | None = None) -> dict[str, Decimal]:
        """ARR bridge from month `start` (opening) to `end` (closing), accumulated month by month."""
        ids = customers if customers is not None else set(self.by_customer)
        out = {k: ZERO for k in ("opening", "new", "expansion", "contraction", "churn", "closing")}
        out["opening"] = sum((self.arr(c, start) for c in ids), ZERO)
        out["closing"] = sum((self.arr(c, end) for c in ids), ZERO)
        prev = start
        for m in month_range(add_months(start, 1), end):
            for c in ids:
                a, b = self.arr(c, prev), self.arr(c, m)
                if a == 0 and b > 0:
                    out["new"] += b
                elif a > 0 and b == 0:
                    out["churn"] += a
                elif b > a:
                    out["expansion"] += b - a
                elif b < a:
                    out["contraction"] += a - b
            prev = m
        return out

    def retention(self, start: date, end: date, customers: set[str] | None = None) -> tuple[Decimal, Decimal, Decimal]:
        """(opening ARR, retained-capped ARR, cohort closing ARR) for customers active at `start`."""
        ids = [c for c in self.active(start) if customers is None or c in customers]
        opening = sum((self.arr(c, start) for c in ids), ZERO)
        kept = sum((min(self.arr(c, end), self.arr(c, start)) for c in ids), ZERO)
        closing = sum((self.arr(c, end) for c in ids), ZERO)
        return opening, kept, closing


def pnl_by_month(lines: Iterable[PnLLine]) -> dict[date, dict[PnLAccount, Decimal]]:
    out: dict[date, dict[PnLAccount, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for line in lines:
        out[line.month][line.account] += line.amount
    return out


def sum_accounts(pnl: dict[date, dict[PnLAccount, Decimal]], months: Iterable[date], *accounts: PnLAccount) -> Decimal:
    return sum((pnl.get(m, {}).get(a, ZERO) for m in months for a in accounts), ZERO)


REVENUE = (PnLAccount.REVENUE_SUBSCRIPTION, PnLAccount.REVENUE_SERVICES)
SUB_COGS = (PnLAccount.COGS_HOSTING, PnLAccount.COGS_THIRD_PARTY, PnLAccount.COGS_SUPPORT)
ALL_COSTS = (
    PnLAccount.COGS_HOSTING,
    PnLAccount.COGS_THIRD_PARTY,
    PnLAccount.COGS_SUPPORT,
    PnLAccount.COGS_SERVICES,
    PnLAccount.SALES_MARKETING,
    PnLAccount.RESEARCH_DEVELOPMENT,
    PnLAccount.GENERAL_ADMIN,
)


def cv(values: list[float]) -> float | None:
    """Coefficient of variation (population)."""
    if len(values) < 2:
        return None
    mu = mean(values)
    return pstdev(values) / mu if mu else None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if not sx or not sy:
        return None
    return float(sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy))


def dec(x: float | None) -> Decimal | None:
    return None if x is None else q_ratio(Decimal(str(x)))


def jsonable(obj: Any) -> Any:
    """Convert nested Decimals/dates for storage in JSON artifacts."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    return obj
