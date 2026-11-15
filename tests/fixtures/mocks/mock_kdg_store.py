from typing import Any, Dict, List, Optional, Tuple
from src.domains.discovery.models.contract.discovery import (
    WorkspaceKnowledgeContract,
    ResourceKnowledge,
    AttributeKnowledge,
    EntityCorrelationContract,
    EntityMatch,
    LineageContract,
    LineageNode,
    LineageEdge,
)


class MockKDGGraphStore:
    """In-memory test double for KDGGraphStore used in offline unit tests."""

    def __init__(self, memgraph_client: Any = None):
        from tests.fixtures.mocks.mock_memgraph import MockMemgraphClient
        self.client = memgraph_client or MockMemgraphClient()
        self._mock_workspaces: Dict[str, Dict[str, Any]] = {}
        self._mock_resources: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._mock_attributes: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._mock_entities: Dict[str, Dict[str, Any]] = {}
        self._mock_taxonomies: Dict[str, Dict[str, Any]] = {}
        self._mock_entity_links: List[Dict[str, Any]] = []
        self._mock_lineage: List[Dict[str, Any]] = []

        orig_execute = getattr(self.client, "execute_query", lambda q, p=None: [])
        def _dispatched_execute(query: str, parameters: Optional[Dict[str, Any]] = None):
            res = self._handle_query(query, parameters)
            if res is not None:
                return res
            return orig_execute(query, parameters)
        self.client.execute_query = _dispatched_execute

    def _handle_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        params = parameters or {}
        q = query.strip()
        q_lower = q.lower()

        # Target node lookup for lineage
        if "match (target:dataresource" in q_lower:
            p_id = params.get("project_id")
            d_id = params.get("dataset_id")
            res = self._mock_resources.get((p_id, d_id))
            if res:
                return [{"resource_id": d_id, "project_id": p_id, "tier": res.get("tier", "BRONZE")}]
            return []

        # Lineage path traversal
        if "match path = (src:dataresource)-[rel:derived_from" in q_lower:
            p_id = params.get("project_id")
            d_id = params.get("dataset_id")
            allowed = set(params.get("allowed_projects", []))
            records = []
            queue = [d_id]
            visited = set()
            depth_limit = 10
            import re
            m = re.search(r"derived_from\*1\.\.(\d+)", q_lower)
            if m:
                depth_limit = int(m.group(1))

            cur_depth = 0
            while queue and cur_depth < depth_limit:
                next_queue = []
                cur_depth += 1
                for current_target in queue:
                    for l in self._mock_lineage:
                        if l["target"] == current_target:
                            src_id = l["source"]
                            src_projs = [p for (p, r) in self._mock_resources if r == src_id]
                            src_proj = src_projs[0] if src_projs else l["project_id"]
                            if src_proj in allowed:
                                src_res = self._mock_resources.get((src_proj, src_id), {})
                                tgt_res = self._mock_resources.get((p_id, current_target), {})
                                records.append({
                                    "source_id": src_id,
                                    "source_proj": src_proj,
                                    "source_tier": src_res.get("tier", "BRONZE"),
                                    "target_id": current_target,
                                    "target_proj": p_id,
                                    "target_tier": tgt_res.get("tier", "BRONZE"),
                                    "run_id": l.get("run_id"),
                                })
                                if src_id not in visited:
                                    visited.add(src_id)
                                    next_queue.append(src_id)
                queue = next_queue
            return records

        # GenericEntity queries for entity resolution
        if "contains_entity]->(e:genericentity)" in q_lower and "match (r:dataresource" in q_lower:
            p_id = params.get("project_id")
            r_id = params.get("resource_id")
            results = []
            for k, e in self._mock_entities.items():
                if e.get("project_id") == p_id and e.get("resource_id") == r_id:
                    results.append({
                        "id": e.get("entity_id", k),
                        "type": e.get("entity_type", "ENTITY"),
                        "value": e.get("value", ""),
                        "norm": e.get("normalized_value", ""),
                    })
            return results

        if "where e.project_id <> $project_id" in q_lower:
            p_id = params.get("project_id")
            results = []
            for k, e in self._mock_entities.items():
                if e.get("project_id") != p_id:
                    results.append({
                        "id": e.get("entity_id", k),
                        "type": e.get("entity_type", "ENTITY"),
                        "value": e.get("value", ""),
                        "norm": e.get("normalized_value", ""),
                        "project_id": e.get("project_id"),
                    })
            return results

        return None

    def bootstrap_indexes(self) -> None:
        pass

    def merge_workspace(self, project_id: str, name: str, owner: str = "analyst") -> Dict[str, Any]:
        ws = {"project_id": project_id, "name": name, "owner": owner}
        self._mock_workspaces[project_id] = ws
        return ws

    def merge_data_resource(
        self,
        project_id: str,
        resource_id: str,
        format: str = "PARQUET",
        tier: str = "BRONZE",
        record_count: int = 0,
        location_uri: Optional[str] = None,
        kind: str = "tabular",
        index_version: int = 1,
    ) -> Dict[str, Any]:
        key = (project_id, resource_id)
        res = {
            "project_id": project_id,
            "resource_id": resource_id,
            "format": format.upper(),
            "tier": tier.upper(),
            "record_count": record_count,
            "location_uri": location_uri,
            "kind": kind.lower(),
            "index_version": index_version,
        }
        self._mock_resources[key] = res
        return res

    def merge_data_attribute(
        self,
        project_id: str,
        resource_id: str,
        name: str,
        physical_type: str,
        inferred_type: Optional[str] = None,
        cardinality: float = 0.0,
        null_ratio: float = 0.0,
        pattern: Optional[str] = None,
        index_version: int = 1,
    ) -> Dict[str, Any]:
        key = (project_id, resource_id, name)
        attr = {
            "project_id": project_id,
            "resource_id": resource_id,
            "name": name,
            "physical_type": physical_type,
            "inferred_type": inferred_type or physical_type,
            "cardinality": cardinality,
            "null_ratio": null_ratio,
            "pattern": pattern,
            "taxonomy": None,
            "confidence": 1.0,
            "low_confidence": False,
            "index_version": index_version,
        }
        self._mock_attributes[key] = attr
        return attr

    def merge_generic_entity(
        self,
        project_id: str,
        resource_id: str,
        attribute_name: str,
        entity_type: str,
        value: str,
        normalized_value: str,
    ) -> Dict[str, Any]:
        entity_id = f"{project_id}:{resource_id}:{attribute_name}:{normalized_value}"
        ent = {
            "entity_id": entity_id,
            "project_id": project_id,
            "resource_id": resource_id,
            "attribute_name": attribute_name,
            "entity_type": entity_type,
            "value": value,
            "normalized_value": normalized_value,
        }
        self._mock_entities[entity_id] = ent
        return ent

    def batch_merge_generic_entities(self, entities: List[Dict[str, Any]]) -> int:
        count = 0
        for e in entities:
            eid = f"{e['project_id']}:{e['resource_id']}:{e['attribute_name']}:{e['normalized_value']}"
            self._mock_entities[eid] = {
                "entity_id": eid,
                "project_id": e["project_id"],
                "resource_id": e["resource_id"],
                "attribute_name": e["attribute_name"],
                "entity_type": e.get("entity_type", "ENTITY"),
                "value": e["value"],
                "normalized_value": e["normalized_value"],
            }
            count += 1
        return count

    def merge_generic_entities_batch(
        self,
        project_id: str,
        resource_id: str,
        entities: List[Dict[str, Any]],
    ) -> None:
        for e in entities:
            norm_val = e.get("normalized_value", "")
            attr_name = e.get("attribute_name", "")
            eid = f"{project_id}:{resource_id}:{attr_name}:{norm_val}"
            self._mock_entities[eid] = {
                "entity_id": e.get("entity_id", eid),
                "project_id": project_id,
                "resource_id": resource_id,
                "attribute_name": attr_name,
                "entity_type": e.get("entity_type", "ENTITY"),
                "value": e.get("value", ""),
                "normalized_value": norm_val,
                "occurrences": e.get("occurrences", 1),
                "index_version": e.get("index_version", 1),
            }

    def merge_semantic_taxonomy(self, concept_id: str, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        tax = {"concept_id": concept_id, "name": name, "description": description or ""}
        self._mock_taxonomies[name] = tax
        return tax

    def map_attribute_to_taxonomy(
        self,
        project_id: str,
        resource_id: str,
        attribute_name: str,
        taxonomy_name: str,
        confidence: float = 1.0,
        low_confidence: bool = False,
    ) -> bool:
        key = (project_id, resource_id, attribute_name)
        if key in self._mock_attributes:
            self._mock_attributes[key]["taxonomy"] = taxonomy_name
            self._mock_attributes[key]["confidence"] = confidence
            self._mock_attributes[key]["low_confidence"] = low_confidence
            return True
        return False

    def merge_entity_link(
        self,
        source_id: str,
        target_id: str,
        link_type: str = "SAME_AS",
        confidence: float = 1.0,
        method: str = "exact",
    ) -> None:
        self._mock_entity_links.append({
            "source_id": source_id,
            "target_id": target_id,
            "link_type": link_type,
            "confidence": confidence,
            "method": method,
        })

    def record_pipeline_execution(
        self,
        run_id: str,
        pipeline_id: str,
        project_id: str,
        status: str,
        input_datasets: List[str],
        target_dataset: str,
    ) -> None:
        for inp in input_datasets:
            self._mock_lineage.append({
                "project_id": project_id,
                "source": inp,
                "target": target_dataset,
                "pipeline_id": pipeline_id,
                "run_id": run_id,
                "status": status,
            })

    def get_workspace_knowledge(
        self,
        project_id: str,
        member_projects: Optional[List[str]] = None,
    ) -> Optional[WorkspaceKnowledgeContract]:
        if member_projects is not None and project_id not in member_projects:
            return None
        ws = self._mock_workspaces.get(project_id)
        if not ws:
            return None

        resources_list = []
        agg_entities: Dict[str, int] = {}
        for (p_id, r_id), r_data in self._mock_resources.items():
            if p_id != project_id:
                continue
            attrs = []
            for (ap_id, ar_id, aname), a_data in self._mock_attributes.items():
                if ap_id == project_id and ar_id == r_id:
                    attrs.append(AttributeKnowledge(
                        name=aname,
                        physical_type=a_data["physical_type"],
                        inferred_type=a_data.get("inferred_type"),
                        cardinality=a_data.get("cardinality", 0.0),
                        null_ratio=a_data.get("null_ratio", 0.0),
                        pattern=a_data.get("pattern"),
                        taxonomy=a_data.get("taxonomy"),
                        confidence=a_data.get("confidence", 1.0),
                        low_confidence=a_data.get("low_confidence", False),
                    ))
            res_ents: Dict[str, int] = {}
            for k, e_data in self._mock_entities.items():
                if e_data.get("project_id") == project_id and e_data.get("resource_id") == r_id:
                    etype = e_data.get("entity_type", "ENTITY")
                    res_ents[etype] = res_ents.get(etype, 0) + 1
                    agg_entities[etype] = agg_entities.get(etype, 0) + 1

            resources_list.append(ResourceKnowledge(
                resource_id=r_id,
                format=r_data["format"],
                tier=r_data["tier"],
                record_count=r_data["record_count"],
                location_uri=r_data.get("location_uri"),
                kind=r_data.get("kind", "tabular"),
                attributes=attrs,
                entity_counts=res_ents,
            ))

        return WorkspaceKnowledgeContract(
            project_id=project_id,
            resources=resources_list,
            entity_type_counts=agg_entities,
            enrichment_status="completed",
        )

    def find_cross_project_entities(
        self,
        value: Optional[str] = None,
        entity_type: Optional[str] = None,
        member_projects: Optional[List[str]] = None,
        fuzzy: bool = False,
    ) -> EntityCorrelationContract:
        norm_target = value.lower().strip() if value else None
        matches = []
        query_label = value or (f"type:{entity_type}" if entity_type else "all")

        for k, e in self._mock_entities.items():
            if member_projects is not None and e.get("project_id") not in member_projects:
                continue
            if norm_target and e.get("normalized_value") != norm_target:
                continue
            if entity_type and e.get("entity_type", "").lower() != entity_type.lower():
                continue

            matches.append(EntityMatch(
                project_id=e["project_id"],
                resource_id=e["resource_id"],
                tier=self._mock_resources.get((e["project_id"], e["resource_id"]), {}).get("tier", "BRONZE"),
                attribute=e.get("attribute_name", ""),
                entity_type=e.get("entity_type", "ENTITY"),
                value=e["value"],
                match_method="exact",
                confidence=1.0,
            ))

        unique_projs = len(set(m.project_id for m in matches))
        return EntityCorrelationContract(
            query=query_label,
            total_projects=unique_projs,
            matches=matches,
        )

    def get_lineage(
        self,
        project_id: str,
        dataset_id: str,
        member_projects: Optional[List[str]] = None,
        depth: int = 10,
    ) -> LineageContract:
        if member_projects is not None and project_id not in member_projects:
            return LineageContract(project_id=project_id, dataset_id=dataset_id, is_root=True, nodes=[], edges=[])

        target_res = self._mock_resources.get((project_id, dataset_id), {})
        nodes = [LineageNode(
            resource_id=dataset_id,
            project_id=project_id,
            tier=target_res.get("tier", "BRONZE"),
            format=target_res.get("format", "PARQUET"),
        )]
        edges = []

        for l in self._mock_lineage:
            if l["project_id"] == project_id and l["target"] == dataset_id:
                edges.append(LineageEdge(
                    source=l["source"],
                    target=l["target"],
                    run_id=l.get("run_id"),
                ))
                if not any(n.resource_id == l["source"] for n in nodes):
                    src_res = self._mock_resources.get((project_id, l["source"]), {})
                    nodes.append(LineageNode(
                        resource_id=l["source"],
                        project_id=project_id,
                        tier=src_res.get("tier", "BRONZE"),
                        format=src_res.get("format", "PARQUET"),
                    ))

        return LineageContract(
            project_id=project_id,
            dataset_id=dataset_id,
            is_root=len(edges) == 0,
            nodes=nodes,
            edges=edges,
        )
