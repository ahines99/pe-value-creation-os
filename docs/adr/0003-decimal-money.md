# ADR 0003: Decimal for all currency and rates

- **Status:** accepted
- **Date:** 2026-09-23
- **Ticket:** PVC-007

## Context
Value cases are presented to investment committees. Binary floating point introduces representation error (0.1 + 0.2 != 0.3) that surfaces as unexplained cents and failed equality checks in golden tests.

## Decision
Currency amounts and rates are `decimal.Decimal` in contracts and services and `numeric` in PostgreSQL. Rounding happens only at presentation. JSON serialisation emits decimals as strings.

## Consequences
- Exact, reproducible golden tests and stable `inputs_hash` values.
- Callers must send numbers as strings or numbers that parse exactly; Pydantic handles conversion.
