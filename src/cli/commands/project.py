import os
import sys
import json
import asyncio
import click
from pathlib import Path
from tabulate import tabulate

from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract

project_facade = ProjectFacade()


def run_async(coro):
    return asyncio.run(coro)


@click.group("project")
def project_group():
    """Manage isolated project workspaces and data ingestion."""
    pass


@project_group.command("create")
@click.option("--id", "--project-id", "--project", "project_id", required=True, help="Unique project slug identifier (e.g. cyber-defense)")
@click.option("--name", required=True, help="Human-readable project name")
@click.option("--desc", "--description", default=None, help="Optional description of the project")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def create_cmd(ctx, project_id, name, desc, json_mode):
    """Create a new project workspace."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        from src.cli.commands.login import verify_cli_token
        user_info = verify_cli_token()
        creator = (user_info.get("sub") or user_info.get("username")) if user_info else "admin"
        contract = ProjectCreateContract(project_id=project_id, name=name, description=desc)
        res = run_async(project_facade.create_project(contract, creator_user_id=creator))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(f"Successfully created project '{res.name}' (ID: {res.project_id}).")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error creating project: {e}", err=True)
        sys.exit(1)


@project_group.command("list")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def list_cmd(ctx, json_mode):
    """List all project workspaces."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        projects = run_async(project_facade.list_projects())
        if is_json:
            click.echo(json.dumps([p.model_dump(mode="json") for p in projects], indent=2))
        else:
            if not projects:
                click.echo("No projects found.")
                sys.exit(0)
            rows = [
                [p.project_id, p.name, p.status, p.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(p.created_at, "strftime") else str(p.created_at)]
                for p in projects
            ]
            click.echo(tabulate(rows, headers=["PROJECT_ID", "NAME", "STATUS", "CREATED_AT"], tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error listing projects: {e}", err=True)
        sys.exit(1)


@project_group.command("info")
@click.option("--id", "project_id", required=True, help="Project identifier")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def info_cmd(ctx, project_id, json_mode):
    """View project details and registered datasets."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        p = run_async(project_facade.get_project(project_id))
        if not p:
            if is_json:
                click.echo(json.dumps({"error": f"Project '{project_id}' not found."}), err=True)
            else:
                click.echo(f"Project '{project_id}' not found.", err=True)
            sys.exit(1)

        datasets = run_async(project_facade.list_datasets(project_id))
        if is_json:
            data = p.model_dump(mode="json")
            data["datasets"] = [d.model_dump(mode="json") for d in datasets]
            click.echo(json.dumps(data, indent=2))
        else:
            click.echo(f"Project: {p.name} ({p.project_id})")
            click.echo(f"Status: {p.status} | Created: {p.created_at}")
            if p.description:
                click.echo(f"Description: {p.description}")
            click.echo("\nRegistered Datasets:")
            if not datasets:
                click.echo("  (No datasets ingested yet)")
            else:
                rows = [[d.dataset_id, d.tier, d.dataset_type, d.record_count, d.storage_uri] for d in datasets]
                click.echo(tabulate(rows, headers=["DATASET", "TIER", "TYPE", "RECORDS", "URI"], tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error getting project info: {e}", err=True)
        sys.exit(1)


@project_group.command("delete")
@click.option("--id", "--project-id", "--project", "project_id", required=True, help="Project identifier")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def delete_cmd(ctx, project_id, json_mode):
    """Delete a project workspace."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        success = run_async(project_facade.delete_project(project_id))
        if not success:
            if is_json:
                click.echo(json.dumps({"error": f"Project '{project_id}' not found."}), err=True)
            else:
                click.echo(f"Project '{project_id}' not found.", err=True)
            sys.exit(1)
        if is_json:
            click.echo(json.dumps({"status": "DELETED", "project_id": project_id}))
        else:
            click.echo(f"Deleted project '{project_id}'.")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error deleting project: {e}", err=True)
        sys.exit(1)


@project_group.command("ingest")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--dataset", "dataset_name", required=True, help="Dataset name/identifier (e.g. raw_logs)")
@click.option("--tier", default="bronze", help="Medallion tier: bronze, silver, gold")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to input data file (CSV, JSON, Parquet)")
@click.option("--ttl", "ttl_expression", default=None, help="Optional dataset TTL duration e.g. '30d', '7d', 'never'")
@click.option("--timestamp-column", default=None, help="Optional event timestamp column for row-level TTL")
@click.option("--overwrite", is_flag=True, default=False, help="Overwrite existing partitions and reset ingestion TTL clock")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ingest_cmd(ctx, project_id, dataset_name, tier, file_path, ttl_expression, timestamp_column, overwrite, json_mode):
    """Ingest tabular data into a project tier partition."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        path = Path(file_path)
        with open(path, "rb") as f:
            data_bytes = f.read()

        res = run_async(
            project_facade.ingest_tabular(
                project_id=project_id,
                dataset_name=dataset_name,
                data_bytes=data_bytes,
                filename=path.name,
                tier=tier,
                ttl_expression=ttl_expression,
                timestamp_column=timestamp_column,
                overwrite=overwrite,
            )
        )
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(f"Successfully ingested {res.records_ingested} records into {res.project_id} (tier: {res.tier}, dataset: {res.dataset_name}).")
            click.echo(f"Storage URI: {res.storage_uri}")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error ingesting tabular data: {e}", err=True)
        sys.exit(1)


@project_group.command("ingest-graph")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to JSON file with nodes and edges")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def ingest_graph_cmd(ctx, project_id, file_path, json_mode):
    """Ingest graph entities and relationships into project knowledge graph."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        nodes = payload.get("nodes", [])
        edges = payload.get("edges", [])

        res = run_async(
            project_facade.ingest_graph(
                project_id=project_id,
                nodes=nodes,
                edges=edges,
            )
        )
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(f"Successfully ingested graph into {res.project_id}: {res.nodes_imported} nodes, {res.edges_imported} edges.")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error ingesting graph: {e}", err=True)
        sys.exit(1)


# -------------------------------------------------------------
# Pipeline Subcommands: artemis project pipeline ...
# -------------------------------------------------------------

from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineUpdateContract,
    PipelineRunTriggerContract,
)

pipeline_facade = PipelineFacade()


@project_group.group("pipeline")
def project_pipeline_group():
    """Manage shareable data processing pipelines and transformation scripts."""
    pass


@project_pipeline_group.command("create")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--name", required=True, help="Pipeline name")
@click.option("--desc", "--description", default=None, help="Pipeline description")
@click.option("--stage", default="BRONZE_TO_SILVER", help="Stage: INGESTION, BRONZE_TO_SILVER, SILVER_TO_GOLD, CUSTOM")
@click.option("--script", "script_path", required=True, type=click.Path(exists=True), help="Path to Python script file")
@click.option("--image", default="artemis-pipeline-runner:latest", help="Docker runner container image")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_create_cmd(ctx, project_id, name, desc, stage, script_path, image, json_mode):
    """Create and upload a shareable pipeline with a Python transformation script."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        script_content = Path(script_path).read_text(encoding="utf-8")
        contract = PipelineCreateContract(
            name=name,
            description=desc,
            stage=stage,
            script_content=script_content,
            docker_image=image,
        )
        res = run_async(pipeline_facade.create_project_pipeline(project_id, contract))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(f"Created pipeline '{res.name}' (ID: {res.pipeline_id}) for project {res.project_id}.")
            click.echo(f"Stage: {res.stage} | Version: {res.version}")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error creating pipeline: {e}", err=True)
        sys.exit(1)


@project_pipeline_group.command("list")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_list_cmd(ctx, project_id, json_mode):
    """List all registered pipelines in a project."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        pipes = run_async(pipeline_facade.list_project_pipelines(project_id))
        if is_json:
            click.echo(json.dumps([p.model_dump(mode="json") for p in pipes], indent=2))
        else:
            if not pipes:
                click.echo(f"No pipelines registered for project '{project_id}'.")
                sys.exit(0)
            rows = [[p.pipeline_id, p.name, p.stage, p.version, p.docker_image, p.created_by] for p in pipes]
            click.echo(tabulate(rows, headers=["PIPELINE_ID", "NAME", "STAGE", "VER", "IMAGE", "AUTHOR"], tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error listing pipelines: {e}", err=True)
        sys.exit(1)


@project_pipeline_group.command("get")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--id", "--pipeline-id", "--name", "identifier", required=True, help="Pipeline ID or name")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_get_cmd(ctx, project_id, identifier, json_mode):
    """Inspect pipeline definition and metadata."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        p = run_async(pipeline_facade.get_project_pipeline(project_id, identifier))
        if not p:
            if is_json:
                click.echo(json.dumps({"error": f"Pipeline '{identifier}' not found."}), err=True)
            else:
                click.echo(f"Pipeline '{identifier}' not found in project '{project_id}'.", err=True)
            sys.exit(1)
        if is_json:
            click.echo(p.model_dump_json(indent=2))
        else:
            click.echo(f"Pipeline: {p.name} ({p.pipeline_id})")
            click.echo(f"Stage: {p.stage} | Version: {p.version} | Author: {p.created_by}")
            click.echo(f"Docker Image: {p.docker_image}")
            if p.description:
                click.echo(f"Description: {p.description}")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error getting pipeline: {e}", err=True)
        sys.exit(1)


@project_pipeline_group.command("update")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--id", "--pipeline-id", "--name", "identifier", required=True, help="Pipeline ID or name")
@click.option("--script", "script_path", default=None, type=click.Path(exists=True), help="Path to new Python script")
@click.option("--name", default=None, help="Updated pipeline name")
@click.option("--stage", default=None, help="Updated stage")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_update_cmd(ctx, project_id, identifier, script_path, name, stage, json_mode):
    """Update pipeline configuration or script with atomic version increment."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        script_content = Path(script_path).read_text(encoding="utf-8") if script_path else None
        contract = PipelineUpdateContract(
            name=name,
            stage=stage,
            script_content=script_content,
        )
        res = run_async(pipeline_facade.update_project_pipeline(project_id, identifier, contract))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            click.echo(f"Updated pipeline '{res.name}' to version {res.version}.")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error updating pipeline: {e}", err=True)
        sys.exit(1)


@project_pipeline_group.command("delete")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--id", "--pipeline-id", "--name", "identifier", required=True, help="Pipeline ID or name")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_delete_cmd(ctx, project_id, identifier, json_mode):
    """Delete a pipeline from a project."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        success = run_async(pipeline_facade.delete_project_pipeline(project_id, identifier))
        if not success:
            if is_json:
                click.echo(json.dumps({"error": f"Pipeline '{identifier}' not found."}), err=True)
            else:
                click.echo(f"Pipeline '{identifier}' not found.", err=True)
            sys.exit(1)
        if is_json:
            click.echo(json.dumps({"status": "DELETED", "pipeline_id": identifier}))
        else:
            click.echo(f"Deleted pipeline '{identifier}' from project '{project_id}'.")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error deleting pipeline: {e}", err=True)
        sys.exit(1)


@project_pipeline_group.command("run")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--id", "--pipeline", "--pipeline-id", "--name", "identifier", required=True, help="Pipeline ID or name")
@click.option("--input-dataset", "input_datasets", multiple=True, help="Source dataset names (can specify multiple times)")
@click.option("--target-dataset", required=True, help="Target destination dataset identifier")
@click.option("--target-tier", default="silver", help="Target medallion tier: bronze, silver, gold")
@click.option("--timeout", default=300, type=int, help="Execution timeout in seconds")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_run_cmd(ctx, project_id, identifier, input_datasets, target_dataset, target_tier, timeout, json_mode):
    """Trigger an ephemeral Docker-sandboxed execution of a project pipeline."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        contract = PipelineRunTriggerContract(
            input_datasets=list(input_datasets),
            target_dataset=target_dataset,
            target_tier=target_tier,
            timeout_seconds=timeout,
        )
        res = run_async(pipeline_facade.trigger_pipeline_run(project_id, identifier, contract))
        if is_json:
            click.echo(res.model_dump_json(indent=2))
        else:
            if res.status == "SUCCESS":
                click.echo("Pipeline run completed successfully:")
                click.echo(f"Status: {res.status}")
                click.echo(f"Run ID: {res.run_id}")
                click.echo(f"Records Processed: {res.records_processed}")
                click.echo(f"Execution Time: {res.duration_ms}ms (Exit Code: {res.exit_code})")
                click.echo(f"Target Dataset: {res.target_dataset} (Tier: {res.target_tier})")
            else:
                click.echo(f"Pipeline run {res.status} (Exit Code: {res.exit_code}):", err=True)
                if res.logs:
                    click.echo(f"Logs:\n{res.logs}", err=True)
                sys.exit(1)
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error triggering pipeline run: {e}", err=True)
        sys.exit(1)


@project_pipeline_group.command("runs")
@click.option("--project", "--project-id", "project_id", required=True, help="Project identifier")
@click.option("--id", "--pipeline-id", "--name", "pipeline_id", default=None, help="Optional pipeline ID filter")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def pipeline_runs_cmd(ctx, project_id, pipeline_id, json_mode):
    """View historical execution runs for project pipelines."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        runs = run_async(pipeline_facade.list_pipeline_runs(project_id, pipeline_id))
        if is_json:
            click.echo(json.dumps([r.model_dump(mode="json") for r in runs], indent=2))
        else:
            if not runs:
                click.echo(f"No execution runs found for project '{project_id}'.")
                sys.exit(0)
            rows = [
                [
                    r.run_id[:12],
                    r.pipeline_id[:12],
                    r.status,
                    r.target_dataset,
                    r.records_processed,
                    f"{r.duration_ms}ms",
                    r.exit_code,
                    r.started_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(r.started_at, "strftime") else str(r.started_at),
                ]
                for r in runs
            ]
            click.echo(tabulate(rows, headers=["RUN_ID", "PIPE_ID", "STATUS", "TARGET", "RECORDS", "TIME", "EXIT", "STARTED"], tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error getting pipeline runs: {e}", err=True)
        sys.exit(1)


# -------------------------------------------------------------
# Scoped Query: artemis project query ...
# -------------------------------------------------------------

@project_group.command("query")
@click.option("--project", "--project-id", "project_id", required=True, help="Target project identifier")
@click.option("--sql", required=True, help="DuckDB SQL analytical query string")
@click.option("--cache-ttl", default=None, help="Optional TTL for cached SQL query result e.g. '15m', '2h'")
@click.option("--export-dataset", default=None, help="Optional dataset identifier to materialize query output")
@click.option("--export-ttl", default=None, help="Optional TTL for materialized query export e.g. '7d'")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def project_query_cmd(ctx, project_id, sql, cache_ttl, export_dataset, export_ttl, json_mode):
    """Execute analytical DuckDB SQL queries scoped to project S3 partitions."""
    is_json = json_mode or ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode
    try:
        from src.domains.analytics.operations.project_query import ProjectQueryExecutor
        executor = ProjectQueryExecutor()
        result = executor.execute_scoped_query(
            project_id,
            sql,
            cache_ttl=cache_ttl,
            export_dataset=export_dataset,
            export_ttl=export_ttl,
        )

        if is_json:
            click.echo(json.dumps(result, indent=2))
        else:
            if result.get("message"):
                click.echo(result["message"])
            elif not result["rows"]:
                click.echo(f"Query returned 0 records ({result['duration_ms']}ms).")
            else:
                click.echo(tabulate(result["rows"], headers=result["columns"], tablefmt="simple"))
                click.echo(f"\n({result['row_count']} rows in {result['duration_ms']}ms)")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error executing project query: {e}", err=True)
        sys.exit(1)


@project_group.command("discover")
@click.argument("project_id")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def discover_cmd(ctx, project_id, json_mode):
    """Knowledge summary of a project workspace."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    try:
        from src.domains.discovery.facade.discovery import DiscoveryFacade
        from src.cli.commands.login import verify_cli_token

        user_info = None
        try:
            user_info = verify_cli_token()
        except Exception:
            pass
        user = user_info or {"sub": "admin", "username": "admin", "roles": ["admin"]}

        discovery_facade = DiscoveryFacade()
        summary = run_async(discovery_facade.get_workspace_knowledge(project_id, user=user))
        if summary is None:
            err_msg = f"Project '{project_id}' not found or access denied."
            if is_json:
                click.echo(json.dumps({"error": err_msg}), err=True)
            else:
                click.echo(err_msg, err=True)
            sys.exit(1)

        if is_json:
            click.echo(summary.model_dump_json(indent=2))
        else:
            click.echo(f"=== Knowledge Summary: {summary.project_id} ===")
            click.echo(f"Enrichment: {summary.enrichment_status}")
            if not summary.resources:
                click.echo("No indexed resources.")
            else:
                click.echo(f"Data Resources ({len(summary.resources)}):")
                for r in summary.resources:
                    row_str = f"{r.record_count:,} rows" if r.record_count is not None else "0 rows"
                    click.echo(f"  - {r.resource_id} ({r.tier}, {r.format}, {row_str})")
                    for a in r.attributes:
                        line = f"      {a.name} {a.physical_type}"
                        if a.taxonomy:
                            conf_str = f" ({a.confidence:.2f})" if a.confidence else ""
                            line += f" -> {a.taxonomy}{conf_str}"
                        click.echo(line)
                    if r.entity_counts:
                        ent_parts = [f"{cnt:,} {etype}" for etype, cnt in r.entity_counts.items()]
                        click.echo(f"      Entities: {', '.join(ent_parts)}")
        sys.exit(0)
    except ConnectionError as ce:
        err_msg = f"Service unavailable: {ce}"
        if is_json:
            click.echo(json.dumps({"error": err_msg}), err=True)
        else:
            click.echo(err_msg, err=True)
        sys.exit(2)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error discovering project: {e}", err=True)
        sys.exit(1)


@project_group.group("members")
def members_group():
    """Manage project memberships and access roles."""
    pass


@members_group.command("list")
@click.argument("project_id")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def list_members_cmd(ctx, project_id, json_mode):
    """List members and their roles for a project."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    try:
        from src.domains.project.operations.membership import ProjectMembershipService
        from src.cli.commands.login import verify_cli_token

        user_info = None
        try:
            user_info = verify_cli_token()
        except Exception:
            pass
        user = user_info or {"sub": "admin", "username": "admin", "roles": ["admin"]}
        svc = ProjectMembershipService()

        # Check membership
        u_id = user.get("sub") or user.get("username")
        roles = user.get("roles", [])
        if not svc.is_member(project_id, user_id=u_id, user_roles=roles):
            err_msg = f"Project '{project_id}' not found or access denied."
            if is_json:
                click.echo(json.dumps({"error": err_msg}), err=True)
            else:
                click.echo(err_msg, err=True)
            sys.exit(1)

        members = svc.list_members(project_id)
        if is_json:
            click.echo(json.dumps([m.model_dump(mode="json") for m in members], indent=2))
        else:
            click.echo(f"=== Members of {project_id} ===")
            if not members:
                click.echo("No members assigned.")
            else:
                table = [[m.user_id, m.role, m.added_by, str(m.added_at)] for m in members]
                click.echo(tabulate(table, headers=["User ID", "Role", "Added By", "Added At"], tablefmt="simple"))
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error listing members: {e}", err=True)
        sys.exit(1)


@members_group.command("add")
@click.argument("project_id")
@click.option("--user", "user_id", required=True, help="User ID to grant membership")
@click.option("--role", default="member", type=click.Choice(["member", "owner"], case_sensitive=False), help="Membership role")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def add_member_cmd(ctx, project_id, user_id, role, json_mode):
    """Add or update a project member (owner or admin only)."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    try:
        from src.domains.project.operations.membership import ProjectMembershipService
        from src.cli.commands.login import verify_cli_token

        user_info = None
        try:
            user_info = verify_cli_token()
        except Exception:
            pass
        caller = user_info or {"sub": "admin", "username": "admin", "roles": ["admin"]}
        svc = ProjectMembershipService()

        caller_id = caller.get("sub") or caller.get("username")
        roles = caller.get("roles", [])
        if not svc.is_owner(project_id, user_id=caller_id, user_roles=roles):
            err_msg = "Permission denied: Only owners or admins can add members."
            if is_json:
                click.echo(json.dumps({"error": err_msg}), err=True)
            else:
                click.echo(err_msg, err=True)
            sys.exit(1)

        member = svc.add_member(project_id=project_id, user_id=user_id, role=role.lower(), added_by=caller_id)
        if is_json:
            click.echo(member.model_dump_json(indent=2))
        else:
            click.echo(f"Added '{member.user_id}' to project '{project_id}' as {member.role}.")
        sys.exit(0)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error adding member: {e}", err=True)
        sys.exit(1)


@members_group.command("remove")
@click.argument("project_id")
@click.option("--user", "user_id", required=True, help="User ID to remove from project")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results formatted as JSON")
@click.pass_context
def remove_member_cmd(ctx, project_id, user_id, json_mode):
    """Remove a project member (owner or admin only)."""
    is_json = json_mode or (ctx.obj.get("JSON_MODE", False) if ctx.obj else json_mode)
    try:
        from src.domains.project.operations.membership import ProjectMembershipService
        from src.cli.commands.login import verify_cli_token

        user_info = None
        try:
            user_info = verify_cli_token()
        except Exception:
            pass
        caller = user_info or {"sub": "admin", "username": "admin", "roles": ["admin"]}
        svc = ProjectMembershipService()

        caller_id = caller.get("sub") or caller.get("username")
        roles = caller.get("roles", [])
        if not svc.is_owner(project_id, user_id=caller_id, user_roles=roles):
            err_msg = "Permission denied: Only owners or admins can remove members."
            if is_json:
                click.echo(json.dumps({"error": err_msg}), err=True)
            else:
                click.echo(err_msg, err=True)
            sys.exit(1)

        svc.remove_member(project_id=project_id, user_id=user_id)
        if is_json:
            click.echo(json.dumps({"status": "REMOVED", "project_id": project_id, "user_id": user_id}))
        else:
            click.echo(f"Removed '{user_id}' from project '{project_id}'.")
        sys.exit(0)
    except ValueError as ve:
        # Last owner protection
        if is_json:
            click.echo(json.dumps({"error": str(ve)}), err=True)
        else:
            click.echo(f"Error: {ve}", err=True)
        sys.exit(1)
    except Exception as e:
        if is_json:
            click.echo(json.dumps({"error": str(e)}), err=True)
        else:
            click.echo(f"Error removing member: {e}", err=True)
        sys.exit(1)


from src.cli.commands.ttl import ttl_group
project_group.add_command(ttl_group)


