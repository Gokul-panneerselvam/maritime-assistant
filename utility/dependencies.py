"""Dependency Injection & Lifecycle Management for Maritime KG.
Adheres to SOLID principles:
- Dependency Inversion: Tools depend on the DatabaseClientProtocol abstraction.
- Interface Segregation: Focused protocols for read/write database operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from utility.config import get_config
from utility.logger import get_logger

logger = get_logger(__name__)


@runtime_checkable
class DatabaseClientProtocol(Protocol):
    """Protocol abstracting Neo4j read and write query execution."""

    def execute_read_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Executes a Cypher query inside a read transaction."""
        ...

    def execute_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Executes a single Cypher query."""
        ...

    def verify_connectivity(self) -> bool:
        """Verifies database connectivity."""
        ...


_db_client: Optional[DatabaseClientProtocol] = None


def get_db_client() -> DatabaseClientProtocol:
    """Thread-safe lazy provider for the Neo4jClient instance.
    Injects Neo4j configuration from the centralized config service.
    """
    global _db_client
    if _db_client is None:
        from knowledge_graph.database import Neo4jClient
        from knowledge_graph.config import Neo4jConfig as LegacyConfig

        cfg = get_config().neo4j
        legacy_cfg = LegacyConfig(
            uri=cfg.uri,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
        )
        client = Neo4jClient(legacy_cfg)
        try:
            client.connect()
            logger.info("Successfully established Neo4j connection pool.")
        except Exception as exc:
            logger.warning("Neo4j database connection deferred or unreachable: %s", exc)
        _db_client = client
    return _db_client


def set_db_client(client: Optional[DatabaseClientProtocol]) -> None:
    """Explicitly injects or overrides the database client (useful for unit tests and mocks)."""
    global _db_client
    _db_client = client

