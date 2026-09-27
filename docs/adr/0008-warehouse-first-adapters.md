# ADR 0008: Warehouse-first data access, vendor APIs where no warehouse exists

- **Status:** accepted (pilot portco to be confirmed)
- **Date:** 2026-09-23
- **Ticket:** PVC-110

## Context
Portfolio companies differ: some run a warehouse with dbt models over their ERP, CRM, billing and support data;
others have only SaaS systems. Per-system API adapters mean one integration per vendor per company, each with its
own credentials, rate limits and schema drift. A warehouse view contract means one integration per company.

## Decision
1. **Warehouse first.** Where a warehouse exists, the portco (or our dbt package) exposes `pvc_<dataset>` views
   matching `docs/data_contracts.md`, plus `pvc_company_profile` and `pvc_dataset_freshness`. `WarehouseAdapter`
   reads them read-only through SQLAlchemy.
2. **CSV export drop** for companies without a warehouse (`CsvExportAdapter`), same contract.
3. **Vendor APIs** (Stripe billing, HubSpot CRM, Zendesk support) when neither is available or fresher data is
   needed, combined per company by `CompositeAdapter` with deterministic entity resolution.
4. Every adapter passes one conformance suite (`tests/test_adapters.py`): evidence registration with
   deterministic ids, company isolation, validated records, error classification (429/5xx transient, other 4xx
   permanent), complete pagination and the egress allow-list.

## Consequences
- The pilot's source systems decide the mix; the conformance suite, not bespoke tests, gates each adapter.
- Vendor adapters are verified against simulators that implement each vendor's paging semantics; they must be
  re-verified against the vendor's sandbox with real credentials during pilot onboarding (PVC-155 checklist).
- Salesforce, NetSuite and other systems are added as `DatasetSource` implementations when a portco needs them.
