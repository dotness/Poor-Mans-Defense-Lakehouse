# Sensitive literals live in the untracked .sanitize-patterns.local; nothing here names them.
"""Sanitize a repository: purge files, rename branding, redact IPs, rewrite history.

Subcommands: backup | rewrite | worktree | verify  (see specs/008-*/contracts/sanitize-cli.md)
"""

from __future__ import annotations

import argparse
import io
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

DEFAULT_PATTERNS = ".sanitize-patterns.local"
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.]*\d)")


# ---------------------------------------------------------------- pure functions
def rewrite_text(text: str, rules: list) -> str:
    for pattern, repl in rules:
        text = re.sub(pattern, repl, text)
    return text


def redact_ips(text: str, allow: list, placeholder: str) -> str:
    allowed = set(allow)

    def _sub(match: re.Match) -> str:
        raw = match.group(0)
        if raw in allowed:
            return raw
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            return raw
        return placeholder if ip.is_global else raw

    return IPV4.sub(_sub, text)


def drop_lines(text: str, regexes: list) -> str:
    if not regexes:
        return text
    compiled = [re.compile(r) for r in regexes]
    kept = [ln for ln in text.splitlines(keepends=True) if not any(c.search(ln) for c in compiled)]
    return "".join(kept)


def sanitize_text(text: str, cfg: dict) -> str:
    text = drop_lines(text, cfg.get("drop_line_regexes", []))
    text = rewrite_text(text, cfg.get("rename_rules", []))
    ipc = cfg.get("ip_redaction", {})
    if ipc.get("enabled", True):
        text = redact_ips(text, ipc.get("allow", []), ipc.get("placeholder", "[REDACTED-IP]"))
    return text


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        die(f"pattern file not found: {path}", 2)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    for pat in cfg.get("forbidden_literals", []) + cfg.get("drop_line_regexes", []):
        re.compile(pat)
    for pat, _ in cfg.get("rename_rules", []):
        re.compile(pat)
    return cfg


