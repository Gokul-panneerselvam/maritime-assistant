import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.loaders.base import read_csv_rows, execute_batched_query
from knowledge_graph.kg_loader.normalizers import parse_utc_iso, compute_duration_hours

logger = logging.getLogger(__name__)

PORT_CALLS_CYPHER = """
UNWIND $batch AS row
MERGE (pc:PortCall {call_id: row.call_id})
ON CREATE SET
    pc.call_type = row.call_type,
    pc.anchorage_arrival_utc = CASE WHEN row.anchorage_arrival_utc IS NOT NULL THEN datetime(row.anchorage_arrival_utc) ELSE null END,
    pc.berth_scheduled_utc = CASE WHEN row.berth_scheduled_utc IS NOT NULL THEN datetime(row.berth_scheduled_utc) ELSE null END,
    pc.berthing_utc = CASE WHEN row.berthing_utc IS NOT NULL THEN datetime(row.berthing_utc) ELSE null END,
    pc.departure_utc = CASE WHEN row.departure_utc IS NOT NULL THEN datetime(row.departure_utc) ELSE null END,
    pc.anchorage_wait_hours = row.anchorage_wait_hours,
    pc.port_stay_hours = row.port_stay_hours
ON MATCH SET
    pc.call_type = row.call_type,
    pc.anchorage_arrival_utc = CASE WHEN row.anchorage_arrival_utc IS NOT NULL THEN datetime(row.anchorage_arrival_utc) ELSE null END,
    pc.berth_scheduled_utc = CASE WHEN row.berth_scheduled_utc IS NOT NULL THEN datetime(row.berth_scheduled_utc) ELSE null END,
    pc.berthing_utc = CASE WHEN row.berthing_utc IS NOT NULL THEN datetime(row.berthing_utc) ELSE null END,
    pc.departure_utc = CASE WHEN row.departure_utc IS NOT NULL THEN datetime(row.departure_utc) ELSE null END,
    pc.anchorage_wait_hours = row.anchorage_wait_hours,
    pc.port_stay_hours = row.port_stay_hours

WITH pc, row
MATCH (voy:Voyage {voyage_id: row.voyage_id})
MERGE (voy)-[:HAS_PORT_CALL]->(pc)

WITH pc, row
MATCH (p:Port {port_code: row.port})
MERGE (pc)-[:AT_PORT]->(p)

WITH pc, row
MATCH (v:Vessel {vessel_id: row.vessel_id})
MERGE (pc)-[:CALL_BY]->(v)
"""

def load_port_calls(
    file_path: Path,
    client: Optional[Neo4jClient] = None,
    batch_size: int = 500,
    dry_run: bool = False
) -> int:
    """
    Ingests port_calls.csv into PortCall nodes, computing anchorage_wait_hours and
    port_stay_hours, and creating relationships to Voyage, Port, and Vessel.
    """
    rows = read_csv_rows(file_path)
    records: List[Dict[str, Any]] = []

    for r in rows:
        call_id = r["call_id"].strip()
        voyage_id = r["voyage_id"].strip()
        vessel_id = r["vessel_id"].strip()
        port = r["port"].strip()
        call_type = r.get("call_type", "").strip()

        anchorage_arr = parse_utc_iso(r.get("anchorage_arrival_utc", ""))
        berth_sched = parse_utc_iso(r.get("berth_scheduled_utc", ""))
        berthing = parse_utc_iso(r.get("berthing_utc", ""))
        departure = parse_utc_iso(r.get("departure_utc", ""))

        anchorage_wait = compute_duration_hours(anchorage_arr, berthing)
        port_stay = compute_duration_hours(berthing, departure)

        records.append({
            "call_id": call_id,
            "voyage_id": voyage_id,
            "vessel_id": vessel_id,
            "port": port,
            "call_type": call_type,
            "anchorage_arrival_utc": anchorage_arr,
            "berth_scheduled_utc": berth_sched,
            "berthing_utc": berthing,
            "departure_utc": departure,
            "anchorage_wait_hours": anchorage_wait,
            "port_stay_hours": port_stay
        })

    logger.info("Prepared %d PortCall records from %s", len(records), file_path.name)
    return execute_batched_query(client, PORT_CALLS_CYPHER, records, batch_size=batch_size, dry_run=dry_run)

