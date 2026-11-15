# Quickstart: Knowledge Discovery Graph

Validation scenarios mapping to the user stories. Contracts: [CLI](./contracts/cli_contracts.md), [API](./contracts/api_contracts.md).

## Prerequisites
- Stack running (`docker compose up -d`): Memgraph, MinIO, PostgreSQL, Redis, Temporal worker.
- Logged in: `artemis login`.
- Optional: `GEMINI_API_KEY` set. Without it, enrichment reports `skipped_no_ai` and only structural/pattern discovery runs.

## Scenario 1 – Project discovery (US1)
```bash
artemis project create --id alpha --name "Alpha"
artemis project ingest --project alpha --dataset patients --tier bronze --file ./sample/patients.csv
artemis project discover alpha
```
Expect: `patients` listed with tier, format, row count, attributes and types; `Enrichment: pending|completed`.

## Scenario 2 – Cross-project entity (US2)
```bash
artemis project create --id beta --name "Beta"
artemis project ingest --project beta --dataset accounts --tier bronze --file ./sample/accounts.csv
artemis discover entity --value "ACCT-99812" --json
```
Expect: matches in both `alpha` and `beta` (value in both fixtures), no raw rows or S3 URIs for foreign projects. Unknown value → empty matches, exit 0.

## Scenario 3 – Lineage (US3)
```bash
artemis pipeline run ...   # derive a SILVER/GOLD dataset in alpha
artemis discover lineage --project alpha --dataset patients_gold
```
Expect: source dataset and pipeline run (status, time) shown; standalone datasets show as root.

## Scenario 4 – Natural language (US4)
```bash
artemis ask "Which projects reference account ACCT-99812?"
```
Expect: answer names `alpha` and `beta`.

## Scenario 5 – Failure handling
```bash
artemis discover jobs --project alpha --status failed
artemis discover reindex --project alpha
```

## Scenario 6 – Membership scoping (FR-021/FR-022)
```bash
artemis project members add alpha --user alice
# As alice (member of alpha only): search for the value that also exists in beta
artemis discover entity --value "ACCT-99812" --json
artemis project discover beta        # behaves like an unknown project
artemis project members remove alpha --user alice
artemis discover entity --value "ACCT-99812" --json   # no matches, no counts
```
Expect: alice sees only `alpha` matches, with no trace (name, count) of `beta`; after removal she sees nothing from `alpha`.

## Automated checks
```bash
pytest tests/contract/test_discovery_contracts.py tests/unit/discovery
pytest tests/integration/test_knowledge_discovery.py
make test
```
