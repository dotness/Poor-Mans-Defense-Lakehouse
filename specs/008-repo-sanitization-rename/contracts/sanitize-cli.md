# Contract: `tools/sanitize_repo.py`

Common: `--patterns PATH` (default `.sanitize-patterns.local`), `--json`. Results on stdout, errors on stderr. Exit codes: `0` success/PASS, `1` verification failure, `2` usage/config error, `3` refused (unsafe precondition).

| Subcommand | Arguments | Behavior |
|------------|-----------|----------|
| `backup` | `--dest DIR` | Mirror-clone the repo to `DIR` (must be outside the repo); run `git fsck`; compare ref tips. Refuses if `DIR` exists and is non-empty |
| `rewrite` | `--workdir DIR` `--backup DIR` | Requires a verified backup. Clones the repo to `DIR`, runs filter-branch (index/tree/msg filters, `--prune-empty`), then imports branches/tags into the real repo with forced update, deletes `refs/original`, `refs/remotes/*`, expires reflogs, runs `gc --prune=now`. Never pushes |
| `worktree` | `--dry-run` | Applies drop-line, rename and IP rules to tracked + untracked non-ignored text files in the working tree |
| `verify` | `--backup DIR` | Scans tree and all history (contents, commit messages, paths, PDF/PPTX blobs) for `forbidden_literals` and old-name rules; compares counts/order/tip diff to the backup; prints VerificationReport |

Pure-function API (unit-tested): `rewrite_text(text, rules) -> str`, `redact_ips(text, allow, placeholder) -> str`, `drop_lines(text, regexes) -> str`.
