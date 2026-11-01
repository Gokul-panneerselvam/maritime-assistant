import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.loaders.base import read_csv_rows, execute_batched_query
from knowledge_graph.kg_loader.normalizers import convert_local_to_utc

logger = logging.getLogger(__name__)

VOYAGES_CYPHER = """
UNWIND $batch AS row
MERGE (voy:Voyage {voyage_id: row.voyage_id})
ON CREATE SET
    voy.departure_local = row.departure_local,
    voy.departure_utc = CASE WHEN row.departure_utc IS NOT NULL THEN datetime(row.departure_utc) ELSE null END,
    voy.original_eta_local = row.original_eta_local,
    voy.original_eta_utc = CASE WHEN row.original_eta_utc IS NOT NULL THEN datetime(row.original_eta_utc) ELSE null END,
    voy.revised_eta_local = row.revised_eta_local,
    voy.revised_eta_utc = CASE WHEN row.revised_eta_utc IS NOT NULL THEN datetime(row.revised_eta_utc) ELSE null END,
    voy.berth_window_start_local = row.berth_window_start_local,
    voy.berth_window_start_utc = CASE WHEN row.berth_window_start_utc IS NOT NULL THEN datetime(row.berth_window_start_utc) ELSE null END,
    voy.berth_window_end_local = row.berth_window_end_local,
    voy.berth_window_end_utc = CASE WHEN row.berth_window_end_utc IS NOT NULL THEN datetime(row.berth_window_end_utc) ELSE null END,
    voy.status = row.status,
    voy.recorded_delay_hours = row.recorded_delay_hours
ON MATCH SET
    voy.departure_local = row.departure_local,
    voy.departure_utc = CASE WHEN row.departure_utc IS NOT NULL THEN datetime(row.departure_utc) ELSE null END,
    voy.original_eta_local = row.original_eta_local,
    voy.original_eta_utc = CASE WHEN row.original_eta_utc IS NOT NULL THEN datetime(row.original_eta_utc) ELSE null END,
    voy.revised_eta_local = row.revised_eta_local,
    voy.revised_eta_utc = CASE WHEN row.revised_eta_utc IS NOT NULL THEN datetime(row.revised_eta_utc) ELSE null END,
    voy.berth_window_start_local = row.berth_window_start_local,
    voy.berth_window_start_utc = CASE WHEN row.berth_window_start_utc IS NOT NULL THEN datetime(row.berth_window_start_utc) ELSE null END,
    voy.berth_window_end_local = row.berth_window_end_local,
    voy.berth_window_end_utc = CASE WHEN row.berth_window_end_utc IS NOT NULL THEN datetime(row.berth_window_end_utc) ELSE null END,
    voy.status = row.status,
    voy.recorded_delay_hours = row.recorded_delay_hours

WITH voy, row
MATCH (v:Vessel {vessel_id: row.vessel_id})
MERGE (v)-[:OPERATES_VOYAGE]->(voy)

WITH voy, row
MATCH (origin:Port {port_code: row.origin})
MERGE (voy)-[:DEPARTS_FROM]->(origin)

WITH voy, row
MATCH (dest:Port {port_code: row.destination})
MERGE (voy)-[:ARRIVES_AT]->(dest)
"""

def load_voyages(
    file_path: Path,
    port_timezones: Dict[str, str],
    client: Optional[Neo4jClient] = None,
    batch_size: int = 500,
    dry_run: bool = False
) -> int:
    """
    Ingests voyages.csv into Voyage nodes, converting all local timestamps to standardized UTC
    based on port timezones, and connects them to Vessel, origin Port, and destination Port.
    """
    rows = read_csv_rows(file_path)
    records: List[Dict[str, Any]] = []

    for r in rows:
        voyage_id = r["voyage_id"].strip()
        vessel_id = r["vessel_id"].strip()
        origin = r["origin"].strip()
        destination = r["destination"].strip()

        origin_tz = port_timezones.get(origin, "UTC")
        dest_tz = port_timezones.get(destination, "UTC")

        dep_local = r.get("departure_local", "").strip() or None
        orig_eta_local = r.get("original_eta_local", "").strip() or None
        rev_eta_local = r.get("revised_eta_local", "").strip() or None
        bw_start_local = r.get("berth_window_start_local", "").strip() or None
        bw_end_local = r.get("berth_window_end_local", "").strip() or None

        # Convert local times using origin and destination timezones
        dep_utc = convert_local_to_utc(dep_local, origin_tz)
        orig_eta_utc = convert_local_to_utc(orig_eta_local, dest_tz)
        rev_eta_utc = convert_local_to_utc(rev_eta_local, dest_tz)
        bw_start_utc = convert_local_to_utc(bw_start_local, dest_tz)
        bw_end_utc = convert_local_to_utc(bw_end_local, dest_tz)

        raw_delay = r.get("recorded_delay_hours", "").strip()
        recorded_delay_hours = float(raw_delay) if raw_delay else 0.0

        records.append({
            "voyage_id": voyage_id,
            "vessel_id": vessel_id,
            "origin": origin,
            "destination": destination,
            "departure_local": dep_local,
            "departure_utc": dep_utc,
            "original_eta_local": orig_eta_local,
            "original_eta_utc": orig_eta_utc,
            "revised_eta_local": rev_eta_local,
            "revised_eta_utc": rev_eta_utc,
            "berth_window_start_local": bw_start_local,
            "berth_window_start_utc": bw_start_utc,
            "berth_window_end_local": bw_end_local,
            "berth_window_end_utc": bw_end_utc,
            "status": r.get("status", "").strip(),
            "recorded_delay_hours": recorded_delay_hours,
        })

    logger.info("Prepared %d Voyage records from %s", len(records), file_path.name)
    return execute_batched_query(client, VOYAGES_CYPHER, records, batch_size=batch_size, dry_run=dry_run)

