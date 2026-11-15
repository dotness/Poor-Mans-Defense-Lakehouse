# Data Model: Repository Sanitization & Rename

## PatternConfig (`.sanitize-patterns.local`, JSON, untracked)

| Field | Type | Description |
|-------|------|-------------|
| `purge_paths` | list[string] | Paths removed from every commit |
| `purge_blob_sha256` | list[string] | Optional content hashes of purged files (verification) |
| `forbidden_literals` | list[string] | Regexes that must have zero hits in tree/history (PDF name, watermark text, personal IP, home path) |
| `drop_line_regexes` | list[string] | Lines removed entirely from text files (watermark lines) |
| `rename_rules` | list[[regex, replacement]] | Ordered rename mapping (most specific first) |
| `ip_redaction` | object | `enabled`, `placeholder`, `allow` (list of IPs / CIDRs preserved) |
| `verify_exclude_paths` | list[string] | Paths excluded from verification (e.g. the pattern file) |

Validation: regexes compile; `rename_rules` order preserved; no rule may match its own replacement (idempotent).

## VerificationReport (stdout / `--json`)

| Field | Description |
|-------|-------------|
| `commits_before`, `commits_after`, `commits_dropped` | Counts (SC-005) |
| `order_preserved` | Subject-sequence comparison after removing dropped commits |
| `hits` | list of `{pattern, location, ref}`; must be empty |
| `ip_exceptions` | Remaining public IPs with justification |
| `tip_diff` | Summary of tip-tree differences vs backup (only purged paths + text-rule changes) |
| `status` | `PASS` / `FAIL` |

## HistoryBackup
Bare mirror clone directory outside the workspace; invariants: `git fsck` clean, tip SHAs equal to the original refs at backup time.

State flow: `Original → Backed-up → Rewritten(clone) → Imported → Pruned → Verified`.
