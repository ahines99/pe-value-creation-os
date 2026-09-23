"""PVC-012: source schemas and row-level validation errors."""

import pytest

from pe_value_os.domain.source_models import (
    CustomerArrMonth,
    PnLLine,
    SourceValidationError,
    parse_csv,
)

ARR_HEADER = "company_id,customer_id,month,arr,product,price_book_id\n"


def test_valid_rows_parse():
    recs, errs = parse_csv(CustomerArrMonth, ARR_HEADER + "c1,cu1,2026-01-01,1200.50,p,pb\n", "arr.csv")
    assert errs == [] and str(recs[0].arr) == "1200.50"


def test_errors_name_file_row_and_field():
    text = ARR_HEADER + "c1,cu1,2026-01-01,100,p,pb\nc1,cu2,2026-01-15,100,p,pb\nc1,cu3,2026-02-01,-5,p,pb\n"
    recs, errs = parse_csv(CustomerArrMonth, text, "arr.csv")
    assert len(recs) == 1
    assert [(e.source, e.row, e.field) for e in errs] == [("arr.csv", 3, "month"), ("arr.csv", 4, "arr")]
    assert "arr.csv row 3 field 'month'" in str(errs[0])


def test_strict_mode_raises():
    with pytest.raises(SourceValidationError, match="row 2 field 'currency'"):
        parse_csv(
            PnLLine,
            "company_id,month,account,amount,currency\nc1,2026-01-01,general_admin,5,usd\n",
            "pnl.csv",
            strict=True,
        )


def test_unknown_columns_rejected():
    _, errs = parse_csv(CustomerArrMonth, ARR_HEADER.strip() + ",extra\nc1,cu1,2026-01-01,1,p,pb,x\n", "a.csv")
    assert errs and errs[0].field == "extra"
