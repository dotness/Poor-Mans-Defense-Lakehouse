import os
import sys
import json
import asyncio
from typing import Optional, List, Dict, Any
import click
from tabulate import tabulate

try:
    from src.domains.discovery.facade.discovery import DiscoveryFacade
    from src.cli.commands.login import verify_cli_token
except ImportError:
    from domains.discovery.facade.discovery import DiscoveryFacade
    from cli.commands.login import verify_cli_token

discovery_facade = DiscoveryFacade()


def run_async(coro):
    return asyncio.run(coro)


def get_current_cli_user() -> dict:
    """Retrieves user profile from local token if available, defaulting to admin."""
    try:
        user_info = verify_cli_token()
        if user_info:
            return user_info
    except Exception:
        pass
    return {"sub": "admin", "username": "admin", "roles": ["admin"]}


def output_result(
    data: Any,
    is_json: bool = False,
    empty_msg: str = "No records found.",
) -> None:
    """Standardized output helper supporting human-readable format and JSON mode."""
    if is_json:
        if hasattr(data, "model_dump_json"):
            click.echo(data.model_dump_json(indent=2))
        elif hasattr(data, "model_dump"):
            click.echo(json.dumps(data.model_dump(mode="json"), indent=2))
        else:
            click.echo(json.dumps(data, indent=2, default=str))
    else:
        if not data:
            click.echo(empty_msg)
        else:
            click.echo(str(data))


@click.group("discover")
def discover_group():
    """Knowledge Discovery Graph queries across project workspaces."""
    pass


@discover_group.command("entity")
@click.option("--value", default=None, help="Specific entity value to search across projects")
@click.option("--type", "entity_type", default=None, help="Entity classification type (e.g. Identifier, Person)")
@click.option("--fuzzy", is_flag=True, default=False, help="Enable typo-tolerant fuzzy string matching")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output formatted JSON")
@click.pass_context
def discover_entity_cmd(ctx, value, entity_type, fuzzy, json_mode):
    """Search for shared entities across member projects."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    if not value and not entity_type:
        err_msg = "Error: At least one of --value or --type must be provided."
        if is_json:
            click.echo(json.dumps({"error": err_msg}), err=True)
        else:
            click.echo(err_msg, err=True)
        sys.exit(1)

    try:
        user = get_current_cli_user()
        res = run_async(discovery_facade.find_entities(value=value, entity_type=entity_type, fuzzy=fuzzy, user=user))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            if not res.matches:
                click.echo(f"=== Cross-Project Entity Correlation: {res.query} ===")
                click.echo("No matching entities found in your member projects.")
            else:
                click.echo(f"=== Cross-Project Entity Correlation: {res.query} ===")
                click.echo(f"Matches Found Across {res.total_projects} Project Workspaces:")
                table = [
                    [m.project_id, m.resource_id, m.tier, m.attribute, m.entity_type, m.value, m.match_method, f"{m.confidence:.2f}"]
                    for m in res.matches
                ]
                headers = ["Project", "Resource", "Tier", "Attribute", "Type", "Value", "Method", "Conf"]
                click.echo(tabulate(table, headers=headers, tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error executing entity discovery: {e}", err=True)
        sys.exit(1)


@discover_group.command("lineage")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", required=True, help="Dataset identifier")
@click.option("--depth", default=10, type=int, help="Maximum traversal depth (default: 10)")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output formatted JSON")
@click.pass_context
def discover_lineage_cmd(ctx, project_id, dataset_id, depth, json_mode):
    """Trace data provenance and lineage trees across member projects."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    try:
        user = get_current_cli_user()
        lineage = run_async(discovery_facade.get_lineage(project_id=project_id, dataset_id=dataset_id, depth=depth, user=user))
        if is_json:
            click.echo(lineage.model_dump_json(indent=2))
        else:
            click.echo(f"=== Lineage for {project_id}/{dataset_id} ===")
            if lineage.is_root:
                click.echo("Root resource: No upstream dataset dependencies detected.")
            else:
                table = [[e.source, e.relationship, e.target, e.run_id or "direct"] for e in lineage.edges]
                click.echo(tabulate(table, headers=["Source", "Relation", "Target", "Pipeline Run"], tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error querying lineage: {e}", err=True)
        sys.exit(1)


@discover_group.command("jobs")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--status", default=None, help="Filter by status (pending, running, completed, failed)")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output formatted JSON")
@click.pass_context
def discover_jobs_cmd(ctx, project_id, status, json_mode):
    """View indexing jobs and their status for a project workspace."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    try:
        user = get_current_cli_user()
        jobs = run_async(discovery_facade.list_jobs(project_id=project_id, status=status, user=user))
        if is_json:
            click.echo(json.dumps([j.model_dump(mode="json") for j in jobs], indent=2))
        else:
            click.echo(f"=== Indexing Jobs: {project_id} ===")
            if not jobs:
                click.echo("No indexing jobs found.")
            else:
                table = [
                    [j.job_id[:8] + "...", j.resource_id, j.phase, j.status, j.attempts, j.error or "-"]
                    for j in jobs
                ]
                headers = ["Job ID", "Resource", "Phase", "Status", "Attempts", "Error"]
                click.echo(tabulate(table, headers=headers, tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error listing indexing jobs: {e}", err=True)
        sys.exit(1)


@discover_group.command("reindex")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", default=None, help="Optional dataset to target")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output formatted JSON")
@click.pass_context
def discover_reindex_cmd(ctx, project_id, dataset_id, json_mode):
    """Schedule a re-indexing job for a project or dataset."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    try:
        user = get_current_cli_user()
        job = run_async(discovery_facade.reindex(project_id=project_id, dataset_id=dataset_id, user=user))
        if is_json:
            click.echo(job.model_dump_json(indent=2))
        else:
            click.echo(f"Successfully scheduled re-index job '{job.job_id}' for project '{project_id}'.")
        sys.exit(0)
    except PermissionError as pe:
        if is_json:
            click.echo(json.dumps({"error": str(pe)}), err=True)
        else:
            click.echo(f"Error: {pe}", err=True)
        sys.exit(1)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error scheduling re-index: {e}", err=True)
        sys.exit(1)
