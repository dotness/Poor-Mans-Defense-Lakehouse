# Implementation Plan: Repository Sanitization & Rename

**Branch**: `008-repo-sanitization-rename` | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-repo-sanitization-rename/spec.md`

## Summary

Purge a copyrighted, IP-watermarked PDF and all old-name branding from the working tree and full git history, rename the project to "Poor Man's Defense Lakehouse", strip personal IPs and local paths, and verify the result. Approach: one Python tool (`tools/sanitize_repo.py`) driven by a **local, untracked** pattern file (so committed files contain no sensitive literals). It runs `git filter-branch` (git-filter-repo is not installed; no network) in a throw-away clone after a mirror backup, imports the rewritten refs into the real repo, applies the same text rules to the working tree, and runs an exhaustive verification scan. Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11+ (stdlib only), Git 2.53, POSIX shell

**Primary Dependencies**: `git` (filter-branch), `pdftotext` (scan PDF blobs); no new packages

**Storage**: Git object store; local JSON `.sanitize-patterns.local` (gitignored); backup mirror outside the workspace

**Testing**: pytest (`tests/unit/tools/test_sanitize_repo.py`); verification scan as integration test; `make test` as regression gate

**Target Platform**: Linux workstation

**Project Type**: single project, maintenance tooling under `tools/`

**Performance Goals**: full rewrite (~40 commits, ~400 files) under 5 minutes

**Constraints**: destructive → backup first; forced publish never automated; committed files must not contain the removed literals

**Scale/Scope**: ~37 commits, ~364 tracked files, ~45 files with old-name occurrences

## Constitution Check

| Principle | Status | Note |
|-----------|--------|------|
| I. Library-First & Modular | PASS | Pure functions (`rewrite_text`, `redact_ips`, `drop_lines`), no platform coupling |
| II. Unified CLI | PASS (justified) | One-off maintenance tool, not a platform service; stdout/stderr conventions and `--json` supported |
| III. Test-First | PASS | Unit tests precede implementation; verify scan is the integration test |
| IV. Resource Constraint / Zero-JVM | PASS | No services, no JVM (BFG rejected for this reason) |
| Quality gates | PASS | `make test` stays green (SC-004) |

Re-check after design: no violations.

## Project Structure

```text
specs/008-repo-sanitization-rename/
├── plan.md  research.md  data-model.md  quickstart.md  tasks.md
├── contracts/sanitize-cli.md
└── checklists/requirements.md
tools/sanitize_repo.py                  # backup | rewrite | worktree | verify
tests/unit/tools/test_sanitize_repo.py
.gitignore                              # + pattern file, watermarked papers
README.md                               # + disclaimer, new name
.sanitize-patterns.local                # UNTRACKED sensitive literals + rename rules
```

## Phases

1. Local pattern file. 2. Mirror backup + fsck. 3. Rewrite in clone (index-filter removes PDF; tree-filter text rules; msg-filter rename; `--prune-empty`; tags). 4. Import refs into the real repo; delete `refs/original`, `refs/remotes/*`; expire reflogs; `gc --prune=now`. 5. Working tree: remove PDF, apply rules, README disclaimer, `.gitignore`. 6. Verify (tree + history + binary blobs, count/order, tip diff, `make test`). 7. Manual publish handoff ([quickstart.md](quickstart.md)).

## Complexity Tracking

| Deviation | Why | Rejected alternative |
|-----------|-----|----------------------|
| `git filter-branch` | filter-repo unavailable offline | BFG needs a JVM; squash loses history |
| Local-only pattern file | Published repo must not contain purged literals | Hard-coded patterns would leak them |
