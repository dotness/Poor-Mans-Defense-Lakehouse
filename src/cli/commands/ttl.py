import sys
import json
import asyncio
from typing import Optional
import click
from tabulate import tabulate

from src.domains.retention.facade.retention import RetentionFacade
from src.domains.retention.models.contract.retention import (
    DatasetTTLSetRequestContract,
    ProjectTTLDefaultsRequestContract,
    RetentionHoldRequestContract,
    DatasetRestoreRequestContract,
    CleanupTriggerRequestContract,
)


def _run_async(coro):
    return asyncio.run(coro)


def _get_cli_user() -> dict:
    try:
        from src.cli.commands.login import verify_cli_token
        info = verify_cli_token()
        if info:
            return info
    except Exception:
        pass
    return {"sub": "admin", "username": "admin", "roles": ["admin"]}


@click.group("ttl")
def ttl_group():
    """Manage dataset & query data TTL retention policies, holds, restoration, and auto-cleanup."""
    pass


@ttl_group.command("set")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", required=True, help="Target dataset identifier")
@click.option("--tier", default="BRONZE", help="Medallion tier: BRONZE, SILVER, GOLD")
@click.option("--ttl", "ttl_expression", required=True, help="TTL duration e.g. '30d', '24h', '7d', 'never'")
@click.option(
    "--granularity",
    default="INGESTION_AGE",
    type=click.Choice(["INGESTION_AGE", "TIMESTAMP_COLUMN"], case_sensitive=False),
    help="Expiration granularity: INGESTION_AGE or TIMESTAMP_COLUMN",
)
@click.option("--timestamp-column", default=None, help="Column name for event-timestamp row pruning")
@click.option("--grace-period", "grace_period_expression", default="24h", help="Soft-delete grace period e.g. '24h' or '0h'")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_set_cmd(ctx, project_id, dataset_id, tier, ttl_expression, granularity, timestamp_column, grace_period_expression, json_mode):
    """Set or update the TTL retention policy for a project dataset."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        gran_norm = granularity.upper()
        if timestamp_column and gran_norm == "INGESTION_AGE":
            gran_norm = "TIMESTAMP_COLUMN"
        req = DatasetTTLSetRequestContract(
            tier=tier,
            ttl_expression=ttl_expression,
            granularity=gran_norm,
            timestamp_column=timestamp_column,
            grace_period_expression=grace_period_expression,
        )
        facade = RetentionFacade()
        res = _run_async(facade.set_dataset_ttl(project_id, dataset_id, req, user=_get_cli_user()))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            restored_note = " (auto-restored from SOFT_DELETED)" if res.auto_restored else ""
            click.echo(
                f"Configured TTL for dataset '{res.dataset_id}' ({res.tier}) in project '{res.project_id}': "
                f"{res.effective_ttl_expression} [Granularity: {res.granularity}, Grace: {res.grace_period_expression}, "
                f"Status: {res.lifecycle_status}]{restored_note}"
            )
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error setting dataset TTL: {e}", err=True)
        sys.exit(1)


@ttl_group.command("get")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", required=True, help="Target dataset identifier")
@click.option("--tier", default="BRONZE", help="Medallion tier: BRONZE, SILVER, GOLD")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_get_cmd(ctx, project_id, dataset_id, tier, json_mode):
    """Inspect the effective TTL policy and lifecycle state of a dataset."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        facade = RetentionFacade()
        res = _run_async(facade.get_dataset_ttl(project_id, dataset_id, tier=tier, user=_get_cli_user()))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(f"=== Retention State: {res.project_id}/{res.dataset_id} ({res.tier}) ===")
            click.echo(f"Effective TTL: {res.effective_ttl_expression} (Source: {res.policy_source})")
            click.echo(f"Granularity:   {res.granularity}" + (f" ({res.timestamp_column})" if res.timestamp_column else ""))
            click.echo(f"Grace Period:  {res.grace_period_expression}")
            click.echo(f"Status:        {res.lifecycle_status} | Hold: {res.retention_hold}")
            click.echo(f"Expires At:    {res.expires_at or 'never'}")
            click.echo(f"Partitions:    {res.active_partitions_count} active")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error getting dataset TTL: {e}", err=True)
        sys.exit(1)


