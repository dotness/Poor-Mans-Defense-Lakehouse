# Feature Specification: Repository Sanitization & Rename to "Poor Man's Defense Lakehouse"

**Feature Branch**: `008-repo-sanitization-rename`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "Address discovered pre-publication issues: 1. Remove the questioned (copyrighted, IP-watermarked) PDF. 2. Rename the project to Poor Mans Defense Lakehouse. 3. Alter and rewrite git history so that it always appeared as such, and the PDF is not searchable via git history."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Copyrighted PDF fully purged, including history (Priority: P1)

The maintainer wants the third-party copyrighted paper (the Cairn.info download of the 2019 Emmanuel & Robin ARTEMIS paper, which carries a download watermark with a personal IP address) to be absent from the working tree AND unrecoverable from the repository's history, so that publishing the repository exposes neither the copyrighted work nor the watermark.

**Why this priority**: This is the only legal-exposure and privacy-leak item; it blocks making the repository public.

**Independent Test**: Search the full history of all branches, tags and stashes for the file name, its content hash, and the watermark strings (IP address, "Téléchargé le"). Zero hits expected.

**Acceptance Scenarios**:

1. **Given** the sanitized repository, **When** anyone lists every file ever committed on any ref, **Then** the PDF path never appears.
2. **Given** the sanitized repository, **When** anyone searches history contents for the watermark text or the IP address, **Then** nothing is found.
3. **Given** a fresh clone of the sanitized repository, **When** unreachable objects are garbage-collected, **Then** the PDF's data is not present in the clone's object store.
4. **Given** documentation that referenced the PDF as a source, **When** the PDF is removed, **Then** the reference points to the public DOI citation (`https://doi.org/10.3917/rdna.820.0093`) instead of a local file.

---

### User Story 2 - Project consistently named "Poor Man's Defense Lakehouse" (Priority: P1)

The maintainer wants the project to carry the new name everywhere (documentation, titles, descriptions, specs, constitution, scripts, container/stack labels), and wants history to read as if that name was always used, so no old-name branding remains discoverable.

**Why this priority**: The old name implies affiliation with a government program; the new name removes the trademark/affiliation risk.

**Independent Test**: Case-insensitive search of the working tree and of full history (commit messages and file contents) for the previous project name and its spelling variants (listed in the local pattern file, not in this spec) returns zero hits, except in explicitly allowed contexts (see Assumptions).

**Acceptance Scenarios**:

1. **Given** the sanitized repository, **When** the README and top-level docs are opened, **Then** the title and descriptions show "Poor Man's Defense Lakehouse".
2. **Given** the sanitized repository, **When** old-name variants are searched across all commit messages and all historical file contents, **Then** none are found.
3. **Given** the rename, **When** the platform's tests and quickstart scenarios are run, **Then** they pass exactly as before the rename (no functional regression).
4. **Given** absolute local paths embedded in spec files (e.g., `file:///home/<user>/Projects/poor-mans-defense-lakehouse/...`), **When** sanitization completes, **Then** they are replaced with relative paths in the tree and in history.

---

### User Story 3 - Rewritten, verifiable, safe history (Priority: P2)

The maintainer wants the rewrite to be performed safely: backed up first, executed once across all refs, verified, and then published without leaving stale copies on remotes or in local caches.

**Why this priority**: History rewriting is destructive; a failed or partial rewrite could lose work or leave the sensitive data reachable.

**Independent Test**: Compare pre- and post-rewrite repositories: commit count, order, dates and the tip file tree (aside from intended removals and renames) match; a backup exists and can be restored.

**Acceptance Scenarios**:

1. **Given** the original repository, **When** the rewrite is about to start, **Then** a complete backup (mirror clone outside the workspace) exists.
2. **Given** the rewrite, **When** it completes, **Then** every branch and tag is rewritten consistently and the commit sequence is preserved, except for commits that become empty and are dropped.
3. **Given** the rewrite, **When** the tip tree is diffed against the pre-rewrite tip, **Then** the only differences are the PDF removal, the rename and path sanitization.
4. **Given** a remote copy exists, **When** the sanitized history is published, **Then** it replaces the old history entirely and stale refs are cleaned.

---

### Edge Cases

