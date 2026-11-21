import sys
from pathlib import Path

# Ensure paths for CLI execution
root_dir = Path(__file__).resolve().parent.parent.parent
src_dir = root_dir / "src"
for p in (str(root_dir), str(src_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

import click

try:
    from src.cli.commands.status import run_status
except ImportError:
    from cli.commands.status import run_status


@click.group()
@click.option("--json", "global_json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose debug output")
@click.pass_context
def cli(ctx, global_json_mode, verbose):
    """Poor Man's Defense Lakehouse Platform Management CLI"""
    ctx.ensure_object(dict)
    ctx.obj["JSON_MODE"] = global_json_mode
    ctx.obj["VERBOSE"] = verbose


@cli.command("login")
@click.option("--username", "-u", default=None, help="Username for authentication")
@click.option("--password", "-p", default=None, help="Password for authentication")
@click.option("--json", "cmd_json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def login_cmd(ctx, username, password, cmd_json_mode):
    """Authenticate and cache credentials in ~/.artemis/token."""
    json_mode = cmd_json_mode or ctx.obj.get("JSON_MODE", False)
    from src.cli.commands.login import run_login
    exit_code = run_login(username=username, password=password, json_mode=json_mode)
    sys.exit(exit_code)


@cli.command("whoami")
@click.option("--json", "cmd_json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def whoami_cmd(ctx, cmd_json_mode):
    """Check current session status and token expiration."""
    json_mode = cmd_json_mode or ctx.obj.get("JSON_MODE", False)
    from src.cli.commands.login import run_whoami
    exit_code = run_whoami(json_mode=json_mode)
    sys.exit(exit_code)


@cli.command("status")
@click.option("--json", "cmd_json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def status_cmd(ctx, cmd_json_mode):
    """Check health and resource consumption of all platform services."""
    json_mode = cmd_json_mode or ctx.obj.get("JSON_MODE", False)
    exit_code = run_status(json_mode=json_mode)
    sys.exit(exit_code)


@cli.command("query")
@click.option("--sql", required=True, help="DuckDB SQL analytical query string")
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "json", "csv"]))
@click.option("--json", "cmd_json_mode", is_flag=True, default=False, help="Shortcut for --format json")
@click.pass_context
def query_cmd(ctx, sql, output_format, cmd_json_mode):
    """Execute analytical SQL queries via embedded DuckDB over MinIO Parquet."""
    json_mode = cmd_json_mode or ctx.obj.get("JSON_MODE", False)
    fmt = "json" if json_mode else output_format
    try:
        try:
            from src.cli.commands.query import run_query
        except ImportError:
            from cli.commands.query import run_query
        exit_code = run_query(sql=sql, output_format=fmt, json_mode=json_mode)
        sys.exit(exit_code)
    except ImportError:
        click.echo("Error: Analytics service not yet implemented.", err=True)
        sys.exit(1)


@cli.command("ask")
@click.argument("prompt")
@click.option("--cache-ttl", default=None, help="Optional TTL for cached AI response e.g. '30m', '2h'")
@click.option("--json", "cmd_json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ask_cmd(ctx, prompt, cache_ttl, cmd_json_mode):
    """Ask natural language intelligence questions via Google AI Studio + Memgraph."""
    json_mode = cmd_json_mode or ctx.obj.get("JSON_MODE", False)
    try:
        try:
            from src.cli.commands.ask import run_ask
        except ImportError:
            from cli.commands.ask import run_ask
        exit_code = run_ask(prompt=prompt, json_mode=json_mode, cache_ttl=cache_ttl)
        sys.exit(exit_code)
    except ImportError:
        click.echo("Error: AI correlation service not yet implemented.", err=True)
        sys.exit(1)


@cli.group("pipeline")
def pipeline_group():
    """Manage batch processing pipelines."""
    pass


@pipeline_group.command("run")
@click.argument("pipeline_name")
@click.option("--json", "cmd_json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_run_cmd(ctx, pipeline_name, cmd_json_mode):
    """Trigger a batch pipeline execution (e.g. mqtt_to_minio)."""
    json_mode = cmd_json_mode or ctx.obj.get("JSON_MODE", False)
    try:
        try:
            from src.cli.commands.pipeline import run_pipeline
        except ImportError:
            from cli.commands.pipeline import run_pipeline
        exit_code = run_pipeline(name=pipeline_name, json_mode=json_mode)
        sys.exit(exit_code)
    except ImportError:
        click.echo("Error: Pipeline service not yet implemented.", err=True)
        sys.exit(1)


from src.cli.commands.project import project_group
cli.add_command(project_group)

from src.cli.commands.discover import discover_group
cli.add_command(discover_group)


if __name__ == "__main__":
    cli()
