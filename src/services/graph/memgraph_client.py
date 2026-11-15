import re
import socket
import logging
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver

from src.config.settings import settings
from src.core.exceptions import ConnectionError, ServiceUnavailableError

logger = logging.getLogger(__name__)

# Valid Cypher identifier: starts with letter, followed by alphanumeric or underscores
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class MemgraphClient:
    """Client for connecting to Memgraph via Bolt protocol."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: Optional[Driver] = None,
    ):
        self.host = host or settings.memgraph_host
        self.port = port or settings.memgraph_port
        self.username = username or settings.memgraph_user
        self.password = password or settings.memgraph_password

        if driver is not None:
            self._driver: Optional[Driver] = driver
        else:
            self._driver = None
            self._connect()

    def _connect(self) -> None:
        try:
            sock = socket.create_connection((self.host, self.port), timeout=0.3)
            sock.close()
        except (OSError, socket.timeout) as e:
            logger.error(f"Memgraph unreachable at {self.host}:{self.port}: {e}")
            raise ConnectionError(
                f"Could not connect to Memgraph at {self.host}:{self.port}: {e}",
                host=self.host,
                port=self.port,
                original_cause=e,
            ) from e

        uri = f"bolt://{self.host}:{self.port}"
        auth = None
        if self.username or self.password:
            auth = (self.username, self.password)
        try:
            self._driver = GraphDatabase.driver(uri, auth=auth, connection_timeout=1.0)
        except Exception as e:
            logger.error(f"Memgraph driver init error: {e}")
            raise ConnectionError(
                f"Failed to initialize Memgraph driver at {uri}: {e}",
                host=self.host,
                port=self.port,
                original_cause=e,
            ) from e

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self._driver:
            raise ServiceUnavailableError("Memgraph driver is not connected", service="memgraph")
        try:
            with self._driver.session() as session:
                result = session.run(query, parameters or {})
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Memgraph query execution failed: {e}")
            raise ServiceUnavailableError(
                f"Memgraph query execution failed: {e}",
                service="memgraph",
                original_cause=e,
            ) from e

    def add_node(
        self,
        label: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """Creates or merges a node in Memgraph."""
        clean_label = label.upper().strip()
        if not IDENTIFIER_PATTERN.match(clean_label):
            clean_label = "ENTITY"

        props = properties or {}
        query = (
            f"MERGE (n:{clean_label} {{name: $name}}) "
            f"ON CREATE SET n.confidence = $confidence, n += $props "
            f"ON MATCH SET n.confidence = $confidence, n += $props "
            f"RETURN n"
        )
        try:
            records = self.execute_query(
                query,
                {"name": name, "confidence": confidence, "props": props},
            )
            return records[0]["n"] if records else {"name": name, "label": clean_label}
        except Exception as e:
            logger.warning(f"Failed to add node {name} to Memgraph: {e}")
            raise

    def add_edge(
        self,
        source_name: str,
        target_name: str,
        relationship: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Creates or merges a directed relationship between two nodes."""
        clean_rel = relationship.upper().strip()
        if not IDENTIFIER_PATTERN.match(clean_rel):
            clean_rel = "RELATION"

        props = properties or {}
        query = (
            f"MATCH (a {{name: $source_name}}), (b {{name: $target_name}}) "
            f"MERGE (a)-[r:{clean_rel}]->(b) "
            f"ON CREATE SET r += $props "
            f"ON MATCH SET r += $props "
            f"RETURN r"
        )
        try:
            records = self.execute_query(
                query,
                {"source_name": source_name, "target_name": target_name, "props": props},
            )
            return records[0]["r"] if records else {"source": source_name, "target": target_name}
        except Exception as e:
            logger.warning(f"Failed to add edge {source_name}->{target_name}: {e}")
            raise

    def find_related_entities(self, search_term: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Searches for nodes and their 1-hop connected neighbors for RAG context."""
        query = (
            "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($term) "
            "OR toLower(labels(n)[0]) CONTAINS toLower($term) "
            "OPTIONAL MATCH (n)-[r]-(m) "
            "RETURN n.name AS entity, labels(n)[0] AS type, type(r) AS relation, m.name AS connected_entity "
            "LIMIT $limit"
        )
        try:
            return self.execute_query(query, {"term": search_term, "limit": limit})
        except Exception as e:
            logger.warning(f"Memgraph entity context retrieval failed: {e}")
            raise
