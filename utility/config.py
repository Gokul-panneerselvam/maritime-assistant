"""Central configuration management for the Maritime Assistant system.
Adheres to SOLID principles: Single responsibility for loading and validating configuration.
All environment values are accessed via typed settings rather than scattered os.getenv calls.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file once at module import
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BASE_DIR / "synthetic_dataset" / "data"


@dataclass(frozen=True)
class Neo4jConfig:
    """Configuration for Neo4j database connection."""
    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j")))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "password"))
    database: str = field(default_factory=lambda: os.getenv("NEO4J_DATABASE", "neo4j"))
    max_connection_lifetime_sec: int = 3600
    max_connection_pool_size: int = 50
    connection_timeout_sec: float = 10.0


@dataclass(frozen=True)
class LoggingConfig:
    """Configuration for structured logging."""
    level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    format: str = field(default_factory=lambda: os.getenv("LOG_FORMAT", "json").lower())
    include_extra: bool = True


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for the Maritime KG MCP Server."""
    host: str = field(default_factory=lambda: os.getenv("MCP_SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("MCP_SERVER_PORT", "8000")))
    token: Optional[str] = field(default_factory=lambda: os.getenv("MCP_SERVER_TOKEN"))
    server_url: str = field(default_factory=lambda: os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/sse"))
    query_limit_default: int = 50
    query_limit_max: int = 500


@dataclass(frozen=True)
class DataConfig:
    """Paths to synthetic dataset source CSVs and operational messages."""
    data_dir: Path = DEFAULT_DATA_DIR

    @property
    def ports_csv(self) -> Path:
        return self.data_dir / "ports.csv"

    @property
    def vessels_csv(self) -> Path:
        return self.data_dir / "vessels.csv"

    @property
    def voyages_csv(self) -> Path:
        return self.data_dir / "voyages.csv"

    @property
    def port_calls_csv(self) -> Path:
        return self.data_dir / "port_calls.csv"

    @property
    def incidents_csv(self) -> Path:
        return self.data_dir / "incidents.csv"

    @property
    def congestion_csv(self) -> Path:
        return self.data_dir / "congestion.csv"

    @property
    def bookings_csv(self) -> Path:
        return self.data_dir / "bookings.csv"

    @property
    def messages_core_dir(self) -> Path:
        return self.data_dir / "messages" / "core"


@dataclass(frozen=True)
class AppConfig:
    """Root application configuration aggregating all subsystem settings."""
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    mcp: MCPServerConfig = field(default_factory=MCPServerConfig)
    data: DataConfig = field(default_factory=DataConfig)
    operational_snapshot_utc: str = "2026-10-26T12:00:00Z"


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Thread-safe cached singleton provider for application configuration."""
    return AppConfig()

