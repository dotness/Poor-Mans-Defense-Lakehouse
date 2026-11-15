import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from sanitize_repo import drop_lines, redact_ips, rewrite_text  # noqa: E402

PUB = "93.184.216." + "34"  # built at runtime so no public IP literal is committed
RULES = [
    [r"file:///home/dev/Projects/Old-Name/", ""],
    [r"/home/dev/", "/home/user/"],
    [r"Old-Name", "new-name"],
    [r"Old[- ]Name", "New Name"],
]


def test_rewrite_text_applies_rules_in_order():
    text = "see file:///home/dev/Projects/Old-Name/specs/a.md and Old Name at /home/dev/x"
    out = rewrite_text(text, RULES)
    assert out == "see specs/a.md and New Name at /home/user/x"


def test_rewrite_text_is_idempotent():
    text = "Old-Name / Old Name / /home/dev/x"
    once = rewrite_text(text, RULES)
    assert rewrite_text(once, RULES) == once


def test_redact_ips_redacts_public_only():
    text = f"pub {PUB} priv 10.0.0.1 lo 127.0.0.1 doc 203.0.113.5 any 0.0.0.0 lan 192.168.1.1"
    out = redact_ips(text, allow=[], placeholder="[REDACTED-IP]")
    assert PUB not in out
    assert out.count("[REDACTED-IP]") == 1
    for kept in ("10.0.0.1", "127.0.0.1", "203.0.113.5", "0.0.0.0", "192.168.1.1"):
        assert kept in out


def test_redact_ips_honours_allow_list():
    assert redact_ips("dns 8.8.8.8", allow=["8.8.8.8"], placeholder="X") == "dns 8.8.8.8"


def test_redact_ips_ignores_non_ip_numbers():
    text = "version 1.2.3 and 999.1.1.1 and 12.34.56"
    assert redact_ips(text, allow=[], placeholder="X") == text


def test_drop_lines_removes_matching_lines_only():
    text = "keep\nDownloaded on x (IP: 10.9.9.9)\nkeep2\n"
    assert drop_lines(text, [r"Downloaded on .*IP:"]) == "keep\nkeep2\n"
