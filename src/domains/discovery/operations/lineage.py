import logging
from typing import List, Optional, Dict, Any, Set, Tuple
from collections import deque

try:
    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
    from src.domains.discovery.models.contract.discovery import (
        LineageContract,
        LineageNode,
        LineageEdge,
    )
except ImportError:
    from domains.discovery.operations.kdg_graph_store import KDGGraphStore
    from domains.discovery.models.contract.discovery import (
        LineageContract,
        LineageNode,
        LineageEdge,
    )

logger = logging.getLogger("artemis.discovery.lineage")


class LineageTraverser:
    """Traverses data provenance and pipeline execution history with member-project scoping."""

    def __init__(self, graph_store: Optional[KDGGraphStore] = None):
        self.graph_store = graph_store or KDGGraphStore()

    def get_lineage(
        self,
        project_id: str,
        dataset_id: str,
        member_projects: List[str],
        depth: int = 10,
    ) -> LineageContract:
        """Traverses lineage tree up to depth levels, strictly omitting non-member project nodes."""
        allowed_projects = set(member_projects or [])
        if project_id not in allowed_projects:
            return LineageContract(
                project_id=project_id,
                dataset_id=dataset_id,
                nodes=[],
                edges=[],
                is_root=True,
            )


        # Live Cypher Traversal
        nodes_map: Dict[str, LineageNode] = {}
        edges: List[LineageEdge] = []
        seen_edges: Set[Tuple[str, str]] = set()

        # Target node lookup
        target_q = """
            MATCH (target:DataResource {project_id: $project_id, resource_id: $dataset_id})
            RETURN target.resource_id as resource_id, target.project_id as project_id, target.tier as tier,
                   COALESCE(target.lifecycle_status, 'ACTIVE') as lifecycle_status,
                   target.purged_at as purged_at, target.applied_ttl as applied_ttl;
        """
        target_records = self.graph_store.client.execute_query(
            target_q,
            {"project_id": project_id, "dataset_id": dataset_id},
        )
        if target_records:
            t_row = target_records[0]
            t_status = t_row.get("lifecycle_status", "ACTIVE")
            nodes_map[dataset_id] = LineageNode(
                resource_id=t_row.get("resource_id", dataset_id),
                project_id=t_row.get("project_id", project_id),
                tier=t_row.get("tier", "BRONZE"),
                lifecycle_status=t_status,
                is_tombstone=(t_status == "PURGED"),
                purged_at=str(t_row["purged_at"]) if t_row.get("purged_at") else None,
                applied_ttl=t_row.get("applied_ttl"),
            )
        else:
            nodes_map[dataset_id] = LineageNode(
                resource_id=dataset_id,
                project_id=project_id,
                tier="BRONZE",
            )

        # Path traversal query
        query = """
            MATCH path = (src:DataResource)-[rel:DERIVED_FROM*1..""" + str(min(depth, 20)) + """]->(target:DataResource {project_id: $project_id, resource_id: $dataset_id})
            WHERE src.project_id IN $allowed_projects
            UNWIND relationships(path) as r
            RETURN DISTINCT startNode(r).resource_id as source_id,
                   startNode(r).project_id as source_proj,
                   startNode(r).tier as source_tier,
                   COALESCE(startNode(r).lifecycle_status, 'ACTIVE') as source_status,
                   startNode(r).purged_at as source_purged_at,
                   startNode(r).applied_ttl as source_applied_ttl,
                   endNode(r).resource_id as target_id,
                   endNode(r).project_id as target_proj,
                   endNode(r).tier as target_tier,
                   COALESCE(endNode(r).lifecycle_status, 'ACTIVE') as target_status,
                   endNode(r).purged_at as target_purged_at,
                   endNode(r).applied_ttl as target_applied_ttl,
                   r.via_run_id as run_id;
        """
        records = self.graph_store.client.execute_query(
            query,
            {"project_id": project_id, "dataset_id": dataset_id, "allowed_projects": list(allowed_projects)},
        )

        for rec in records:
            s_id = rec.get("source_id")
            s_proj = rec.get("source_proj")
            t_id = rec.get("target_id")
            t_proj = rec.get("target_proj")
            run_id = rec.get("run_id")

            if s_id and s_proj in allowed_projects:
                s_status = rec.get("source_status", "ACTIVE")
                nodes_map[s_id] = LineageNode(
                    resource_id=s_id,
                    project_id=s_proj,
                    tier=rec.get("source_tier", "BRONZE"),
                    lifecycle_status=s_status,
                    is_tombstone=(s_status == "PURGED"),
                    purged_at=str(rec["source_purged_at"]) if rec.get("source_purged_at") else None,
                    applied_ttl=rec.get("source_applied_ttl"),
                )
            if t_id and t_proj in allowed_projects:
                t_status = rec.get("target_status", "ACTIVE")
                nodes_map[t_id] = LineageNode(
                    resource_id=t_id,
                    project_id=t_proj,
                    tier=rec.get("target_tier", "BRONZE"),
                    lifecycle_status=t_status,
                    is_tombstone=(t_status == "PURGED"),
                    purged_at=str(rec["target_purged_at"]) if rec.get("target_purged_at") else None,
                    applied_ttl=rec.get("target_applied_ttl"),
                )

            if s_id and t_id and (s_id, t_id) not in seen_edges:
                seen_edges.add((s_id, t_id))
                edges.append(LineageEdge(
                    source=s_id,
                    target=t_id,
                    relationship="DERIVED_FROM",
                    run_id=run_id,
                ))

        is_root = len(edges) == 0
        return LineageContract(
            project_id=project_id,
            dataset_id=dataset_id,
            nodes=list(nodes_map.values()),
            edges=edges,
            is_root=is_root,
        )


