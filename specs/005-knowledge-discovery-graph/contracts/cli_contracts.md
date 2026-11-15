# CLI Contracts: Discovery

**Feature**: `005-knowledge-discovery-graph` | All commands accept `--json`; results on stdout, errors on stderr, non-zero exit on error.

```bash
# Knowledge summary of one project (FR-010)
artemis project discover <project_id> [--json]

# Cross-project entity search (FR-011); at least one of --value / --type
artemis discover entity --value "ACCT-99812" [--type Identifier] [--fuzzy] [--json]

# Lineage of a dataset (FR-012)
artemis discover lineage --project <project_id> --dataset <dataset_id> [--depth 10] [--json]

# Re-index existing data / retry failed jobs (spec assumption)
artemis discover reindex --project <project_id> [--dataset <dataset_id>]

# Indexing job status (FR-019)
artemis discover jobs --project <project_id> [--status failed] [--json]

# Project membership (FR-022); add/remove require owner or admin
artemis project members list <project_id> [--json]
artemis project members add <project_id> --user <user_id>
artemis project members remove <project_id> --user <user_id>
```

## Visibility rule (FR-021)
`discover entity`, `discover lineage` and `ask` results include only projects the caller is a member of; other projects are omitted entirely, including from counts. `project discover <id>` for a non-member project behaves like an unknown project (exit 1, same message).

## Exit codes
| Code | Meaning |
|------|---------|
| 0 | Success (including empty results) |
| 1 | Unknown project/dataset or invalid arguments |
| 2 | Service unavailable (graph store unreachable) |

## Human output example (`project discover`)
```
=== Knowledge Summary: clinical-trials-2026 ===
Enrichment: completed
Data Resources (2):
  - patient_vitals (BRONZE, PARQUET, 50,000 rows)
      subject_id VARCHAR -> Taxonomy:PatientIdentifier (0.93)
      blood_pressure INTEGER
      Entities: 1,200 Identifier
```
Empty project prints `No indexed resources.`; pending enrichment prints `Enrichment: pending`.
