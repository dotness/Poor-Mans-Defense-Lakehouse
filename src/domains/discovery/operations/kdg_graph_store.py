import logging
from typing import Any, Dict, List, Optional, Tuple

from src.services.graph.memgraph_client import MemgraphClient
from src.domains.discovery.models.contract.discovery import (
    WorkspaceKnowledgeContract,
    ResourceKnowledge,
    AttributeKnowledge,
    EntityCorrelationContract,
    EntityMatch,
    LineageContract,
)

logger = logging.getLogger("artemis.discovery.graph_store")


class KDGGraphStore:
    """Manages knowledge graph persistence and queries in Memgraph."""

    def __init__(self, memgraph_client: Optional[MemgraphClient] = None):
        self.client = memgraph_client or MemgraphClient()
        self.bootstrap_indexes()

    def bootstrap_indexes(self) -> None:
        """Initializes index constraints in Memgraph."""
        indexes = [
            "CREATE INDEX ON :DataResource(project_id);",
            "CREATE INDEX ON :DataAttribute(project_id);",
            "CREATE INDEX ON :GenericEntity(project_id);",
            "CREATE INDEX ON :GenericEntity(normalized_value);",
            "CREATE INDEX ON :GenericEntity(entity_type);",
            "CREATE INDEX ON :SemanticTaxonomy(name);",
        ]
        for idx in indexes:
            try:
                self.client.execute_query(idx)
            except Exception as e:
                logger.debug(f"Index creation notice: {e}")

    def merge_workspace(self, project_id: str, name: str, owner: Optional[str] = None) -> Dict[str, Any]:
        """Creates or updates a Workspace node."""
        query = """
            MERGE (w:Workspace {project_id: $project_id})
            ON CREATE SET w.name = $name, w.owner = $owner, w.created_at = datetime()
            ON MATCH SET w.name = $name
            RETURN w;
        """
        records = self.client.execute_query(query, {"project_id": project_id, "name": name, "owner": owner})
        return records[0]["w"] if records else {"project_id": project_id, "name": name}

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
        """Creates or updates a DataResource node linked to a Workspace."""
        query = """
            MERGE (w:Workspace {project_id: $project_id})
            MERGE (r:DataResource {project_id: $project_id, resource_id: $resource_id})
            ON CREATE SET r.format = $format, r.tier = $tier, r.record_count = $record_count,
                          r.location_uri = $location_uri, r.kind = $kind, r.index_version = $index_version,
                          r.indexed_at = datetime()
            ON MATCH SET r.format = $format, r.tier = $tier, r.record_count = $record_count,
                         r.location_uri = $location_uri, r.kind = $kind, r.index_version = $index_version,
                         r.indexed_at = datetime()
            MERGE (w)-[:OWNS_RESOURCE]->(r)
            RETURN r;
        """
        records = self.client.execute_query(
            query,
            {
                "project_id": project_id,
                "resource_id": resource_id,
                "format": format.upper(),
                "tier": tier.upper(),
                "record_count": record_count,
                "location_uri": location_uri,
                "kind": kind.lower(),
                "index_version": index_version,
            },
        )
        return records[0]["r"] if records else {"project_id": project_id, "resource_id": resource_id}

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
        """Creates or updates a DataAttribute node connected to a DataResource."""
        query = """
            MATCH (r:DataResource {project_id: $project_id, resource_id: $resource_id})
            MERGE (a:DataAttribute {project_id: $project_id, resource_id: $resource_id, name: $name})
            ON CREATE SET a.physical_type = $physical_type, a.inferred_type = $inferred_type,
                          a.cardinality = $cardinality, a.null_ratio = $null_ratio,
                          a.pattern = $pattern, a.index_version = $index_version
            ON MATCH SET a.physical_type = $physical_type, a.inferred_type = $inferred_type,
                         a.cardinality = $cardinality, a.null_ratio = $null_ratio,
                         a.pattern = $pattern, a.index_version = $index_version
            MERGE (r)-[:HAS_ATTRIBUTE]->(a)
            RETURN a;
        """
        records = self.client.execute_query(
            query,
            {
                "project_id": project_id,
                "resource_id": resource_id,
                "name": name,
                "physical_type": physical_type,
                "inferred_type": inferred_type,
                "cardinality": cardinality,
                "null_ratio": null_ratio,
                "pattern": pattern,
                "index_version": index_version,
            },
        )
        return records[0]["a"] if records else {"name": name}

    def merge_generic_entity(
        self,
        project_id: str,
        resource_id: str,
        attribute_name: str,
        entity_type: str,
        value: str,
        normalized_value: str,
        source: str = "column",
        occurrences: int = 1,
        index_version: int = 1,
    ) -> Dict[str, Any]:
        """Creates or updates a GenericEntity node linked to a DataResource via CONTAINS_ENTITY."""
        entity_id = f"{project_id}:{entity_type}:{normalized_value}"
        query = """
            MATCH (r:DataResource {project_id: $project_id, resource_id: $resource_id})
            MERGE (e:GenericEntity {project_id: $project_id, entity_type: $entity_type, normalized_value: $normalized_value})
            ON CREATE SET e.entity_id = $entity_id, e.value = $value, e.source = $source, e.index_version = $index_version
            ON MATCH SET e.value = $value, e.source = $source, e.index_version = $index_version
            MERGE (r)-[rel:CONTAINS_ENTITY {attribute: $attribute_name}]->(e)
            ON CREATE SET rel.occurrences = $occurrences
            ON MATCH SET rel.occurrences = rel.occurrences + $occurrences
            RETURN e;
        """
        records = self.client.execute_query(
            query,
            {
                "project_id": project_id,
                "resource_id": resource_id,
                "attribute_name": attribute_name,
                "entity_type": entity_type,
                "value": value,
                "normalized_value": normalized_value,
                "source": source,
                "occurrences": occurrences,
                "index_version": index_version,
                "entity_id": entity_id,
            },
        )
        return records[0]["e"] if records else {"entity_id": entity_id}

    def merge_generic_entities_batch(
        self,
        project_id: str,
        resource_id: str,
        entities: List[Dict[str, Any]],
    ) -> None:
        """Batches creation/updates of GenericEntity nodes linked to DataResource."""
        if not entities:
            return

        chunk_size = 500
        for i in range(0, len(entities), chunk_size):
            chunk = entities[i : i + chunk_size]
            query = """
                MATCH (r:DataResource {project_id: $project_id, resource_id: $resource_id})
                UNWIND $batch AS item
                MERGE (e:GenericEntity {project_id: $project_id, entity_type: item.entity_type, normalized_value: item.normalized_value})
                ON CREATE SET e.entity_id = item.entity_id, e.value = item.value, e.source = item.source, e.index_version = item.index_version
                ON MATCH SET e.value = item.value, e.source = item.source, e.index_version = item.index_version
                MERGE (r)-[rel:CONTAINS_ENTITY {attribute: item.attribute_name}]->(e)
                ON CREATE SET rel.occurrences = item.occurrences
                ON MATCH SET rel.occurrences = rel.occurrences + item.occurrences;
            """
            self.client.execute_query(
                query,
                {
                    "project_id": project_id,
                    "resource_id": resource_id,
                    "batch": chunk,
                },
            )

    def merge_semantic_taxonomy(
        self,
        concept_id: str,
        name: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """Creates or updates a SemanticTaxonomy concept node."""
        query = """
            MERGE (t:SemanticTaxonomy {name: $name})
            ON CREATE SET t.concept_id = $concept_id, t.description = $description
            ON MATCH SET t.description = $description
            RETURN t;
        """
        records = self.client.execute_query(
            query,
            {"concept_id": concept_id, "name": name, "description": description},
        )
        return records[0]["t"] if records else {"name": name}

    def map_attribute_to_taxonomy(
        self,
        project_id: str,
        resource_id: str,
        attribute_name: str,
        taxonomy_name: str,
        confidence: float,
        low_confidence: bool = False,
    ) -> None:
        """Connects a DataAttribute to a SemanticTaxonomy node."""
        query = """
            MATCH (a:DataAttribute {project_id: $project_id, resource_id: $resource_id, name: $attribute_name})
            MERGE (t:SemanticTaxonomy {name: $taxonomy_name})
            MERGE (a)-[r:MAPS_TO_TAXONOMY]->(t)
            SET r.confidence = $confidence, r.low_confidence = $low_confidence
            RETURN r;
        """
        self.client.execute_query(
            query,
            {
                "project_id": project_id,
                "resource_id": resource_id,
                "attribute_name": attribute_name,
                "taxonomy_name": taxonomy_name,
                "confidence": confidence,
                "low_confidence": low_confidence,
            },
        )

    def link_same_as(
        self,
        entity_a_id: str,
        entity_b_id: str,
        confidence: float = 1.0,
        method: str = "exact",
    ) -> None:
        """Links two GenericEntity nodes with a bidirectional SAME_AS relationship."""
        query = """
            MATCH (a:GenericEntity {entity_id: $id_a})
            MATCH (b:GenericEntity {entity_id: $id_b})
            WHERE a <> b
            MERGE (a)-[r:SAME_AS]->(b)
            SET r.confidence = $confidence, r.method = $method
            RETURN r;
        """
        self.client.execute_query(
            query,
            {"id_a": entity_a_id, "id_b": entity_b_id, "confidence": confidence, "method": method},
        )

    def prune_stale_index_data(
        self,
        project_id: str,
        resource_id: str,
        current_index_version: int,
    ) -> None:
        """Removes attributes and resource-entity links older than current_index_version."""
        query_attrs = """
            MATCH (a:DataAttribute {project_id: $project_id, resource_id: $resource_id})
            WHERE a.index_version < $ver
            DETACH DELETE a;
        """
        query_rels = """
            MATCH (r:DataResource {project_id: $project_id, resource_id: $resource_id})-[rel:CONTAINS_ENTITY]->(e:GenericEntity)
            WHERE e.index_version < $ver
            DELETE rel;
        """
        self.client.execute_query(query_attrs, {"project_id": project_id, "resource_id": resource_id, "ver": current_index_version})
        self.client.execute_query(query_rels, {"project_id": project_id, "resource_id": resource_id, "ver": current_index_version})

    def delete_resource(self, project_id: str, resource_id: str) -> None:
        """Deletes a resource subtree and cleans up orphaned entities."""
        query = """
            MATCH (r:DataResource {project_id: $project_id, resource_id: $resource_id})
            OPTIONAL MATCH (r)-[:HAS_ATTRIBUTE]->(a:DataAttribute)
            DETACH DELETE a
            DETACH DELETE r;
        """
        self.client.execute_query(query, {"project_id": project_id, "resource_id": resource_id})

    def delete_workspace_subtree(self, project_id: str) -> None:
        """Deletes workspace, all its resources, attributes, and entities."""
        query = """
            MATCH (w:Workspace {project_id: $project_id})
            OPTIONAL MATCH (w)-[:CONTAINS_RESOURCE]->(r:DataResource)
            OPTIONAL MATCH (r)-[:HAS_ATTRIBUTE]->(a:DataAttribute)
            OPTIONAL MATCH (r)-[:CONTAINS_ENTITY]->(e:GenericEntity)
            DETACH DELETE a
            DETACH DELETE e
            DETACH DELETE r
            DETACH DELETE w;
        """
        self.client.execute_query(query, {"project_id": project_id})

    def get_workspace_knowledge(
        self,
        project_id: str,
        member_projects: List[str],
    ) -> Optional[WorkspaceKnowledgeContract]:
        """Retrieves complete knowledge summary for a workspace if user is a member."""
        if project_id not in member_projects:
            return None

        query = """
            MATCH (r:DataResource {project_id: $project_id})
            OPTIONAL MATCH (r)-[:HAS_ATTRIBUTE]->(a:DataAttribute)
            OPTIONAL MATCH (a)-[mt:MAPS_TO_TAXONOMY]->(t:SemanticTaxonomy)
            OPTIONAL MATCH (r)-[:CONTAINS_ENTITY]->(e:GenericEntity)
            OPTIONAL MATCH (parent:DataResource)-[:DERIVED_FROM]->(r)
            RETURN r, collect(DISTINCT a) as attrs, collect(DISTINCT {name: a.name, tax: t.name, conf: mt.confidence, low: mt.low_confidence}) as tax_maps,
                   collect(DISTINCT e) as entities, collect(DISTINCT parent.resource_id) as parents;
        """
        records = self.client.execute_query(query, {"project_id": project_id})
        resources: List[ResourceKnowledge] = []
        agg_entities: Dict[str, int] = {}

        for rec in records:
            r = rec["r"]
            if not r:
                continue
            r_id = r.get("resource_id", "")
            attrs_data = rec.get("attrs", [])
            tax_maps = {m["name"]: m for m in rec.get("tax_maps", []) if m.get("name")}
            entities_data = rec.get("entities", [])
            parents = [p for p in rec.get("parents", []) if p]

            attrs: List[AttributeKnowledge] = []
            for a in attrs_data:
                if not a:
                    continue
                aname = a.get("name", "")
                tinfo = tax_maps.get(aname, {})
                attrs.append(AttributeKnowledge(
                    name=aname,
                    physical_type=a.get("physical_type", "VARCHAR"),
                    inferred_type=a.get("inferred_type"),
                    taxonomy=tinfo.get("tax"),
                    confidence=float(tinfo.get("conf")) if tinfo.get("conf") is not None else None,
                    low_confidence=bool(tinfo.get("low") or False),
                    cardinality=float(a.get("cardinality", 0.0)),
                    null_ratio=float(a.get("null_ratio", 0.0)),
                    pattern=a.get("pattern"),
                ))

            res_ents: Dict[str, int] = {}
            for e in entities_data:
                if not e:
                    continue
                etype = e.get("entity_type", "ENTITY")
                res_ents[etype] = res_ents.get(etype, 0) + 1
                agg_entities[etype] = agg_entities.get(etype, 0) + 1

            resources.append(ResourceKnowledge(
                resource_id=r_id,
                format=r.get("format", "PARQUET"),
                tier=r.get("tier", "BRONZE"),
                record_count=int(r.get("record_count", 0)),
                location_uri=r.get("location_uri"),
                kind=r.get("kind", "tabular"),
                attributes=attrs,
                entity_counts=res_ents,
                derived_from=parents,
            ))

        return WorkspaceKnowledgeContract(
            project_id=project_id,
            resources=resources,
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
        """Finds entity matches across projects, strictly limited to member_projects."""
        allowed_projects = set(member_projects or [])
        matches: List[EntityMatch] = []
        val_norm = value.strip().lower() if value else None
        query_label = value or (f"type:{entity_type}" if entity_type else "all")

        if not allowed_projects:
            return EntityCorrelationContract(query=query_label, matches=[], total_projects=0)

        # Cypher query with strict member_projects confinement
        query = """
            MATCH (r:DataResource)-[rel:CONTAINS_ENTITY]->(e:GenericEntity)
            WHERE r.project_id IN $projects
              AND ($val IS NULL OR e.normalized_value = $val)
              AND ($type IS NULL OR toLower(e.entity_type) = toLower($type))
            RETURN r.project_id as project_id, r.resource_id as resource_id, r.tier as tier,
                   rel.attribute as attribute, e.entity_type as entity_type, e.value as value,
                   'exact' as match_method, 1.0 as confidence;
        """
        records = self.client.execute_query(
            query,
            {
                "projects": list(allowed_projects),
                "val": val_norm,
                "type": entity_type,
            },
        )
        for rec in records:
            matches.append(EntityMatch(
                project_id=rec["project_id"],
                resource_id=rec["resource_id"],
                tier=rec.get("tier", "BRONZE"),
                attribute=rec.get("attribute", ""),
                entity_type=rec.get("entity_type", ""),
                value=rec.get("value", ""),
                match_method=rec.get("match_method", "exact"),
                confidence=float(rec.get("confidence", 1.0)),
            ))

        distinct_projects = len(set(m.project_id for m in matches))
        return EntityCorrelationContract(
            query=query_label,
            matches=matches,
            total_projects=distinct_projects,
        )

    def get_lineage(
        self,
        project_id: str,
        dataset_id: str,
        member_projects: List[str],
        depth: int = 10,
    ) -> LineageContract:
        """Retrieves lineage tree, filtering out nodes outside member_projects."""
        try:
            from src.domains.discovery.operations.lineage import LineageTraverser
        except ImportError:
            from domains.discovery.operations.lineage import LineageTraverser
        traverser = LineageTraverser(graph_store=self)
        return traverser.get_lineage(project_id, dataset_id, member_projects, depth)

    def record_pipeline_execution(
        self,
        run_id: str,
        pipeline_id: str,
        project_id: str,
        status: str,
        input_datasets: List[str],
        target_dataset: str,
    ) -> None:
        """Records PipelineExecution node and connects DERIVED_FROM edges between datasets."""
        query = """
            MERGE (pe:PipelineExecution {run_id: $run_id})
            ON CREATE SET pe.pipeline_id = $pipeline_id, pe.project_id = $project_id,
                          pe.status = $status, pe.executed_at = datetime()
            WITH pe
            MATCH (target:DataResource {project_id: $project_id, resource_id: $target_dataset})
            MERGE (pe)-[:WRITES_TO]->(target)
            WITH pe, target
            UNWIND $inputs as inp_id
            MATCH (src:DataResource {project_id: $project_id, resource_id: inp_id})
            MERGE (pe)-[:READS_FROM]->(src)
            MERGE (src)-[:DERIVED_FROM {via_run_id: $run_id}]->(target);
        """
        self.client.execute_query(
            query,
            {
                "run_id": run_id,
                "pipeline_id": pipeline_id,
                "project_id": project_id,
                "status": status,
                "inputs": input_datasets,
                "target_dataset": target_dataset,
            },
        )