@ttl_group.command("clear")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", required=True, help="Target dataset identifier")
@click.option("--tier", default="BRONZE", help="Medallion tier: BRONZE, SILVER, GOLD")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_clear_cmd(ctx, project_id, dataset_id, tier, json_mode):
    """Clear an explicit dataset TTL override and revert to the tier/project default."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        facade = RetentionFacade()
        res = _run_async(facade.clear_dataset_ttl(project_id, dataset_id, tier=tier, user=_get_cli_user()))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(
                f"Cleared explicit TTL override for '{res.dataset_id}' ({res.tier}). "
                f"Now inheriting {res.effective_ttl_expression} from {res.policy_source}."
            )
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error clearing dataset TTL: {e}", err=True)
        sys.exit(1)


@ttl_group.command("set-default")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option(
    "--scope",
    "target_scope",
    default="TIER",
    type=click.Choice(["PROJECT", "TIER", "QUERY_DATA"], case_sensitive=False),
    help="Default scope: PROJECT, TIER, or QUERY_DATA",
)
@click.option("--tier", default=None, help="Tier (BRONZE, SILVER, GOLD) when scope is TIER")
@click.option(
    "--artifact-type",
    "query_artifact_type",
    default=None,
    type=click.Choice(["SQL_RESULT_CACHE", "AI_RAG_CACHE", "MATERIALIZED_EXPORT", "QUERY_HISTORY_LOG"], case_sensitive=False),
    help="Query artifact category when scope is QUERY_DATA",
)
@click.option("--ttl", "ttl_expression", required=True, help="Default TTL expression e.g. '30d', '1h', '7d'")
@click.option("--grace-period", "grace_period_expression", default="24h", help="Default grace period e.g. '24h'")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_set_default_cmd(ctx, project_id, target_scope, tier, query_artifact_type, ttl_expression, grace_period_expression, json_mode):
    """Configure default TTL policies for a project, storage tier, or query data artifact type."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        req = ProjectTTLDefaultsRequestContract(
            target_scope=target_scope.upper(),
            tier=tier.upper() if tier else None,
            query_artifact_type=query_artifact_type.upper() if query_artifact_type else None,
            ttl_expression=ttl_expression,
            grace_period_expression=grace_period_expression,
        )
        facade = RetentionFacade()
        res = _run_async(facade.set_default_ttl(project_id, req, user=_get_cli_user()))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(
                f"Configured default TTL ({res.target_scope}) for project '{project_id}': {res.ttl_expression}"
            )
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error setting default TTL: {e}", err=True)
        sys.exit(1)


@ttl_group.command("hold")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", default=None, help="Dataset identifier (omit for project-wide hold)")
@click.option("--tier", default="BRONZE", help="Medallion tier: BRONZE, SILVER, GOLD")
@click.option("--reason", default="Investigative retention hold", help="Reason for placing hold")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_hold_cmd(ctx, project_id, dataset_id, tier, reason, json_mode):
    """Place a Retention Hold on a dataset or entire project (pausing auto-cleanup)."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        facade = RetentionFacade()
        if dataset_id:
            req = RetentionHoldRequestContract(tier=tier, retention_hold=True, reason=reason)
            res = _run_async(facade.set_dataset_hold(project_id, dataset_id, req, user=_get_cli_user()))
            if is_json:
                click.echo(res.model_dump_json(indent=2))
            else:
                click.echo(f"Placed Retention Hold on dataset '{res.dataset_id}' ({res.tier}) in project '{project_id}'.")
        else:
            res_list = _run_async(facade.set_project_hold(project_id, retention_hold=True, reason=reason, user=_get_cli_user()))
            if is_json:
                click.echo(json.dumps([r.model_dump(mode="json") for r in res_list], indent=2))
            else:
                click.echo(f"Placed Retention Hold across {len(res_list)} datasets in project '{project_id}'.")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error placing retention hold: {e}", err=True)
        sys.exit(1)


@ttl_group.command("unhold")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", default=None, help="Dataset identifier (omit for project-wide unhold)")
@click.option("--tier", default="BRONZE", help="Medallion tier: BRONZE, SILVER, GOLD")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_unhold_cmd(ctx, project_id, dataset_id, tier, json_mode):
    """Release a Retention Hold on a dataset or entire project."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        facade = RetentionFacade()
        if dataset_id:
            req = RetentionHoldRequestContract(tier=tier, retention_hold=False)
            res = _run_async(facade.set_dataset_hold(project_id, dataset_id, req, user=_get_cli_user()))
            if is_json:
                click.echo(res.model_dump_json(indent=2))
            else:
                click.echo(f"Released Retention Hold on dataset '{res.dataset_id}' ({res.tier}) in project '{project_id}'.")
        else:
            res_list = _run_async(facade.set_project_hold(project_id, retention_hold=False, user=_get_cli_user()))
            if is_json:
                click.echo(json.dumps([r.model_dump(mode="json") for r in res_list], indent=2))
            else:
                click.echo(f"Released Retention Hold across {len(res_list)} datasets in project '{project_id}'.")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error releasing retention hold: {e}", err=True)
        sys.exit(1)


