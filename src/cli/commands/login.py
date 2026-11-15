import os
import sys
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional
import click
import jwt

from src.domains.auth.facade.auth import AuthFacade
from src.security.jwt import decode_access_token

TOKEN_DIR = Path.home() / ".artemis"
TOKEN_FILE = TOKEN_DIR / "token"



def save_token(token: str) -> None:
    """Saves the JWT token to ~/.artemis/token with strict 0600 permissions."""
    TOKEN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(token)
    os.chmod(TOKEN_FILE, 0o600)


def get_token() -> Optional[str]:
    """Retrieves the cached JWT token from ~/.artemis/token if present."""
    if not TOKEN_FILE.exists():
        return None
    try:
        return TOKEN_FILE.read_text().strip()
    except Exception:
        return None


def verify_cli_token() -> Optional[dict]:
    """Verifies that the CLI has a valid, unexpired token."""
    token = get_token()
    if not token:
        return None
    try:
        return decode_access_token(token)
    except (jwt.ExpiredSignatureError, jwt.PyJWTError):
        return None


def require_cli_auth(json_mode: bool = False) -> str:
    """Enforces authentication for CLI commands. Returns the valid token or exits."""
    token = get_token()
    if not token:
        if json_mode:
            click.echo('{"error": "Unauthorized", "detail": "Missing token. Run \'artemis login\'."}')
        else:
            click.echo("Error: Authentication required. Run 'artemis login' to log in.", err=True)
        sys.exit(1)

    try:
        decode_access_token(token)
        return token
    except jwt.ExpiredSignatureError:
        if json_mode:
            click.echo('{"error": "Unauthorized", "detail": "Token expired. Run \'artemis login\'."}')
        else:
            click.echo("Error: Authentication token has expired. Run 'artemis login' to refresh.", err=True)
        sys.exit(1)
    except jwt.PyJWTError as e:
        if json_mode:
            click.echo(f'{{"error": "Unauthorized", "detail": "Invalid token: {e}"}}')
        else:
            click.echo(f"Error: Invalid authentication token ({e}). Run 'artemis login'.", err=True)
        sys.exit(1)


def run_login(username: Optional[str] = None, password: Optional[str] = None, json_mode: bool = False) -> int:
    """Executes the login flow, issuing and saving a token."""
    if not username:
        username = click.prompt("Username", default="admin")
    if not password:
        password = click.prompt("Password", hide_input=True, default="admin")

    facade = AuthFacade()
    try:
        token_resp = asyncio.run(facade.authenticate(username, password))
        save_token(token_resp.access_token)
        if json_mode:
            click.echo(f'{{"status": "SUCCESS", "token_type": "{token_resp.token_type}", "expires_in": {token_resp.expires_in}}}')
        else:
            click.echo(f"Successfully logged in as '{username}'. Token saved to {TOKEN_FILE}.")
        return 0
    except PermissionError as e:
        if json_mode:
            click.echo(f'{{"status": "ERROR", "detail": "{str(e)}"}}')
        else:
            click.echo(f"Login failed: {e}", err=True)
        return 1
    except Exception as e:
        if json_mode:
            click.echo(f'{{"status": "ERROR", "detail": "{str(e)}"}}')
        else:
            click.echo(f"Unexpected error during login: {e}", err=True)
        return 1


def run_whoami(json_mode: bool = False) -> int:
    """Displays the currently authenticated user session details."""
    payload = verify_cli_token()
    if not payload:
        if json_mode:
            click.echo('{"authenticated": false, "error": "Not authenticated. Run \'artemis login\'."}')
        else:
            click.echo("Not authenticated. Run 'artemis login' to log in.", err=True)
        return 1

    username = payload.get("username", payload.get("sub", "unknown"))
    roles = payload.get("roles", [])
    scopes = payload.get("scopes", [])
    exp_ts = payload.get("exp")
    exp_str = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat() if exp_ts else "Never"

    if json_mode:
        click.echo(json.dumps({
            "authenticated": True,
            "username": username,
            "roles": roles,
            "scopes": scopes,
            "expires_at": exp_str,
        }))
    else:
        click.echo(f"Authenticated as: {username}")
        click.echo(f"Roles: {', '.join(roles)}")
        click.echo(f"Scopes: {', '.join(scopes)}")
        click.echo(f"Session expires: {exp_str}")
    return 0
