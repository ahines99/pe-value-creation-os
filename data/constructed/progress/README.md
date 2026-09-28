# Constructed operating exercise

Every operating number in `underwriting.json` is analyst-authored. None describes
an actual Progress customer cohort, ticket population, vendor contract, staffing
action or receivable. Public Progress financial facts provide context through the
separate [public baseline](../../public/progress/README.md); consolidated statements
do not establish the constructed operating assumptions.

Regenerate and evaluate without vendor accounts or a live model:

```powershell
uv run python scripts/build_underwriting_example.py
uv run pvc underwriting --input data/constructed/progress/underwriting.json --output var/underwriting/report
```

The generator declares three judgmental cases, rationale, units and falsification
conditions for each numeric input. The same three initiative identities persist
across scenarios. Cost and benefit dates can differ. The downside delays benefits,
raises implementation/ongoing costs and removes the service-spend action.

To compare a narrower scope, exclude an initiative by its stable ID:

```powershell
uv run pvc underwriting --input data/constructed/progress/underwriting.json --exclude service-automation --output var/underwriting/without-service
```

Repeat `--exclude` for additional initiatives. Excluding all three retains the
25,000 shared commitment; it cannot erase a cost assumed already committed.
These are analytical selection changes, not approvals or source-system actions.

The [method and limitations](../../../docs/adr/0010-monthly-underwriting.md) define
the cash proxy, rounding/timing, overlap guard and arbitrary 6×/8×/10× sensitivity
grid. The exercise does not yet impose resource capacity, persist case revisions,
compare actual results, or complete the executive decision memo. It is an input to
those later integrations, not a recommendation that Progress execute these levers.
