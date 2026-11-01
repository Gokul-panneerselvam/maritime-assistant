import csv
import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

def read_csv_rows(file_path: Path) -> List[Dict[str, str]]:
    """Reads a CSV file into a list of row dictionaries using UTF-8."""
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]

def chunk_list(items: List[Any], chunk_size: int = 500) -> Generator[List[Any], None, None]:
    """Yields successive chunks from a list."""
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]

def execute_batched_query(
    client: Optional[Neo4jClient],
    query: str,
    records: List[Dict[str, Any]],
    batch_size: int = 500,
    dry_run: bool = False
) -> int:
    """
    Executes a Cypher UNWIND query in batches of size batch_size.
    If dry_run is True or client is None, skips database execution.
    Returns the total number of records processed.
    """
    total = len(records)
    if dry_run or client is None:
        logger.info("[Dry Run] Would execute query for %d records (batch_size=%d)", total, batch_size)
        return total

    count = 0
    for chunk in chunk_list(records, batch_size):
        client.execute_batch(query, chunk)
        count += len(chunk)
        logger.debug("Ingested batch of %d records (%d/%d)", len(chunk), count, total)

    return count

