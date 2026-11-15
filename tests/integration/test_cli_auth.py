import os
from pathlib import Path
import pytest
from click.testing import CliRunner
from src.cli.main import cli
from src.cli.commands.login import TOKEN_FILE, TOKEN_DIR


@pytest.fixture
def clean_token_env(tmp_path, monkeypatch):
    """Overrides TOKEN_DIR and TOKEN_FILE to point to an isolated tmp_path."""
    custom_dir = tmp_path / ".artemis"
    custom_file = custom_dir / "token"

    monkeypatch.setattr("src.cli.commands.login.TOKEN_DIR", custom_dir)
    monkeypatch.setattr("src.cli.commands.login.TOKEN_FILE", custom_file)
    monkeypatch.setattr("src.cli.commands.query.require_cli_auth", lambda json_mode=False: None if custom_file.exists() else pytest.fail("Unauthorized"))

    yield {"dir": custom_dir, "file": custom_file}


def test_cli_requires_login(clean_token_env):
    runner = CliRunner()
    result = runner.invoke(cli, ["login", "-u", "admin", "-p", "wrong_pass"])
    assert result.exit_code != 0
    assert not clean_token_env["file"].exists()


def test_cli_login_flow_and_authenticated_execution(clean_token_env):
    runner = CliRunner()
    # 1. Login with correct admin credentials
    login_result = runner.invoke(cli, ["login", "-u", "admin", "-p", "admin"])
    assert login_result.exit_code == 0
    assert clean_token_env["file"].exists()

    # Verify file permissions are 0600
    file_mode = oct(clean_token_env["file"].stat().st_mode & 0o777)
    assert file_mode == "0o600"

    # 2. Query with analytical command
    query_result = runner.invoke(cli, ["query", "--sql", "SELECT 1 as test_col", "--json"])
    assert query_result.exit_code == 0
