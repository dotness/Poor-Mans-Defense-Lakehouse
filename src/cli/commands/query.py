import sys
import json
import asyncio
from typing import Optional

try:
    from src.cli.commands.login import require_cli_auth
    from src.domains.analytics.facade.analytics import AnalyticsFacade
    from src.domains.analytics.models.contract.query import QueryRequestContract
except ImportError:
    from cli.commands.login import require_cli_auth
    from domains.analytics.facade.analytics import AnalyticsFacade
    from domains.analytics.models.contract.query import QueryRequestContract


def run_query(sql: str, output_format: str = "table", json_mode: bool = False) -> int:
    """Executes analytical SQL queries via AnalyticsFacade."""
    require_cli_auth(json_mode=json_mode)
    fmt = "json" if json_mode else output_format
    try:
        facade = AnalyticsFacade()
        request = QueryRequestContract(sql=sql, format=fmt)
        result = asyncio.run(facade.execute_query(request))

        if json_mode:
            print(result.formatted_output or result.model_dump_json())
        else:
            print(f"\n{result.formatted_output}")
            print(f"\nQuery completed in {result.duration_ms / 1000.0:.3f}s ({result.row_count} rows returned).\n")
        return 0
    except Exception as e:
        if json_mode:
            print(json.dumps({"status": "FAILED", "error": str(e)}, indent=2))
        else:
            print(f"SQL Execution Error: {e}", file=sys.stderr)
        return 1
