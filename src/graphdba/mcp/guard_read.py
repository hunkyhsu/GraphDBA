import re
import logging

logger = logging.getLogger(__name__)

class ReadSecurityError(Exception):
    """Custom exception raised when an agent violates physical database boundaries"""
    pass

_FORBIDDEN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|COMMIT|ROLLBACK|DO|CALL)\b',
    re.IGNORECASE
)
_ALLOWED = re.compile(
    r'^\s*(SELECT|EXPLAIN|WITH)\b',
    re.IGNORECASE
)

def validate_query(query: str) -> None:
    "Validate the query for dangrous keywords"
    if not query or not query.strip():
        raise ReadSecurityError("SQL query can not be empty")
    
    clean_query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    clean_query = re.sub(r'/\*.*?\*/', '', clean_query, flags=re.DOTALL)

    match = _FORBIDDEN.search(clean_query)
    if match:
        blocked_word = match.group(1).upper()
        logger.warning("Blocked DML/DDL queries containing %s", blocked_word)
        raise ReadSecurityError(f"Keyword '{blocked_word}' forbidden")
    if not _ALLOWED.match(clean_query):
        logger.warning("Blocked queries not start with (SELECT, EXPLAIN, WITH)")
        raise ReadSecurityError("Only SELECT, EXPLAIN, or WITH queries allowed")

def limit_rows(query: str, limit: int) -> str:
    clean_query = query.strip().rstrip(';')
    if not re.search(r'\bLIMIT\s+\d+', clean_query, re.IGNORECASE):
        return f"{clean_query} LIMIT {limit};"
    return clean_query + ";"


class ReadEnforcer:
    validate_query = staticmethod(validate_query)
    limit_rows = staticmethod(limit_rows)
