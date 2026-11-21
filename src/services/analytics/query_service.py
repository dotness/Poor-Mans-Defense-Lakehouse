import time
import json
import io
import csv
from typing import Dict, Any, Tuple
from tabulate import tabulate

try:
    from src.services.analytics.duckdb_client import DuckDBClient
except ImportError:
    from services.analytics.duckdb_client import DuckDBClient


class QueryService:
    def __init__(self, client: DuckDBClient = None):
        self.client = client or DuckDBClient()

    def execute(self, sql: str, output_format: str = "table") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        executable_sql = sql
        short_circuit_empty = False
        try:
            from src.domains.retention.operations.query_interceptor import QueryTTLInterceptor
            interception = QueryTTLInterceptor().intercept_sql_query(sql)
            if interception.short_circuit_empty:
                short_circuit_empty = True
            else:
                executable_sql = interception.rewritten_sql
        except Exception:
            pass

        if short_circuit_empty:
            duration_sec = time.time() - start_time
            columns = []
            rows = []
            row_count = 0
        else:
            try:
                cursor = self.client.query(executable_sql)
                duration_sec = time.time() - start_time
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                row_count = len(rows)
            except Exception as e:
                err_msg = str(e)
                if "No files found that match the pattern" in err_msg or "No files match" in err_msg:
                    duration_sec = time.time() - start_time
                    columns = []
                    rows = []
                    row_count = 0
                else:
                    raise

        meta = {
            "query": sql,
            "duration_seconds": round(duration_sec, 4),
            "row_count": row_count,
            "columns": columns,
        }

        if output_format == "json":
            dict_rows = [dict(zip(columns, row)) for row in rows]
            formatted_output = json.dumps(dict_rows, indent=2, default=str)
        elif output_format == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            if columns:
                writer.writerow(columns)
                writer.writerows(rows)
            formatted_output = buf.getvalue().strip()
        else:
            # table format
            if row_count == 0 and not columns:
                formatted_output = "No data found (telemetry lake in object storage is empty)."
            else:
                formatted_output = tabulate(rows, headers=columns, tablefmt="simple")

        return formatted_output, meta

