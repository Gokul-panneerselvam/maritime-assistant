import logging
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver, Session
from knowledge_graph.config import Neo4jConfig

logger = logging.getLogger(__name__)

class Neo4jClient:
    """Manages connection and transaction execution with Neo4j."""

    def __init__(self, config: Optional[Neo4jConfig] = None):
        self.config = config or Neo4jConfig()
        self._driver: Optional[Driver] = None

    def connect(self) -> Driver:
        """Establishes driver connection and verifies connectivity."""
        if not self._driver:
            logger.info("Connecting to Neo4j at %s as user '%s'...", self.config.uri, self.config.user)
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password)
            )
            self.verify_connectivity()
        return self._driver

    def verify_connectivity(self) -> bool:
        """Verifies that the server is reachable and credentials are valid."""
        if not self._driver:
            self.connect()
        try:
            self._driver.verify_connectivity()
            logger.info("Successfully connected to Neo4j database.")
            return True
        except Exception as e:
            logger.error("Failed to connect to Neo4j: %s", e)
            raise

    def get_session(self) -> Session:
        """Returns a session for the configured database."""
        if not self._driver:
            self.connect()
        return self._driver.session(database=self.config.database)

    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Executes a single Cypher query and returns the records as dictionaries."""
        with self.get_session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def execute_read_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Executes a query inside an explicit read-only transaction."""
        with self.get_session() as session:
            def _read_tx(tx):
                result = tx.run(query, parameters or {})
                return [record.data() for record in result]
            return session.execute_read(_read_tx)

    def execute_batch(self, query: str, batch: List[Dict[str, Any]]) -> None:
        """Executes a batch Cypher query using UNWIND in a managed write transaction."""
        if not batch:
            return

        with self.get_session() as session:
            def _write_tx(tx):
                tx.run(query, {"batch": batch})

            session.execute_write(_write_tx)

    def get_graph_counts(self) -> Dict[str, Any]:
        """Returns node and relationship counts for verification."""
        with self.get_session() as session:
            node_counts = session.run(
                """
                CALL db.labels() YIELD label
                CALL apoc.cypher.run('MATCH (n:`' + label + '`) RETURN count(n) AS count', {}) YIELD value
                RETURN label, value.count AS count
                """
            )
            # Fallback if APOC is not installed
            try:
                nodes = {record["label"]: record["count"] for record in node_counts}
            except Exception:
                # Query each label individually using standard Cypher
                label_res = session.run("CALL db.labels() YIELD label RETURN label")
                labels = [r["label"] for r in label_res]
                nodes = {}
                for lbl in labels:
                    cnt_res = session.run(f"MATCH (n:`{lbl}`) RETURN count(n) AS cnt")
                    nodes[lbl] = cnt_res.single()["cnt"]

            rel_res = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
            rel_types = [r["relationshipType"] for r in rel_res]
            relationships = {}
            for rel in rel_types:
                cnt_res = session.run(f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS cnt")
                relationships[rel] = cnt_res.single()["cnt"]

            total_nodes = session.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]

            return {
                "total_nodes": total_nodes,
                "total_relationships": total_rels,
                "nodes_by_label": nodes,
                "relationships_by_type": relationships
            }

    def clear_database(self) -> None:
        """Detaches and deletes all nodes and relationships."""
        logger.warning("Clearing entire Neo4j database...")
        with self.get_session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Database cleared.")

    def close(self) -> None:
        """Closes the driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

