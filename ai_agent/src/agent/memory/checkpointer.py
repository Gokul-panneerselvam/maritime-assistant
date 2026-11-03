"""
LangGraph Checkpointing and Persistent Storage Configuration.
"""

import sqlite3
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

STORAGE_DIR = (Path(__file__).resolve().parents[3] / "storage").resolve()

CHECKPOINT_DB_PATH = STORAGE_DIR / "checkpoints.db"


def get_checkpointer() -> SqliteSaver:
    """Creates and returns persistent SQLite checkpointer for LangGraph StateGraph."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
    return SqliteSaver(conn)

