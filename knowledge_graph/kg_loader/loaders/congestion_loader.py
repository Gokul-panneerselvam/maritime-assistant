import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.loaders.base import read_csv_rows, execute_batched_query

logger = logging.getLogger(__name__)

CONGESTION_CYPHER = """
UNWIND $batch AS row
MERGE (cg:Congestion {congestion_id: row.congestion_id})
ON CREATE SET
    cg.date_utc = CASE WHEN row.date_utc IS NOT NULL THEN date(row.date_utc) ELSE null END,
    cg.congestion_level = row.congestion_level,
    cg.avg_wait_hours = row.avg_wait_hours,
    cg.vessels_at_anchor = row.vessels_at_anchor,
    cg.source = row.source
ON MATCH SET
    cg.date_utc = CASE WHEN row.date_utc IS NOT NULL THEN date(row.date_utc) ELSE null END,
    cg.congestion_level = row.congestion_level,
    cg.avg_wait_hours = row.avg_wait_hours,
    cg.vessels_at_anchor = row.vessels_at_anchor,
    cg.source = row.source

WITH cg, row
MATCH (p:Port {port_code: row.port})
MERGE (p)-[:HAS_CONGESTION]->(cg)
"""

def load_congestion(
    file_path: Path,
    client: Optional[Neo4jClient] = None,
    batch_size: int = 500,
    dry_run: bool = False
) -> int:
    """
    Ingests congestion.csv into Congestion nodes with composite ID CONG_<port>_<date>,
    and connects them to the associated Port via [:HAS_CONGESTION].
    """
    rows = read_csv_rows(file_path)
    records: List[Dict[str, Any]] = []

    for r in rows:
        port = r["port"].strip()
        date_str = r["date"].strip()
        congestion_id = f"CONG_{port}_{date_str}"
        level = r.get("congestion_level", "").strip()

        raw_wait = r.get("avg_wait_hours", "").strip()
        avg_wait = float(raw_wait) if raw_wait else 0.0

        raw_vessels = r.get("vessels_at_anchor", "").strip()
        vessels_at_anchor = int(raw_vessels) if raw_vessels else 0

        source = r.get("source", "").strip()

        records.append({
            "congestion_id": congestion_id,
            "port": port,
            "date_utc": date_str,
            "congestion_level": level,
            "avg_wait_hours": avg_wait,
            "vessels_at_anchor": vessels_at_anchor,
            "source": source
        })

    logger.info("Prepared %d Congestion records from %s", len(records), file_path.name)
    return execute_batched_query(client, CONGESTION_CYPHER, records, batch_size=batch_size, dry_run=dry_run)