def die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def git(*args, cwd=None, check=True, text=True, input=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=check, text=text, input=input,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sanitize_file(path: Path, cfg: dict) -> bool:
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if b"\0" in raw:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    new = sanitize_text(text, cfg)
    if new != text:
        path.write_bytes(new.encode("utf-8"))
        return True
    return False


# ---------------------------------------------------------------- subcommands
def cmd_backup(args, cfg) -> int:
    dest = Path(args.dest).resolve()
    repo = Path.cwd().resolve()
    if repo in dest.parents or dest == repo:
        die("backup destination must be outside the repository", 3)
    if dest.exists() and any(dest.iterdir()):
        die(f"destination not empty: {dest}", 3)
    git("clone", "--mirror", "--no-local", str(repo), str(dest))
    fsck = git("fsck", "--no-progress", cwd=dest, check=False)
    if fsck.returncode != 0:
        die("backup fsck failed:\n" + fsck.stderr, 1)
    src_heads = git("rev-parse", "main").stdout.strip()
    bak_heads = git("rev-parse", "main", cwd=dest).stdout.strip()
    if src_heads != bak_heads:
        die("backup tip differs from source", 1)
    print(json.dumps({"backup": str(dest), "main": bak_heads, "fsck": "ok"}) if args.json
          else f"backup ok: {dest} (main={bak_heads[:12]})")
    return 0


def cmd_rewrite(args, cfg) -> int:
    repo = Path.cwd().resolve()
    backup = Path(args.backup).resolve()
    if not (backup / "HEAD").exists():
        die("a verified backup is required (run backup first)", 3)
    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    git("clone", "--no-local", str(repo), str(work))
    branches = [b.strip().removeprefix("origin/") for b in
                git("branch", "-r", cwd=work).stdout.splitlines() if "->" not in b]
    for b in branches:
        git("branch", "-f", b, f"origin/{b}", cwd=work, check=False)
    self_path = str(Path(__file__).resolve())
    pat_path = str(Path(args.patterns).resolve())
    purge = " ".join(shlex_quote(p) for p in cfg.get("purge_paths", []))
    env = dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING="1")
    cmd = [
        "git", "filter-branch", "-f", "--prune-empty",
        "--index-filter", f"git rm --cached --ignore-unmatch -r -q -- {purge}",
        "--tree-filter", f"python3 {shlex_quote(self_path)} --patterns {shlex_quote(pat_path)} _treefilter",
        "--msg-filter", f"python3 {shlex_quote(self_path)} --patterns {shlex_quote(pat_path)} _msgfilter",
        "--tag-name-filter", "cat", "--", "--all",
    ]
    r = subprocess.run(cmd, cwd=work, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        die("filter-branch failed:\n" + r.stdout, 1)
    # drop remote-tracking refs and backups in the clone
    for ref in git("for-each-ref", "--format=%(refname)", "refs/remotes", "refs/original", cwd=work).stdout.split():
        git("update-ref", "-d", ref, cwd=work)
    # import into the real repo (never pushes)
    git("fetch", "--update-head-ok", "--no-tags", "-f", str(work), "refs/heads/*:refs/heads/*", cwd=repo)
    git("fetch", "-f", str(work), "refs/tags/*:refs/tags/*", cwd=repo, check=False)
    git("reset", "-q", cwd=repo)
    for ref in git("for-each-ref", "--format=%(refname)", "refs/remotes", "refs/original", "refs/stash", cwd=repo).stdout.split():
        git("update-ref", "-d", ref, cwd=repo)
    for f in ("ORIG_HEAD", "FETCH_HEAD"):
        (repo / ".git" / f).unlink(missing_ok=True)
    git("reflog", "expire", "--expire=now", "--all", cwd=repo)
    git("gc", "--prune=now", "--aggressive", "-q", cwd=repo)
    shutil.rmtree(work, ignore_errors=True)
    print("rewrite complete; history imported locally; nothing pushed")
    return 0


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def cmd_treefilter(args, cfg) -> int:
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            sanitize_file(Path(root) / name, cfg)
    return 0


def cmd_msgfilter(args, cfg) -> int:
    data = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    sys.stdout.buffer.write(rewrite_text(data, cfg.get("rename_rules", [])).encode("utf-8"))
    return 0


def cmd_worktree(args, cfg) -> int:
    files = git("ls-files", "-co", "--exclude-standard", "-z").stdout.split("\0")
    changed = []
    for f in filter(None, files):
        p = Path(f)
        if not p.is_file() or p.is_symlink():
            continue
        if args.dry_run:
            try:
                t = p.read_bytes()
                if b"\0" in t:
                    continue
                s = t.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if sanitize_text(s, cfg) != s:
                changed.append(f)
        elif sanitize_file(p, cfg):
            changed.append(f)
    print(json.dumps({"changed": changed}) if args.json else f"{'would change' if args.dry_run else 'changed'} {len(changed)} files")
    for f in changed:
        if not args.json:
            print("  ", f)
    return 0


def _scan_bytes(data: bytes, regexes: list, label: str, hits: list, ref: str, depth=0):
    for rx in regexes:
        if rx.search(data):
            hits.append({"pattern": rx.pattern.decode(), "location": label, "ref": ref})
    if depth < 2 and data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for n in z.namelist():
                    _scan_bytes(z.read(n), regexes, f"{label}!{n}", hits, ref, depth + 1)
        except zipfile.BadZipFile:
            pass
    if data[:4] == b"%PDF" and shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-", "-"], input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
        for rx in regexes:
            if rx.search(out):
                hits.append({"pattern": rx.pattern.decode(), "location": label + " (pdf text)", "ref": ref})


def cmd_verify(args, cfg) -> int:
    repo = Path.cwd().resolve()
    lits = cfg.get("forbidden_literals", [])
    regexes = [re.compile(p.encode(), re.IGNORECASE) for p in lits]
    excl = set(cfg.get("verify_exclude_paths", [])) | {DEFAULT_PATTERNS}
    hits: list = []
    # 1. working tree
    files = git("ls-files", "-co", "--exclude-standard", "-z").stdout.split("\0")
    for f in filter(None, files):
        if f in excl or not Path(f).is_file():
            continue
        _scan_bytes(Path(f).read_bytes(), regexes, f, hits, "worktree")
        _scan_bytes(f.encode(), regexes, f + " (path)", hits, "worktree")
    # 2. history: messages, paths, blobs
    log = git("log", "--all", "--format=%H%n%an%n%ae%n%B%x00").stdout.encode()
    _scan_bytes(log, regexes, "commit messages", hits, "history")
    objs = git("rev-list", "--objects", "--all").stdout.splitlines()
    shas, paths = [], {}
    for line in objs:
        sha, _, path = line.partition(" ")
        if path:
            paths[sha] = path
            _scan_bytes(path.encode(), regexes, f"{path} (path)", hits, "history")
        shas.append(sha)
    p = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, _ = p.communicate("\n".join(shas).encode() + b"\n")
    pos = 0
    while pos < len(out):
        nl = out.index(b"\n", pos)
        header = out[pos:nl].split()
        pos = nl + 1
        if len(header) < 3:
            continue
        sha, typ, size = header[0].decode(), header[1], int(header[2])
        body = out[pos:pos + size]
        pos += size + 1
        if typ == b"blob":
            name = paths.get(sha, sha)
            if name in excl:
                continue
            _scan_bytes(body, regexes, f"{name}@{sha[:10]}", hits, "history")
    # 3. counts / order / tip diff vs backup
    report = {"hits": hits, "ip_exceptions": []}
    if args.backup:
        bk = Path(args.backup).resolve()
        fmt = "--format=%at %ae"
        before = git("log", "--all", fmt, cwd=bk).stdout.splitlines()
        after = git("log", "--all", fmt).stdout.splitlines()
        it = iter(before)
        order_ok = all(any(x == y for y in it) for x in after)
        report.update(commits_before=len(before), commits_after=len(after),
                      commits_dropped=len(before) - len(after), order_preserved=order_ok)
        tmp = Path(tempfile.mkdtemp(prefix="verify-"))
        try:
            git("clone", "-q", "--no-local", str(bk), str(tmp / "old"))
            git("fetch", "-q", "--no-tags", str(repo), "main:refs/heads/new", cwd=tmp / "old")
            diff = git("diff", "--name-status", "main", "new", cwd=tmp / "old").stdout.splitlines()
            report["tip_diff"] = {"added": [d for d in diff if d.startswith("A")],
                                  "deleted": [d for d in diff if d.startswith("D")],
                                  "modified_count": sum(d.startswith("M") for d in diff)}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    ips = git("grep", "-I", "-h", "-o", "-E", r"([0-9]{1,3}\.){3}[0-9]{1,3}", "--", ".", ":!*.pdf").stdout.split()
    for ip in sorted(set(ips)):
        try:
            if ipaddress.ip_address(ip).is_global:
                report["ip_exceptions"].append(ip)
        except ValueError:
            pass
    ok = not hits and report.get("order_preserved", True)
    report["status"] = "PASS" if ok else "FAIL"
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"status: {report['status']}  hits: {len(hits)}")
        for h in hits[:50]:
            print("  HIT", h["ref"], h["location"], h["pattern"])
        for k in ("commits_before", "commits_after", "commits_dropped", "order_preserved", "tip_diff"):
            if k in report:
                print(f"  {k}: {report[k]}")
        print("  remaining public IPs (tracked text):", report["ip_exceptions"])
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patterns", default=DEFAULT_PATTERNS)
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup"); b.add_argument("--dest", required=True)
    r = sub.add_parser("rewrite"); r.add_argument("--workdir", required=True); r.add_argument("--backup", required=True)
    w = sub.add_parser("worktree"); w.add_argument("--dry-run", action="store_true")
    v = sub.add_parser("verify"); v.add_argument("--backup")
    sub.add_parser("_treefilter")
    sub.add_parser("_msgfilter")
    args = ap.parse_args(argv)
    cfg = load_config(args.patterns)
    return {"backup": cmd_backup, "rewrite": cmd_rewrite, "worktree": cmd_worktree, "verify": cmd_verify,
            "_treefilter": cmd_treefilter, "_msgfilter": cmd_msgfilter}[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
