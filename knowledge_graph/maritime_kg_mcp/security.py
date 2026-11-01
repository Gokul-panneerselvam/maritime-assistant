import re
from typing import Tuple, Optional

# Mutating keywords that must NEVER be allowed in read queries
MUTATING_KEYWORDS_REGEX = re.compile(
    r"\b("
    r"CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|ALTER|TRUNCATE|"
    r"LOAD\s+CSV"
    r")\b",
    re.IGNORECASE
)

# Mutating or dangerous procedures
MUTATING_PROCEDURES_REGEX = re.compile(
    r"\bCALL\s+("
    r"dbms\.|"
    r"apoc\.cypher\.|"
    r"apoc\.periodic\.|"
    r"apoc\.create\.|"
    r"apoc\.merge\.|"
    r"apoc\.trigger\."
    r")",
    re.IGNORECASE
)

# Comments stripper
COMMENT_SINGLE_LINE = re.compile(r"//.*?$", re.MULTILINE)
COMMENT_MULTI_LINE = re.compile(r"/\*.*?\*/", re.DOTALL)

MAX_ROWS_LIMIT = 500
DEFAULT_ROWS_LIMIT = 100

def strip_cypher_comments(query: str) -> str:
    """Removes single-line and multi-line Cypher comments."""
    without_multi = COMMENT_MULTI_LINE.sub(" ", query)
    without_comments = COMMENT_SINGLE_LINE.sub(" ", without_multi)
    return without_comments.strip()

def validate_read_only_cypher(query: str) -> Tuple[bool, Optional[str]]:
    """
    Validates that a Cypher query is strictly read-only.
    Returns (is_valid, error_message).
    """
    if not query or not query.strip():
        return False, "Query string cannot be empty."

    cleaned_query = strip_cypher_comments(query)

    # Check for mutating keywords
    match_kw = MUTATING_KEYWORDS_REGEX.search(cleaned_query)
    if match_kw:
        keyword = match_kw.group(1).upper()
        return False, f"Permission denied: Query contains mutating keyword '{keyword}'. Only read queries are allowed."

    # Check for disallowed administrative procedures
    match_proc = MUTATING_PROCEDURES_REGEX.search(cleaned_query)
    if match_proc:
        proc = match_proc.group(1)
        return False, f"Permission denied: Calling mutating/admin procedure '{proc}' is not permitted."

    # Verify query begins with or contains read operations (MATCH, RETURN, SHOW, CALL db.)
    has_read_op = bool(re.search(r"\b(MATCH|RETURN|SHOW|CALL\s+db\.)\b", cleaned_query, re.IGNORECASE))
    if not has_read_op:
        return False, "Query must contain a valid read operation (e.g. MATCH, RETURN, SHOW, CALL db.*)."

    return True, None

def enforce_query_limit(query: str, requested_limit: int = DEFAULT_ROWS_LIMIT) -> str:
    """
    Ensures the query has a reasonable row limit, capped at MAX_ROWS_LIMIT.
    If the query has no LIMIT clause, one is appended.
    """
    cleaned = query.strip().rstrip(";")
    effective_limit = min(max(1, requested_limit), MAX_ROWS_LIMIT)

    # Check if query already has a LIMIT clause
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", cleaned, re.IGNORECASE)
    if limit_match:
        existing_val = int(limit_match.group(1))
        if existing_val > MAX_ROWS_LIMIT:
            # Replace excessive limit with MAX_ROWS_LIMIT
            cleaned = re.sub(
                r"\bLIMIT\s+\d+\b",
                f"LIMIT {MAX_ROWS_LIMIT}",
                cleaned,
                flags=re.IGNORECASE
            )
        return cleaned

    # Append limit if none present and query ends with RETURN
    if re.search(r"\bRETURN\b", cleaned, re.IGNORECASE):
        return f"{cleaned} LIMIT {effective_limit}"

    return cleaned

