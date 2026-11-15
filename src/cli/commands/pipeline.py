import json
import asyncio
from typing import Dict, Any

try:
    from src.cli.commands.login import require_cli_auth
    from src.domains.pipeline.facade.pipeline import PipelineFacade
    from src.domains.pipeline.models.contract.pipeline import PipelineRunRequestContract
except ImportError:
    from cli.commands.login import require_cli_auth
    from domains.pipeline.facade.pipeline import PipelineFacade
    from domains.pipeline.models.contract.pipeline import PipelineRunRequestContract


def run_pipeline(name: str, json_mode: bool = False) -> int:
    """Executes a named batch processing pipeline via PipelineFacade."""
    require_cli_auth(json_mode=json_mode)
    try:
        facade = PipelineFacade()
        request = PipelineRunRequestContract(pipeline_name=name)
        result = asyncio.run(facade.run_pipeline(request))

        if json_mode:
            print(result.model_dump_json(indent=2))
        else:
            print(f"Pipeline '{name}' executed with status: {result.status}.")
            print(f"Events processed: {result.events_processed}")
            if result.object_key:
                print(f"Parquet destination: {result.object_key}")
        return 0
    except ValueError as ve:
        err = str(ve)
        if json_mode:
            print(json.dumps({"status": "FAILED", "error": err}, indent=2))
        else:
            print(f"Error: {err}")
        return 1
    except Exception as e:
        err_payload = {"status": "FAILED", "pipeline": name, "error": str(e)}
        if json_mode:
            print(json.dumps(err_payload, indent=2))
        else:
            print(f"Pipeline '{name}' failed: {e}")
        return 1
