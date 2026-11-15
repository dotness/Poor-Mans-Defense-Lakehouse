import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from rapidfuzz.distance import JaroWinkler

try:
    from src.config.settings import settings
    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
except ImportError:
    from config.settings import settings
    from domains.discovery.operations.kdg_graph_store import KDGGraphStore

logger = logging.getLogger("artemis.discovery.entity_resolution")


class DisjointSetUnion:
    """Disjoint-Set Union (Union-Find) with path compression."""

    def __init__(self):
        self.parent: Dict[str, str] = {}
        self.rank: Dict[str, int] = {}

    def find(self, item: str) -> str:
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0
            return item
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, item1: str, item2: str) -> None:
        root1 = self.find(item1)
        root2 = self.find(item2)
        if root1 != root2:
            if self.rank[root1] < self.rank[root2]:
                self.parent[root1] = root2
            elif self.rank[root1] > self.rank[root2]:
                self.parent[root2] = root1
            else:
                self.parent[root2] = root1
                self.rank[root1] += 1

    def get_clusters(self) -> Dict[str, List[str]]:
        clusters: Dict[str, List[str]] = {}
        for item in self.parent:
            root = self.find(item)
            clusters.setdefault(root, []).append(item)
        return clusters


class EntityResolver:
    """Resolves cross-project entity correlations using exact match, Jaro-Winkler, and DSU clustering."""

    def __init__(
        self,
        graph_store: Optional[KDGGraphStore] = None,
        fuzzy_threshold: Optional[float] = None,
    ):
        self.graph_store = graph_store or KDGGraphStore()
        self.fuzzy_threshold = fuzzy_threshold or getattr(settings, "discovery_fuzzy_threshold", 0.93)

    def normalize(self, val: str) -> str:
        """Normalizes an entity value string."""
        if not val:
            return ""
        return val.strip().lower()

    def are_types_compatible(self, type1: Optional[str], type2: Optional[str]) -> bool:
        """Checks if two entity types are compatible."""
        if not type1 or not type2:
            return True
        t1 = type1.lower().strip()
        t2 = type2.lower().strip()
        if t1 == t2:
            return True
        # Both generic
        if t1 in ("identifier", "genericentity", "entity") and t2 in ("identifier", "genericentity", "entity"):
            return True
        return False

    def resolve_pair(
        self,
        ent1: Dict[str, Any],
        ent2: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Compares two entities and returns match metadata if resolved, else None."""
        if not self.are_types_compatible(ent1.get("type"), ent2.get("type")):
            return None

        val1 = self.normalize(ent1.get("value", ""))
        val2 = self.normalize(ent2.get("value", ""))

        if not val1 or not val2:
            return None

        # Exact match
        if val1 == val2:
            return {
                "method": "exact",
                "confidence": 1.0,
            }

        # If both values contain digits, they must have the same digits to prevent false code linking
        digits1 = "".join(c for c in val1 if c.isdigit())
        digits2 = "".join(c for c in val2 if c.isdigit())
        if digits1 and digits2 and digits1 != digits2:
            return None

        # Short tokens (len <= 6) must match exactly to avoid linking codes like hosp-a and hosp-b
        if len(val1) <= 6 or len(val2) <= 6:
            return None

        # Jaro-Winkler fuzzy match
        similarity = JaroWinkler.similarity(val1, val2)
        if similarity >= self.fuzzy_threshold:
            return {
                "method": "jaro_winkler",
                "confidence": round(float(similarity), 4),
            }

        return None


    def resolve_entities_for_resource(
        self,
        project_id: str,
        resource_id: str,
    ) -> int:
        """Finds entity matches for newly indexed entities against existing cross-project entities."""
        # Query generic entities for this resource and potential match candidates
        query_res = """
            MATCH (r:DataResource {project_id: $project_id, resource_id: $resource_id})-[:CONTAINS_ENTITY]->(e:GenericEntity)
            RETURN e.entity_id as id, e.entity_type as type, e.value as value, e.normalized_value as norm;
        """
        # Execute query
        source_ents = self.graph_store.client.execute_query(query_res, {"project_id": project_id, "resource_id": resource_id})
        query_all = "MATCH (e:GenericEntity) WHERE e.project_id <> $project_id RETURN e.entity_id as id, e.entity_type as type, e.value as value, e.normalized_value as norm, e.project_id as project_id;"
        all_other_ents = self.graph_store.client.execute_query(query_all, {"project_id": project_id})

        links_created = 0
        dsu = DisjointSetUnion()

        for s_ent in source_ents:
            s_val = s_ent.get("value") or s_ent.get("norm", "")
            s_id = s_ent.get("id") or s_ent.get("entity_id")
            s_type = s_ent.get("type") or s_ent.get("entity_type")
            ent1 = {"id": s_id, "value": s_val, "type": s_type}

            for o_ent in all_other_ents:
                o_val = o_ent.get("value") or o_ent.get("norm", "")
                o_id = o_ent.get("id") or o_ent.get("entity_id")
                o_type = o_ent.get("type") or o_ent.get("entity_type")
                ent2 = {"id": o_id, "value": o_val, "type": o_type}

                match = self.resolve_pair(ent1, ent2)
                if match:
                    dsu.union(str(s_id), str(o_id))
                    links_created += 1
                    # Merge SAME_AS edge in graph
                    edge_q = """
                        MATCH (e1:GenericEntity {entity_id: $id1}), (e2:GenericEntity {entity_id: $id2})
                        MERGE (e1)-[rel:SAME_AS]-(e2)
                        ON CREATE SET rel.confidence = $conf, rel.method = $method
                        ON MATCH SET rel.confidence = $conf, rel.method = $method;
                    """
                    self.graph_store.client.execute_query(edge_q, {
                        "id1": s_id,
                        "id2": o_id,
                        "conf": match["confidence"],
                        "method": match["method"],
                    })

        return links_created
