import json
import pyarrow as pa
import pyarrow.parquet as pq

try:
    from src.services.analytics.query_service import QueryService
except ImportError:
    from services.analytics.query_service import QueryService


def test_duckdb_parquet_query_and_formatting(tmp_path):
    # 1. Create a synthetic Parquet file
    parquet_file = tmp_path / "test_data.parquet"
    table = pa.Table.from_pydict({
        "device_id": [f"device_{i%5}" for i in range(100)],
        "metric_name": ["temperature" if i % 2 == 0 else "cpu_load" for i in range(100)],
        "value": [float(i) for i in range(100)],
    })
    pq.write_table(table, parquet_file)

    service = QueryService()

    # 2. Test aggregation query with table format
    sql = f"SELECT metric_name, COUNT(*) as total_count, AVG(value) as avg_val FROM read_parquet('{parquet_file}') GROUP BY metric_name ORDER BY metric_name"
    out_table, meta = service.execute(sql, output_format="table")
    
    assert meta["row_count"] == 2
    assert meta["duration_seconds"] < 2.0
    assert "cpu_load" in out_table
    assert "temperature" in out_table

    # 3. Test JSON formatting
    out_json, meta_json = service.execute(sql, output_format="json")
    parsed = json.loads(out_json)
    assert len(parsed) == 2
    assert parsed[0]["metric_name"] == "cpu_load"
    assert parsed[0]["total_count"] == 50
    assert parsed[1]["metric_name"] == "temperature"

    # 4. Test CSV formatting
    out_csv, _ = service.execute(sql, output_format="csv")
    lines = out_csv.split("\n")
    assert lines[0] == "metric_name,total_count,avg_val"
    assert "cpu_load,50" in lines[1]
