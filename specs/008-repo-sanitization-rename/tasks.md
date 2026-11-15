# Tasks: Repository Sanitization & Rename

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/sanitize-cli.md](contracts/sanitize-cli.md)

## Phase 1: Setup

- [X] T001 Create `.sanitize-patterns.local` (PDF path, watermark/IP/home-path literals, drop-line regexes, ordered rename rules, IP allow-list incl. `8.8.8.8`) in repo root
- [X] T002 Add `.sanitize-patterns.local`, watermarked-paper rules and `*.local` backups to `.gitignore`
- [X] T003 Create `tests/unit/tools/__init__.py` (if missing) and `tools/` import path for tests

## Phase 2: Foundational (blocks all stories)

- [X] T004 [P] Write unit tests for `rewrite_text`, `redact_ips`, `drop_lines` (ordering, idempotence, allow-list, private/doc ranges kept) in `tests/unit/tools/test_sanitize_repo.py`
- [X] T005 Implement pure functions and pattern loading in `tools/sanitize_repo.py`
- [X] T006 Implement `backup` subcommand (mirror clone outside repo, fsck, tip comparison) in `tools/sanitize_repo.py`
- [X] T007 Create the verified backup mirror outside the workspace

## Phase 3: User Story 1 — PDF purged incl. history & IP (P1)

**Independent test**: zero hits for PDF name/hash/watermark/IP across all history.

- [X] T008 [US1] Implement `rewrite` subcommand (clone, index-filter purge, tree-filter text rules, msg-filter, prune-empty, import refs, purge `refs/original`/`refs/remotes`, reflog expire, gc) in `tools/sanitize_repo.py`
- [X] T009 [US1] Run `rewrite` and delete the PDF from the working tree (`git rm`) 
- [X] T010 [US1] Scan remaining PDFs/PPTX/SQLite blobs for watermark/IP; handle hits
- [X] T011 [US1] Replace local references to the PDF with the DOI citation in docs/README (`https://doi.org/10.3917/rdna.820.0093`)

## Phase 4: User Story 2 — Rename everywhere (P1)

**Independent test**: zero old-name variants and zero home-path leaks in tree and history; tests pass.

- [X] T012 [US2] Implement `worktree` subcommand in `tools/sanitize_repo.py`
- [X] T013 [US2] Apply `worktree` rules (docs, specs, constitution, Makefile, pyproject, src, tests, HTML)
- [X] T014 [US2] Sanitize `specs/008-repo-sanitization-rename/` itself so it holds no purged literals
- [X] T015 [US2] Add the legal disclaimer and new title at the top of `README.md`
- [ ] T016 [US2] Run `make test` / pytest to confirm no regression (NOT RUN: .venv interpreter unreachable from sandbox; run make test locally)

## Phase 5: User Story 3 — Verified, safe history (P2)

**Independent test**: `verify` reports PASS; backup restorable.

- [X] T017 [US3] Implement `verify` subcommand (tree, history contents/messages/paths, binary blobs, counts/order, tip diff, `--json`) in `tools/sanitize_repo.py`
- [X] T018 [US3] Run `verify` against the backup and fix any hits
- [X] T019 [US3] Confirm a fresh clone after gc contains no PDF data (SC-007)

## Phase 6: Polish

- [X] T020 Re-run `speckit` checks: update `.specify/memory/constitution.md` title only if still carrying old name (covered by T013) and confirm spec checklist
- [X] T021 Report manual publish steps (rename remote, force push, re-clone); do NOT push

## Dependencies

T001–T003 → T004–T007 → US1 (T008–T011) → US2 (T012–T016) → US3 (T017–T019) → Polish. T017 may be written in parallel with US2 but is run last.

## Parallel Example

T004 (tests) and T006 (backup subcommand) touch different parts and can proceed together after T001.

## Strategy

Deliver US1 first (blocking legal item), then US2, then verify. History rewrite runs once, only after the backup exists (T007).
