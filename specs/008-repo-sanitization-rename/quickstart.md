# Quickstart: Validate Sanitization

Prerequisites: git, python3, pdftotext; `.sanitize-patterns.local` present (untracked).

```sh
python3 tools/sanitize_repo.py backup  --dest ../dl-backup.git
python3 tools/sanitize_repo.py rewrite --workdir /tmp/dl-rewrite --backup ../dl-backup.git
python3 tools/sanitize_repo.py worktree
python3 tools/sanitize_repo.py verify  --backup ../dl-backup.git
make test
```

Expected: `verify` prints `PASS` with zero hits, commit order preserved, tip diff limited to purged paths and text-rule changes; `make test` green.

Manual spot checks:
- `git log --all --name-only | grep -ci cairn` → `0`
- `git rev-list --all | wc -l` equals the backup count minus dropped empty commits.

## Publishing (manual, after your review)
1. Rename the GitHub repository to `poor-mans-defense-lakehouse` (or delete and recreate it to drop cached old objects).
2. `git remote set-url origin git@github.com:<owner>/poor-mans-defense-lakehouse.git`
3. `git push --force --all origin && git push --force --tags origin`
4. Ask GitHub support to garbage-collect if the old repository remains reachable; re-clone all other copies.
5. Optionally rename the local folder.
