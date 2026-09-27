# Bad calculation release (rollback and recompute)

1. Roll back to the previous image ([service-errors.md](service-errors.md)).
2. Scope the damage: every value case stores `calc_version` and `inputs_hash`. With the read-only role, list affected runs with `select distinct run_id from value_cases where calc_version = <bad version>`.
3. Fix the calculation, bump its `CALC_VERSION`, and add a golden test that reproduces the defect.
4. After release, recompute each affected run with `pvc recompute --run <run_id> --reason "<incident id>"`. Old value cases are superseded, not deleted, and the recompute is audited with before and after values.
5. If an affected plan was already approved, send the approver the before/after diff. Approval is not re-applied automatically.
