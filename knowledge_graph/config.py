from dataclasses import dataclass, field
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BASE_DIR / "synthetic_dataset" / "data"

@dataclass
class Neo4jConfig:
    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j")))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "password"))
    database: str = field(default_factory=lambda: os.getenv("NEO4J_DATABASE", "neo4j"))

@dataclass
class DataConfig:
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

