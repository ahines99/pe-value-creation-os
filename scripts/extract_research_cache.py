"""Read an existing authorized Compustat cache into a private pilot bundle.

Requires PyArrow in the executing environment. No credentials, login, network or
source-repository imports. Run from the PE project root. Config is documented in
docs/pilot/public-company-research.md; output cannot leave var/research-pilot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path


def extract(cache: Path, config: dict, as_of: datetime) -> tuple[list[dict], dict[str, int]]:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    tickers = [config["focal_ticker"], *[p["ticker"] for p in config["peers"]]]
    statements = []
    counts = {"files": 0, "empty_files": 0, "eligible_rows": 0, "invalid_revenue": 0, "missing_vintage": 0}
    standard = {"indfmt": "INDL", "datafmt": "STD", "popsrc": "D", "consol": "C"}
    for period, table_name, suffix in (("annual", "funda", ""), ("quarterly", "fundq", "q")):
        files = sorted((cache / table_name).glob("*.parquet"))
        if not files:
            raise ValueError(f"no Parquet files in the {table_name} directory")
        mapping = {
            "revenue": f"sale{suffix}",
            "cogs": f"cogs{suffix}",
            "sga": f"xsga{suffix}",
            "research_development": f"xrd{suffix}",
            "operating_income": f"oiadp{suffix}",
        }
        for path in files:
            before = path.stat()
            parquet = pq.ParquetFile(path)
            counts["files"] += 1
            if not parquet.metadata.num_rows:
                counts["empty_files"] += 1
                continue
            names = parquet.schema_arrow.names
            required = {"tic", "gvkey", "datadate", f"fyear{suffix}", f"curcd{suffix}", f"sale{suffix}", *standard}
            if not required.issubset(names):
                raise ValueError(f"nonempty {table_name} extract is missing required columns")
            wanted = {
                *required,
                "fqtr",
                "conm",
                "available_ts_utc",
                "compustat_vintage_ts_utc",
                "ingest_ts_utc",
                *mapping.values(),
            }
            # First read identity/date only; full financial fields only for relevant files.
            identity = parquet.read(columns=["tic", "datadate"])
            mask = pc.and_(
                pc.is_in(identity["tic"].cast(pa.string()), value_set=pa.array(tickers)),
                pc.greater_equal(identity["datadate"], pa.scalar(date(config["first_year"] - 1, 1, 1))),
            )
            indices = pc.indices_nonzero(mask).to_pylist()
            if not indices:
                continue
            data = parquet.read(columns=sorted(wanted.intersection(names))).take(pa.array(indices)).to_pylist()
            selected = []
            for index, row in zip(indices, data, strict=True):
                if any(row.get(k) != v for k, v in standard.items()):
                    continue
                end = row["datadate"]
                if end is None or end > as_of.date():
                    continue
                revenue = row[mapping["revenue"]]
                if revenue is None or not Decimal(str(revenue)).is_finite() or revenue <= 0:
                    counts["invalid_revenue"] += 1
                    continue
                vintage = row.get("compustat_vintage_ts_utc") or row.get("ingest_ts_utc")
                if vintage is None:
                    counts["missing_vintage"] += 1
                    continue
                if vintage.tzinfo is None:
                    raise ValueError("source vintage has no timezone")
                if vintage > as_of:
                    continue
                normalized = {
                    "entity_id": str(row["gvkey"]),
                    "ticker": row["tic"],
                    "company": row.get("conm") or row["tic"],
                    "period": period,
                    "period_end": end.isoformat(),
                    "fiscal_year": row[f"fyear{suffix}"],
                    "fiscal_quarter": row.get("fqtr") if suffix else None,
                    "currency": row[f"curcd{suffix}"],
                    "unit": "millions",
                    "source": f"comp.{table_name}",
                    "source_file": str(path.resolve()),
                    "source_row": index,
                    "vintage": vintage.isoformat(),
                    "available_at": row["available_ts_utc"].isoformat() if row.get("available_ts_utc") else None,
                }
                for dest, source in mapping.items():
                    normalized[dest] = str(row[source]) if row.get(source) is not None else None
                selected.append(normalized)
            if selected:
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("source changed during extraction; retry against a stable cache")
                for row in selected:
                    row["source_sha256"] = digest
                statements.extend(selected)
    counts["eligible_rows"] = len(statements)
    return statements, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True, help="Compustat directory containing funda/ and fundq/")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--as-of", required=True, help="timezone-aware ISO timestamp")
    parser.add_argument("--name", default="input")
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of)
    if as_of.tzinfo is None:
        parser.error("--as-of requires a timezone")
    if as_of > datetime.now(UTC):
        parser.error("--as-of must not be in the future")
    root = Path.cwd().resolve() / "var" / "research-pilot"
    if root.resolve() != root:
        parser.error("private research directory must not redirect through a symbolic link")
    output = (root / f"{args.name}.json").resolve()
    if not output.is_relative_to(root) or output == root or output == args.config.resolve():
        parser.error("output must stay within var/research-pilot and must not overwrite config")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    rows, counts = extract(args.cache, config, as_of)
    bundle = {**config, "classification": "licensed_private", "as_of": as_of.isoformat(), "statements": rows}
    bundle.setdefault("source_notes", []).append(f"Local extraction counters: {json.dumps(counts, sort_keys=True)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"Private input written: {len(rows)} candidate rows; {counts['files']} files inspected.")


if __name__ == "__main__":
    main()
