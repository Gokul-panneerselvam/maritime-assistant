import logging
from pathlib import Path
from typing import Dict, List, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.loaders.base import read_csv_rows, execute_batched_query

logger = logging.getLogger(__name__)

PORTS_CYPHER = """
UNWIND $batch AS row
MERGE (p:Port {port_code: row.port_code})
ON CREATE SET
    p.name = row.name,
    p.country = row.country,
    p.timezone = row.timezone
ON MATCH SET
    p.name = row.name,
    p.country = row.country,
    p.timezone = row.timezone
"""

def load_ports(
    file_path: Path,
    client: Optional[Neo4jClient] = None,
    batch_size: int = 500,
    dry_run: bool = False
) -> Dict[str, str]:
    """
    Ingests ports.csv into (:Port) nodes.
    Returns a dictionary mapping port_code -> timezone for downstream voyage conversion.
    """
    rows = read_csv_rows(file_path)
    records: List[Dict[str, str]] = []
    timezone_map: Dict[str, str] = {}

    for r in rows:
        code = r["port_code"].strip()
        name = r["name"].strip()
        country = r["country"].strip()
        tz = r["timezone"].strip()

        timezone_map[code] = tz
        records.append({
            "port_code": code,
            "name": name,
            "country": country,
            "timezone": tz
        })

    logger.info("Prepared %d Port records from %s", len(records), file_path.name)
    execute_batched_query(client, PORTS_CYPHER, records, batch_size=batch_size, dry_run=dry_run)
    return timezone_map

