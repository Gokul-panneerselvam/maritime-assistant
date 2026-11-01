import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.loaders.base import read_csv_rows, execute_batched_query
from knowledge_graph.kg_loader.normalizers import slugify, extract_rolled_voyage

logger = logging.getLogger(__name__)

BOOKINGS_CYPHER = """
UNWIND $batch AS row
MERGE (c:Customer {customer_id: row.customer_id})
ON CREATE SET c.name = row.customer_name
ON MATCH SET c.name = row.customer_name

MERGE (b:Booking {booking_id: row.booking_id})
ON CREATE SET
    b.containers = row.containers,
    b.status = row.status,
    b.promised_delivery_date_utc = CASE WHEN row.promised_delivery_date_utc IS NOT NULL THEN date(row.promised_delivery_date_utc) ELSE null END,
    b.is_rolled = row.is_rolled
ON MATCH SET
    b.containers = row.containers,
    b.status = row.status,
    b.promised_delivery_date_utc = CASE WHEN row.promised_delivery_date_utc IS NOT NULL THEN date(row.promised_delivery_date_utc) ELSE null END,
    b.is_rolled = row.is_rolled

MERGE (c)-[:PLACED_BOOKING]->(b)

WITH b, row
MATCH (voy:Voyage {voyage_id: row.voyage_id})
MERGE (b)-[:BOOKED_ON]->(voy)

WITH b, row
WHERE row.rolled_to_voyage_id IS NOT NULL
MATCH (target_voy:Voyage {voyage_id: row.rolled_to_voyage_id})
MERGE (b)-[:ROLLED_TO]->(target_voy)
"""

def load_bookings(
    file_path: Path,
    client: Optional[Neo4jClient] = None,
    batch_size: int = 500,
    dry_run: bool = False
) -> int:
    """
    Ingests bookings.csv into Customer and Booking nodes, links them with [:PLACED_BOOKING],
    [:BOOKED_ON], and conditionally [:ROLLED_TO] for rolled shipments.
    """
    rows = read_csv_rows(file_path)
    records: List[Dict[str, Any]] = []

    for r in rows:
        booking_id = r["booking_id"].strip()
        customer_name = r["customer"].strip()
        voyage_id = r["voyage_id"].strip()
        containers = int(r.get("containers", 0))
        status = r.get("status", "").strip()
        delivery_date = r.get("promised_delivery_date", "").strip() or None

        is_rolled = status.lower().startswith("rolled")
        rolled_to_voyage_id = extract_rolled_voyage(status)

        records.append({
            "booking_id": booking_id,
            "customer_id": slugify(customer_name),
            "customer_name": customer_name,
            "voyage_id": voyage_id,
            "containers": containers,
            "status": status,
            "promised_delivery_date_utc": delivery_date,
            "is_rolled": is_rolled,
            "rolled_to_voyage_id": rolled_to_voyage_id
        })

    logger.info("Prepared %d Booking records from %s", len(records), file_path.name)
    return execute_batched_query(client, BOOKINGS_CYPHER, records, batch_size=batch_size, dry_run=dry_run)

