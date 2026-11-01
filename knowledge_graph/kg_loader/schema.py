import logging
from typing import List
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

CONSTRAINTS: List[str] = [
    # Unique Node Identifier Constraints
    "CREATE CONSTRAINT unique_vessel_id IF NOT EXISTS FOR (v:Vessel) REQUIRE v.vessel_id IS UNIQUE",
    "CREATE CONSTRAINT unique_vessel_imo IF NOT EXISTS FOR (v:Vessel) REQUIRE v.imo IS UNIQUE",
    "CREATE CONSTRAINT unique_vessel_type IF NOT EXISTS FOR (t:VesselType) REQUIRE t.type_id IS UNIQUE",
    "CREATE CONSTRAINT unique_vessel_class IF NOT EXISTS FOR (c:VesselClass) REQUIRE c.class_id IS UNIQUE",
    "CREATE CONSTRAINT unique_tech_manager IF NOT EXISTS FOR (m:TechnicalManager) REQUIRE m.manager_id IS UNIQUE",
    "CREATE CONSTRAINT unique_port_code IF NOT EXISTS FOR (p:Port) REQUIRE p.port_code IS UNIQUE",
    "CREATE CONSTRAINT unique_voyage_id IF NOT EXISTS FOR (voy:Voyage) REQUIRE voy.voyage_id IS UNIQUE",
    "CREATE CONSTRAINT unique_call_id IF NOT EXISTS FOR (pc:PortCall) REQUIRE pc.call_id IS UNIQUE",
    "CREATE CONSTRAINT unique_incident_id IF NOT EXISTS FOR (i:Incident) REQUIRE i.incident_id IS UNIQUE",
    "CREATE CONSTRAINT unique_congestion_id IF NOT EXISTS FOR (cg:Congestion) REQUIRE cg.congestion_id IS UNIQUE",
    "CREATE CONSTRAINT unique_booking_id IF NOT EXISTS FOR (b:Booking) REQUIRE b.booking_id IS UNIQUE",
    "CREATE CONSTRAINT unique_customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
    "CREATE CONSTRAINT unique_org_id IF NOT EXISTS FOR (org:Organization) REQUIRE org.org_id IS UNIQUE",
    "CREATE CONSTRAINT unique_message_id IF NOT EXISTS FOR (msg:Message) REQUIRE msg.message_id IS UNIQUE",
]

INDEXES: List[str] = [
    # Operational Performance Indexes
    "CREATE INDEX voyage_arrival_utc_idx IF NOT EXISTS FOR (voy:Voyage) ON (voy.revised_eta_utc)",
    "CREATE INDEX incident_reported_utc_idx IF NOT EXISTS FOR (i:Incident) ON (i.reported_utc)",
    "CREATE INDEX congestion_date_utc_idx IF NOT EXISTS FOR (cg:Congestion) ON (cg.date_utc)",
    "CREATE INDEX booking_delivery_date_idx IF NOT EXISTS FOR (b:Booking) ON (b.promised_delivery_date_utc)",
    "CREATE INDEX message_sent_at_utc_idx IF NOT EXISTS FOR (msg:Message) ON (msg.sent_at_utc)",
]

def init_schema(client: Neo4jClient) -> None:
    """Applies all constraints and indexes defined in the schema specification."""
    logger.info("Initializing Neo4j schema constraints and indexes...")
    with client.get_session() as session:
        for stmt in CONSTRAINTS:
            try:
                session.run(stmt)
                logger.debug("Applied constraint: %s", stmt)
            except Exception as e:
                logger.warning("Could not apply constraint (%s): %s", stmt, e)

        for stmt in INDEXES:
            try:
                session.run(stmt)
                logger.debug("Applied index: %s", stmt)
            except Exception as e:
                logger.warning("Could not apply index (%s): %s", stmt, e)

    logger.info("Schema initialization complete.")