@ttl_group.command("restore")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--dataset", "--dataset-id", "dataset_id", required=True, help="Soft-deleted dataset or query export ID")
@click.option("--tier", default="BRONZE", help="Medallion tier: BRONZE, SILVER, GOLD")
@click.option("--ttl", "ttl_expression", default=None, help="Extended TTL duration e.g. '60d' or 'never'")
@click.option("--hold", "retention_hold", is_flag=True, default=False, help="Place a Retention Hold upon restoration")
@click.option("--reason", default="Explicit CLI restore", help="Reason for restoring dataset")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_restore_cmd(ctx, project_id, dataset_id, tier, ttl_expression, retention_hold, reason, json_mode):
    """Explicitly restore a SOFT_DELETED dataset or query export during its grace period."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        req = DatasetRestoreRequestContract(
            tier=tier,
            ttl_expression=ttl_expression,
            retention_hold=retention_hold,
            reason=reason,
        )
        facade = RetentionFacade()
        res = _run_async(facade.restore_dataset(project_id, dataset_id, req, user=_get_cli_user()))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(
                f"Restored '{res.dataset_id}' ({res.tier}) in project '{project_id}' to {res.lifecycle_status} "
                f"(TTL: {res.effective_ttl_expression}, Hold: {res.retention_hold})."
            )
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error restoring dataset: {e}", err=True)
        sys.exit(1)


@ttl_group.command("summary")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_summary_cmd(ctx, project_id, json_mode):
    """Display project-wide retention governance summary and expiring-soon datasets."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        facade = RetentionFacade()
        summary = _run_async(facade.get_project_summary(project_id, user=_get_cli_user()))
        if is_json:
            click.echo(summary.model_dump_json(indent=2))
        else:
            click.echo(f"=== Retention Governance Summary: {summary.project_id} ===")
            click.echo(
                f"Counts: Active={summary.counts['active']} | Expiring<=24h={summary.counts['expiring_within_24h']} | "
                f"Held={summary.counts['held']} | Soft-Deleted={summary.counts['soft_deleted']} | "
                f"Tombstones={summary.counts['purged_tombstones']}"
            )
            if not summary.datasets:
                click.echo("No datasets registered.")
            else:
                rows = [
                    [
                        d["dataset_id"],
                        d["tier"],
                        d["effective_ttl_expression"],
                        d["granularity"],
                        d["lifecycle_status"],
                        "YES" if d["retention_hold"] else "NO",
                        d["expires_at"] or "never",
                    ]
                    for d in summary.datasets
                ]
                click.echo(
                    tabulate(
                        rows,
                        headers=["DATASET", "TIER", "TTL", "GRANULARITY", "STATUS", "HOLD", "EXPIRES_AT"],
                        tablefmt="simple",
                    )
                )
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error retrieving retention summary: {e}", err=True)
        sys.exit(1)


@ttl_group.command("cleanup")
@click.option("--project", "--project-id", "project_id", default=None, help="Optional project ID (omit for global sweep)")
@click.option("--dry-run", is_flag=True, default=False, help="Preview candidate deletions and reclaimable bytes without deleting data")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_cleanup_cmd(ctx, project_id, dry_run, json_mode):
    """Trigger on-demand TTL auto-cleanup or a deterministic --dry-run preview."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        req = CleanupTriggerRequestContract(dry_run=dry_run, include_query_artifacts=True)
        facade = RetentionFacade()
        run = _run_async(facade.trigger_cleanup(project_id=project_id, request=req, user=_get_cli_user()))
        if is_json:
            click.echo(run.model_dump_json(indent=2))
        else:
            mode_str = "DRY-RUN PREVIEW" if dry_run else "LIVE CLEANUP"
            scope_str = f"project '{project_id}'" if project_id else "all projects"
            click.echo(f"=== TTL Cleanup [{mode_str}] ({scope_str}) — Status: {run.status} ===")
            click.echo(
                f"Evaluated: {run.datasets_evaluated} | Soft-Deleted: {run.datasets_soft_deleted} | "
                f"Purged: {run.datasets_purged} | Compacted: {run.partitions_compacted} ({run.rows_pruned} rows) | "
                f"Query Artifacts Purged: {run.query_artifacts_purged}"
            )
            click.echo(
                f"Graph Pruned: {run.graph_elements_pruned} | Tombstones: {run.tombstones_created} | "
                f"Skipped (Held: {run.skipped_held_count}, Locked: {run.skipped_locked_count}) | "
                f"Bytes Reclaimed: {run.bytes_reclaimed:,}"
            )
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error executing TTL cleanup: {e}", err=True)
        sys.exit(1)


@ttl_group.command("history")
@click.option("--project", "--project-id", "project_id", default=None, help="Optional project ID filter")
@click.option("--limit", default=20, type=int, help="Maximum audit runs to return")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ttl_history_cmd(ctx, project_id, limit, json_mode):
    """View historical auto-cleanup and dry-run audit logs."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else False)
    try:
        facade = RetentionFacade()
        runs = _run_async(facade.list_cleanup_runs(project_id=project_id, limit=limit, user=_get_cli_user()))
        if is_json:
            click.echo(json.dumps([r.model_dump(mode="json") for r in runs], indent=2))
        else:
            if not runs:
                click.echo("No cleanup runs recorded.")
            else:
                rows = [
                    [
                        r.run_id[:12],
                        r.trigger_type,
                        r.project_id or "GLOBAL",
                        r.status,
                        r.datasets_soft_deleted,
                        r.datasets_purged,
                        r.query_artifacts_purged,
                        r.bytes_reclaimed,
                        f"{r.duration_ms}ms",
                    ]
                    for r in runs
                ]
                click.echo(
                    tabulate(
                        rows,
                        headers=["RUN_ID", "TRIGGER", "SCOPE", "STATUS", "SOFT_DEL", "PURGED", "Q_ARTS", "BYTES", "TIME"],
                        tablefmt="simple",
                    )
                )
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error listing cleanup history: {e}", err=True)
        sys.exit(1)
