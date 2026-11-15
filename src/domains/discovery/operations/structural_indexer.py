import json
import logging
import os
from typing import Dict, Any, Optional, List
import duckdb

try:
    from src.config.settings import settings
    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
    from src.domains.discovery.operations.pattern_profiler import PatternProfiler
except ImportError:
    from config.settings import settings
    from domains.discovery.operations.kdg_graph_store import KDGGraphStore
    from domains.discovery.operations.pattern_profiler import PatternProfiler

logger = logging.getLogger("artemis.discovery.structural_indexer")


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flattens a nested dictionary into dot-separated keys."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class StructuralIndexer:
    """Phase 1 Deterministic Structural Profiler using DuckDB and PatternProfiler."""

    def __init__(
        self,
        graph_store: Optional[KDGGraphStore] = None,
        pattern_profiler: Optional[PatternProfiler] = None,
        sample_size: Optional[int] = None,
        entity_cap: Optional[int] = None,
    ):
        self.graph_store = graph_store or KDGGraphStore()
        self.pattern_profiler = pattern_profiler or PatternProfiler()
        self.sample_size = sample_size or getattr(settings, "discovery_sample_size", 10000)
        self.entity_cap = entity_cap or getattr(settings, "discovery_entity_cap", 10000)

    def index_resource(
        self,
        project_id: str,
        resource_id: str,
        file_path: str,
        format: str = "CSV",
        tier: str = "BRONZE",
        location_uri: Optional[str] = None,
        index_version: int = 1,
    ) -> Dict[str, Any]:
        """Indexes a dataset or document structurally and updates the knowledge graph."""
        format_upper = format.upper()
        uri = location_uri or file_path

        try:
            if not os.path.exists(file_path):
                return {
                    "status": "FAILED",
                    "error": f"File not found: {file_path}",
                    "resource_id": resource_id,
                }

            # Ensure workspace node exists
            self.graph_store.merge_workspace(project_id=project_id, name=project_id)

            if format_upper in ("CSV", "PARQUET", "TSV"):
                return self._index_tabular(
                    project_id=project_id,
                    resource_id=resource_id,
                    file_path=file_path,
                    format=format_upper,
                    tier=tier,
                    location_uri=uri,
                    index_version=index_version,
                )
            elif format_upper == "JSON":
                return self._index_json(
                    project_id=project_id,
                    resource_id=resource_id,
                    file_path=file_path,
                    tier=tier,
                    location_uri=uri,
                    index_version=index_version,
                )
            elif format_upper in ("TEXT", "TXT", "MD", "PDF"):
                return self._index_text(
                    project_id=project_id,
                    resource_id=resource_id,
                    file_path=file_path,
                    format=format_upper,
                    tier=tier,
                    location_uri=uri,
                    index_version=index_version,
                )
            else:
                # Default generic indexing
                self.graph_store.merge_data_resource(
                    project_id=project_id,
                    resource_id=resource_id,
                    format=format_upper,
                    tier=tier,
                    location_uri=uri,
                    record_count=0,
                    index_version=index_version,
                )
                return {
                    "status": "SUCCESS",
                    "resource_id": resource_id,
                    "record_count": 0,
                    "format": format_upper,
                }

        except Exception as e:
            logger.error(f"Structural indexing failed for {project_id}/{resource_id}: {e}", exc_info=True)
            return {
                "status": "FAILED",
                "error": str(e),
                "resource_id": resource_id,
            }

    def _index_tabular(
        self,
        project_id: str,
        resource_id: str,
        file_path: str,
        format: str,
        tier: str,
        location_uri: str,
        index_version: int,
    ) -> Dict[str, Any]:
        con = duckdb.connect(":memory:")
        try:
            read_func = "read_parquet" if format == "PARQUET" else "read_csv_auto"
            view_sql = f"CREATE VIEW dataset AS SELECT * FROM {read_func}('{file_path}');"
            con.execute(view_sql)

            # Get total count
            total_records = con.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]

            # Register DataResource
            self.graph_store.merge_data_resource(
                project_id=project_id,
                resource_id=resource_id,
                format=format,
                tier=tier,
                location_uri=location_uri,
                record_count=total_records,
                index_version=index_version,
            )

            # Describe schema
            schema_info = con.execute("DESCRIBE dataset").fetchall()
            # Sample rows
            sample_cur = con.execute(f"SELECT * FROM dataset LIMIT {self.sample_size}")
            col_names = [desc[0] for desc in sample_cur.description]
            sample_rows = sample_cur.fetchall()

            # Transpose sample rows by column index
            for idx, row in enumerate(schema_info):
                col_name = str(row[0])
                col_type = str(row[1])

                sample_vals = [r[idx] for r in sample_rows]
                non_null_vals = [v for v in sample_vals if v is not None]
                null_count = len(sample_vals) - len(non_null_vals)
                sample_count = len(sample_vals)
                null_ratio = float(null_count / sample_count) if sample_count > 0 else 0.0

                unique_vals = list({str(v) for v in non_null_vals})
                distinct_count = len(unique_vals)
                cardinality_ratio = float(distinct_count / sample_count) if sample_count > 0 else 0.0

                pattern = self.pattern_profiler.detect_pattern(sample_vals)

                self.graph_store.merge_data_attribute(
                    project_id=project_id,
                    resource_id=resource_id,
                    name=col_name,
                    physical_type=col_type,
                    null_ratio=null_ratio,
                    cardinality=distinct_count,
                    pattern=pattern,
                    index_version=index_version,
                )

                # Capture GenericEntities if candidate
                if self.pattern_profiler.is_entity_candidate(pattern, cardinality_ratio, physical_type=col_type):
                    capped_vals = unique_vals[:self.entity_cap]
                    entity_type = pattern or "Identifier"
                    batch_entities = []
                    for val in capped_vals:
                        val_str = str(val).strip()
                        if val_str:
                            batch_entities.append({
                                "entity_id": f"{project_id}:{entity_type}:{val_str.lower()}",
                                "attribute_name": col_name,
                                "entity_type": entity_type,
                                "value": val_str,
                                "normalized_value": val_str.lower(),
                                "source": "column",
                                "occurrences": 1,
                                "index_version": index_version,
                            })
                    if batch_entities:
                        self.graph_store.merge_generic_entities_batch(
                            project_id=project_id,
                            resource_id=resource_id,
                            entities=batch_entities,
                        )


            return {
                "status": "SUCCESS",
                "resource_id": resource_id,
                "record_count": total_records,
                "format": format,
            }
        finally:
            con.close()

    def _index_json(
        self,
        project_id: str,
        resource_id: str,
        file_path: str,
        tier: str,
        location_uri: str,
        index_version: int,
    ) -> Dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        records: List[Dict[str, Any]] = []
        if content.startswith("["):
            data = json.loads(content)
            records = [flatten_dict(x) if isinstance(x, dict) else {"value": x} for x in data]
        else:
            try:
                # Single json object
                single_obj = json.loads(content)
                records = [flatten_dict(single_obj)]
            except Exception:
                # JSON Lines
                for line in content.splitlines():
                    if line.strip():
                        records.append(flatten_dict(json.loads(line)))

        record_count = len(records)
        self.graph_store.merge_data_resource(
            project_id=project_id,
            resource_id=resource_id,
            format="JSON",
            tier=tier,
            location_uri=location_uri,
            record_count=record_count,
            index_version=index_version,
        )

        if not records:
            return {"status": "SUCCESS", "resource_id": resource_id, "record_count": 0, "format": "JSON"}

        # Collect all keys
        all_keys = set()
        for r in records[:self.sample_size]:
            all_keys.update(r.keys())

        for key in all_keys:
            vals = [r.get(key) for r in records[:self.sample_size] if key in r]
            null_count = sum(1 for v in vals if v is None)
            sample_len = len(vals)
            null_ratio = float(null_count / sample_len) if sample_len > 0 else 0.0
            unique_vals = list({str(v) for v in vals if v is not None})
            cardinality = len(unique_vals)
            cardinality_ratio = float(cardinality / sample_len) if sample_len > 0 else 0.0
            pattern = self.pattern_profiler.detect_pattern(vals)

            self.graph_store.merge_data_attribute(
                project_id=project_id,
                resource_id=resource_id,
                name=key,
                physical_type="JSON_PROPERTY",
                null_ratio=null_ratio,
                cardinality=cardinality,
                pattern=pattern,
                index_version=index_version,
            )

            if self.pattern_profiler.is_entity_candidate(pattern, cardinality_ratio):
                entity_type = pattern or "Identifier"
                for u in unique_vals[:self.entity_cap]:
                    self.graph_store.merge_generic_entity(
                        project_id=project_id,
                        resource_id=resource_id,
                        attribute_name=key,
                        entity_type=entity_type,
                        value=u,
                        normalized_value=u.lower(),
                    )

        return {
            "status": "SUCCESS",
            "resource_id": resource_id,
            "record_count": record_count,
            "format": "JSON",
        }

    def _index_text(
        self,
        project_id: str,
        resource_id: str,
        file_path: str,
        format: str,
        tier: str,
        location_uri: str,
        index_version: int,
    ) -> Dict[str, Any]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        line_count = len(lines)
        word_count = sum(len(line.split()) for line in lines)

        self.graph_store.merge_data_resource(
            project_id=project_id,
            resource_id=resource_id,
            format=format,
            tier=tier,
            location_uri=location_uri,
            record_count=line_count,
            index_version=index_version,
        )

        self.graph_store.merge_data_attribute(
            project_id=project_id,
            resource_id=resource_id,
            name="content",
            physical_type="TEXT_BODY",
            null_ratio=0.0,
            cardinality=word_count,
            pattern=None,
            index_version=index_version,
        )

        return {
            "status": "SUCCESS",
            "resource_id": resource_id,
            "record_count": line_count,
            "format": format,
        }