- The PDF was added, modified, deleted, or renamed in different commits (or duplicated under other names): all path and content-hash variants must be purged.
- The PDF's text was extracted into other files (e.g., a text dump): such derivatives containing the watermark must also be reviewed and purged.
- Other research files (research report PDF, presentation) are out of scope unless they contain the watermark/IP; they are flagged for separate review.
- IP addresses in third-party public data (e.g., test fixtures, vendor docs) that are not the maintainer's: reviewed individually; redacted if public and non-documentation, otherwise listed as justified exceptions.
- Commits that touch only the removed PDF become empty: they are dropped, not left blank.
- Binary files, the SQLite database or generated artifacts containing the old name must be checked and rewritten or regenerated.
- Existing clones, forks, caches or open pull requests of the old history cannot be recalled; they must be re-cloned/discarded.
- Commit signatures become invalid after the rewrite (if any existed).
- Author identity in commits is unchanged by this feature (see Assumptions).
- Renaming the remote repository or local folder is a manual step documented for the maintainer.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The copyrighted PDF MUST be removed from the working tree.
- **FR-002**: The PDF MUST be removed from every commit on every branch and tag, by path and by content, so it is not discoverable through history browsing or search.
- **FR-003**: Any file content in tree or history carrying the download watermark (personal IP address, download timestamp) MUST be removed or redacted.
- **FR-003a**: The maintainer's personal public IP address (listed only in the local pattern file) and any other non-documentation, non-private IP address found in the tree or history (including derived text dumps such as `pdf_text_clean.txt` and `infra_matches.txt`) MUST be stripped, replaced by a neutral placeholder (e.g., `[REDACTED-IP]`), in the working tree and in all historic file contents and commit messages. Reserved/documentation and private-range addresses used by the platform's own configuration (e.g., `127.0.0.1`, `10.x`, `192.168.x`, `172.16-31.x`, `192.0.2.x`) are preserved.
- **FR-003b**: Download-watermark lines (e.g., "Téléchargé le ... sur https://shs.cairn.info (IP: ...)") MUST be removed entirely, not only their IP part.
- **FR-004**: Documentation referencing the PDF MUST cite the public DOI instead of a local file.
- **FR-005**: The project name MUST be changed to "Poor Man's Defense Lakehouse" in all documentation, specs, constitution, scripts, configuration labels and metadata in the working tree.
- **FR-006**: The old project name, in all spelling variants, MUST be rewritten to the new name in historic file contents and commit messages, so history reads as if the new name was always used.
- **FR-007**: Absolute local filesystem paths revealing the maintainer's username MUST be replaced by relative paths in the tree and in history.
- **FR-008**: A full backup of the repository MUST be created outside the workspace before any history rewrite.
- **FR-009**: The rewrite MUST preserve commit order, timestamps and messages (apart from rename substitutions) and drop only commits that become empty.
- **FR-010**: A verification step MUST demonstrate: no PDF path/hash, no watermark text, no old-name variants, no local-path leaks in tree or full history; and that the tip tree differs from the original only by the intended changes.
- **FR-011**: The system MUST still pass its existing automated tests and quickstart scenarios after the rename.
- **FR-012**: A legal disclaimer (independent, non-affiliated educational prototype; no endorsement by the French Ministry of Armed Forces, DGA, ATHEA, Thales, Atos or affiliates) MUST be present at the top of the README.
- **FR-013**: Ignore rules MUST prevent third-party papers/PDFs with download watermarks from being accidentally re-committed.
- **FR-014**: Instructions MUST be provided for the maintainer to publish the rewritten history (forced replacement), purge remote caches, rename the remote repository, and re-clone elsewhere.

### Key Entities

- **Sensitive Artifact**: A file or text fragment that must not be publicly reachable (copyrighted PDF, watermark text, personal IP, local absolute paths). Attributes: path, content hash, location (tree/history).
- **Rename Mapping**: The set of old-name variants and the new-name replacement for each, applied consistently to contents and messages.
- **History Backup**: A complete pre-rewrite mirror used for rollback and before/after comparison.
- **Verification Report**: Record of searches run and results (zero hits) plus the tip-tree diff summary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 occurrences of the PDF's file name, content hash or watermark text across all refs in full history after the rewrite.
- **SC-002**: 0 occurrences of any old-name variant in the working tree and in all commit messages and historic contents (except allowed contexts in Assumptions).
- **SC-002a**: 0 occurrences of the maintainer's personal IP, and 0 public (non-reserved, non-private) IPv4/IPv6 addresses, in the working tree and across all history, commit messages included; a scan report lists any remaining addresses with justification (preserved reserved/private ranges only).
- **SC-003**: 0 occurrences of the maintainer's local home path in the tree and in history.
- **SC-004**: 100% of the automated tests and quickstart scenarios that passed before the change still pass after it.
- **SC-005**: Commit count after the rewrite equals the original count minus only commits that became empty, with relative order preserved.
- **SC-006**: A restorable backup of the original repository exists before the rewrite, and restoring it reproduces the original tip exactly.
- **SC-007**: A fresh clone of the published repository has no recoverable PDF data after garbage collection.

## Assumptions

- The repository is currently private with no public forks; rewriting shared history is acceptable, and the maintainer will force-publish it.
- Names of real French programs (ARTEMIS.IA, ATHEA, etc.) used as subjects of public research references are legitimate descriptive references and are **not** rewritten; only the project's own name is renamed.
- The new display name is "Poor Man's Defense Lakehouse"; its slug form is `poor-mans-defense-lakehouse`. Renaming the `artemis` CLI command is **out of scope** to avoid functional regression; it is a follow-up item.
- Author name and personal email in commit metadata are out of scope (the maintainer may choose to rewrite them separately).
- Other research documents (research-report PDF, presentation) are out of scope, except for a watermark/IP check.
- Adding an open-source license file is out of scope (separate item).
- The rewrite uses a dedicated history-rewriting tool, chosen at planning time, with a backup taken first; the destructive forced publish happens only after the maintainer's explicit confirmation.
- Old clones and caches outside the maintainer's control cannot be recalled.
