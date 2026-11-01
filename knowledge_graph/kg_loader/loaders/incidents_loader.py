import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.loaders.base import read_csv_rows, execute_batched_query
from knowledge_graph.kg_loader.normalizers import parse_utc_iso

logger = logging.getLogger(__name__)

INCIDENTS_CYPHER = """
UNWIND $batch AS row
MERGE (inc:Incident {incident_id: row.incident_id})
ON CREATE SET
    inc.type = row.type,
    inc.status = row.status,
    inc.severity = row.severity,
    inc.reported_utc = CASE WHEN row.reported_utc IS NOT NULL THEN datetime(row.reported_utc) ELSE null END,
    inc.source = row.source,
    inc.attributed_delay_hours = row.attributed_delay_hours
ON MATCH SET
    inc.type = row.type,
    inc.status = row.status,
    inc.severity = row.severity,
    inc.reported_utc = CASE WHEN row.reported_utc IS NOT NULL THEN datetime(row.reported_utc) ELSE null END,
    inc.source = row.source,
    inc.attributed_delay_hours = row.attributed_delay_hours

WITH inc, row
MATCH (voy:Voyage {voyage_id: row.voyage_id})
MERGE (voy)-[:EXPERIENCED_INCIDENT]->(inc)

WITH inc, voy
MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
MERGE (inc)-[:AFFECTS_VESSEL]->(v)
"""

def load_incidents(
    file_path: Path,
    client: Optional[Neo4jClient] = None,
    batch_size: int = 500,
    dry_run: bool = False
) -> int:
    """
    Ingests incidents.csv into Incident nodes, links them to Voyage via [:EXPERIENCED_INCIDENT],
    and to the operating Vessel via [:AFFECTS_VESSEL].
    """
    rows = read_csv_rows(file_path)
    records: List[Dict[str, Any]] = []

    for r in rows:
        incident_id = r["incident_id"].strip()
        voyage_id = r["voyage_id"].strip()
        itype = r.get("type", "").strip()
        status = r.get("status", "").strip()
        severity = r.get("severity", "").strip()
        source = r.get("source", "").strip()
        reported_utc = parse_utc_iso(r.get("reported_utc", ""))

        raw_delay = r.get("attributed_delay_hours", "").strip()
        attributed_delay = float(raw_delay) if raw_delay else None

        records.append({
            "incident_id": incident_id,
            "voyage_id": voyage_id,
            "type": itype,
            "status": status,
            "severity": severity,
            "reported_utc": reported_utc,
            "source": source,
            "attributed_delay_hours": attributed_delay
        })

    logger.info("Prepared %d Incident records from %s", len(records), file_path.name)
    return execute_batched_query(client, INCIDENTS_CYPHER, records, batch_size=batch_size, dry_run=dry_run)

