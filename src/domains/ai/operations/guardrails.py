import re
import logging

logger = logging.getLogger("artemis.ai.guardrails")

# Forbidden SQL keywords for DuckDB analytical inspection
FORBIDDEN_SQL_PATTERNS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE|ATTACH|DETACH|COPY|INSTALL|LOAD|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# Allowed starting SQL keywords
ALLOWED_SQL_STARTS = re.compile(
    r"^\s*(SELECT|DESCRIBE|EXPLAIN|SHOW|WITH)\b",
    re.IGNORECASE,
)

# Forbidden Cypher clauses for Memgraph graph queries
FORBIDDEN_CYPHER_PATTERNS = re.compile(
    r"\b(CREATE|DELETE|DETACH|SET|REMOVE|MERGE|DROP)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql_query: str) -> str:
    """Validates that a SQL query is strictly read-only.
    
    Raises PermissionError if any mutation pattern or unauthorized statement is detected.
    Returns cleaned SQL string.
    """
    if not sql_query or not sql_query.strip():
        raise ValueError("SQL query cannot be empty.")

    clean_sql = sql_query.strip()
    
    if not ALLOWED_SQL_STARTS.match(clean_sql):
        raise PermissionError(
            f"Unauthorized SQL query: Must begin with SELECT, DESCRIBE, EXPLAIN, SHOW, or WITH. Query: '{clean_sql[:50]}...'"
        )

    match = FORBIDDEN_SQL_PATTERNS.search(clean_sql)
    if match:
        raise PermissionError(
            f"Mutating SQL keyword '{match.group(0).upper()}' is strictly prohibited in read-only analytical mode."
        )

    return clean_sql


def validate_readonly_cypher(cypher_query: str) -> str:
    """Validates that a Cypher query is strictly read-only.
    
    Raises PermissionError if any mutating clause is detected.
    Returns cleaned Cypher string.
    """
    if not cypher_query or not cypher_query.strip():
        raise ValueError("Cypher query cannot be empty.")

    clean_cypher = cypher_query.strip()

    match = FORBIDDEN_CYPHER_PATTERNS.search(clean_cypher)
    if match:
        raise PermissionError(
            f"Mutating Cypher keyword '{match.group(0).upper()}' is strictly prohibited in read-only graph mode."
        )

    return clean_cypher


SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def validate_safe_identifier(identifier: str) -> str:
    """Validates that a project or resource identifier is well-formed and safe against injection."""
    if not identifier or not str(identifier).strip():
        raise ValueError("Identifier cannot be empty.")
    clean = str(identifier).strip()
    if not SAFE_IDENTIFIER_PATTERN.match(clean):
        raise ValueError(
            f"Invalid identifier '{clean}': only alphanumeric characters, dashes, underscores, and dots are permitted."
        )
    return clean

