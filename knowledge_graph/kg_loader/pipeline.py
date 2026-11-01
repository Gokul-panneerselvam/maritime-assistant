import logging
import time
from typing import Any, Dict, Optional
from knowledge_graph.config import DataConfig, Neo4jConfig
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.schema import init_schema
from knowledge_graph.kg_loader.loaders import (
    load_ports,
    load_vessels,
    load_voyages,
    load_port_calls,
    load_incidents,
    load_congestion,
    load_bookings,
)

logger = logging.getLogger("maritime_agent.pipeline")

class IngestionPipeline:
    """Orchestrates end-to-end ingestion of operational CSV data into Neo4j."""

    def __init__(
        self,
        neo4j_config: Optional[Neo4jConfig] = None,
        data_config: Optional[DataConfig] = None,
        batch_size: int = 500
    ):
        self.neo4j_config = neo4j_config or Neo4jConfig()
        self.data_config = data_config or DataConfig()
        self.batch_size = batch_size

    def run(self, dry_run: bool = False, clear_db: bool = False) -> Dict[str, Any]:
        """
        Executes the full ingestion pipeline.
        If dry_run is True, parses and validates all CSVs without executing database queries.
        """
        start_time = time.time()
        logger.info("=== Starting Maritime Operations Graph Ingestion Pipeline ===")
        logger.info("Data Directory: %s", self.data_config.data_dir)
        logger.info("Dry Run Mode: %s", dry_run)

        stats: Dict[str, Any] = {
            "ports_processed": 0,
            "vessels_processed": 0,
            "voyages_processed": 0,
            "port_calls_processed": 0,
            "incidents_processed": 0,
            "congestion_processed": 0,
            "bookings_processed": 0,
            "dry_run": dry_run,
        }

        client: Optional[Neo4jClient] = None

        try:
            if not dry_run:
                client = Neo4jClient(self.neo4j_config)
                client.connect()

                if clear_db:
                    client.clear_database()

                logger.info("Applying Neo4j schema constraints and indexes...")
                init_schema(client)

            # Step 1: Ports
            logger.info("Step 1/7: Loading Ports...")
            timezones = load_ports(
                self.data_config.ports_csv,
                client=client,
                batch_size=self.batch_size,
                dry_run=dry_run
            )
            stats["ports_processed"] = len(timezones)
            logger.info("Loaded %d ports and timezone mappings.", len(timezones))

            # Step 2: Vessels & Classifications
            logger.info("Step 2/7: Loading Vessels, Types, Classes, and Managers...")
            stats["vessels_processed"] = load_vessels(
                self.data_config.vessels_csv,
                client=client,
                batch_size=self.batch_size,
                dry_run=dry_run
            )

            # Step 3: Voyages (Local -> UTC Normalized)
            logger.info("Step 3/7: Loading Voyages with UTC timezone normalization...")
            stats["voyages_processed"] = load_voyages(
                self.data_config.voyages_csv,
                port_timezones=timezones,
                client=client,
                batch_size=self.batch_size,
                dry_run=dry_run
            )

            # Step 4: Port Calls & Durations
            logger.info("Step 4/7: Loading Port Calls & computing wait/stay metrics...")
            stats["port_calls_processed"] = load_port_calls(
                self.data_config.port_calls_csv,
                client=client,
                batch_size=self.batch_size,
                dry_run=dry_run
            )

            # Step 5: Incidents & Vessel Attribution
            logger.info("Step 5/7: Loading Incidents & attributing to affected Vessels...")
            stats["incidents_processed"] = load_incidents(
                self.data_config.incidents_csv,
                client=client,
                batch_size=self.batch_size,
                dry_run=dry_run
            )

            # Step 6: Congestion Feeds
            logger.info("Step 6/7: Loading Daily Congestion observations...")
            stats["congestion_processed"] = load_congestion(
                self.data_config.congestion_csv,
                client=client,
                batch_size=self.batch_size,
                dry_run=dry_run
            )

            # Step 7: Bookings, Customers, Rolled Shipments
            logger.info("Step 7/7: Loading Bookings, Customers, and Rolled connections...")
            stats["bookings_processed"] = load_bookings(
                self.data_config.bookings_csv,
                client=client,
                batch_size=self.batch_size,
                dry_run=dry_run
            )

            # Verification Step
            if client and not dry_run:
                logger.info("Verifying graph counts...")
                graph_counts = client.get_graph_counts()
                stats["graph_counts"] = graph_counts
                logger.info("Graph verification summary:")
                logger.info("  Total Nodes: %d", graph_counts["total_nodes"])
                logger.info("  Total Relationships: %d", graph_counts["total_relationships"])
                for label, count in graph_counts["nodes_by_label"].items():
                    logger.info("    (:%s): %d", label, count)
                for rel, count in graph_counts["relationships_by_type"].items():
                    logger.info("    [:%s]: %d", rel, count)

            elapsed = time.time() - start_time
            stats["elapsed_seconds"] = round(elapsed, 2)
            logger.info("=== Ingestion Pipeline completed successfully in %.2fs ===", elapsed)
            return stats

        finally:
            if client:
                client.close()

