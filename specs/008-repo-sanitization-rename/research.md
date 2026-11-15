# Research: Repository Sanitization & Rename

## R1 — History rewrite tool
- **Decision**: `git filter-branch` (index-filter + tree-filter + msg-filter, `--prune-empty`, `--tag-name-filter cat`, `-- --all`).
- **Rationale**: `git-filter-repo` is not installed and the sandbox has no network. History is small (~37 commits, ~364 files) so filter-branch speed is irrelevant.
- **Alternatives**: `git-filter-repo` (preferred upstream, unavailable offline); BFG (JVM, violates the project's zero-JVM stance); squash into a fresh single commit (loses history, violates FR-009).

## R2 — Safe execution model
- **Decision**: mirror backup → rewrite in a throw-away clone → forced fetch of rewritten refs into the real repo → purge `refs/original`, remote-tracking refs, reflogs → `gc --prune=now`.
- **Rationale**: filter-branch refuses a dirty tree and the real working tree has uncommitted work (specs 007/008, docs, tools) that must survive.
- **Alternatives**: stash and rewrite in place (risk to untracked work); swapping `.git` directories (fragile).

## R3 — Where do sensitive literals live?
- **Decision**: a gitignored `.sanitize-patterns.local` (JSON). Committed code and specs contain no old-name literals, filename of the PDF, or IP.
- **Rationale**: otherwise the published repo would itself contain what we purge, defeating SC-001/SC-002.
- **Alternatives**: constants in script (leaks); environment variables (awkward for ~20 patterns).

## R4 — IP stripping
- **Decision**: The personal IP exists only inside the watermarked PDF blob (verified: not in text files); removing the PDF from all history removes it. Additionally a generic rule redacts any IPv4 not in loopback/private/link-local/documentation ranges (`0.0.0.0` kept) in text files, and watermark lines are dropped. `8.8.8.8` in `tests/unit/discovery/test_pattern_profiler.py` is a benign well-known public DNS test value and is a documented exception (allow-list in the pattern file).
- **Rationale**: Satisfies FR-003/003a/003b and SC-002a while avoiding breaking fixtures.
- **Alternatives**: redact all IPs (breaks tests/documentation examples).

## R5 — Rename mapping (applied most-specific first)
1. Local path prefix to the project folder → removed (relative links); any remaining `/home/<user>` → `/home/user`.
2. Slug variants (`...-s-...`, repo URL) → `poor-mans-defense-lakehouse`.
3. Display variants (hyphen/space/apostrophe spellings of the previous name, `.IA` suffix optional) → `Poor Man's Defense Lakehouse`.
4. `PoorMansDefenseLakehouse` identifier → `PoorMansDefenseLakehouse`.
References to the real ARTEMIS.IA program (without the "Poor Man's" prefix) are untouched (spec assumption).
- Python package metadata (`pyproject.toml` description/name fields) updated by the same rules; the importable package and `artemis` CLI keep their names (out of scope).

## R6 — Binary files
- **Decision**: Text rules apply only to files that decode as UTF-8 without NUL bytes. SQLite DB, PPTX and PDFs are scanned in verification (`strings`, `unzip -p`, `pdftotext`) and handled individually if they hit.
- **Rationale**: Blind byte substitution can corrupt binaries.

## R7 — Remote and residual copies
- GitHub retains old objects after a force push (cached views, PR refs). The cleanest option is deleting and recreating the remote under the new name, or contacting GitHub support to run garbage collection. Documented in the quickstart; not automated.
