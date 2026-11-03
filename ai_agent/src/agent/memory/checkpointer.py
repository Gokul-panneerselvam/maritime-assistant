"""
LangGraph Checkpointing Configuration for Maritime Operations AI Agent.
Provides an async-compatible SQLite checkpointer using aiosqlite and AsyncSqliteSaver.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Optional, Sequence

import aiosqlite
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    DeltaChannelHistory,
)
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

STORAGE_DIR = (Path(__file__).resolve().parents[3] / "storage").resolve()
CHECKPOINT_DB_PATH = STORAGE_DIR / "checkpoints.db"


def _sanitize_for_msgpack(obj: Any) -> Any:
    """Recursively converts non-msgpack serializable types (Neo4j DateTime/Date) to strings/primitives."""
    if obj is None:
        return None
    if hasattr(obj, "to_native"):
        native = obj.to_native()
        if hasattr(native, "isoformat"):
            return native.isoformat()
        return str(native)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_msgpack(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_msgpack(item) for item in obj]
    return obj


class AsyncSqliteCheckpointer(BaseCheckpointSaver[str]):
    """
    Asynchronous SQLite checkpointer proxy for LangGraph.
    
    Lazily binds to the running asyncio loop on first execution, opens a connection
    via aiosqlite to `storage/checkpoints.db`, and delegates all checkpoint operations
    to `AsyncSqliteSaver`.
    """

    def __init__(self, db_path: Path = CHECKPOINT_DB_PATH):
        super().__init__()
        self.db_path = str(db_path)
        self._saver: Optional[AsyncSqliteSaver] = None
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock: Optional[asyncio.Lock] = None

    async def _get_saver(self) -> AsyncSqliteSaver:
        """Initializes the aiosqlite connection and AsyncSqliteSaver on the active event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            if self._saver is None:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                self._conn = await aiosqlite.connect(self.db_path)
                self._saver = AsyncSqliteSaver(self._conn)
                await self._saver.setup()
            return self._saver

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        saver = await self._get_saver()
        return await saver.aget_tuple(config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        saver = await self._get_saver()
        sanitized_cp = dict(checkpoint)
        if "channel_values" in sanitized_cp:
            sanitized_cp["channel_values"] = _sanitize_for_msgpack(sanitized_cp["channel_values"])
        return await saver.aput(config, sanitized_cp, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        saver = await self._get_saver()
        sanitized_writes = [(k, _sanitize_for_msgpack(v)) for k, v in writes]
        return await saver.aput_writes(config, sanitized_writes, task_id, task_path)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        saver = await self._get_saver()
        async for item in saver.alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def aget_delta_channel_history(
        self,
        config: RunnableConfig,
        channels: Sequence[str],
    ) -> Optional[DeltaChannelHistory]:
        saver = await self._get_saver()
        return await saver.aget_delta_channel_history(config, channels)

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        if self._saver is not None:
            return self._saver.get_tuple(config)
        return None

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        if self._saver is not None:
            sanitized_cp = dict(checkpoint)
            if "channel_values" in sanitized_cp:
                sanitized_cp["channel_values"] = _sanitize_for_msgpack(sanitized_cp["channel_values"])
            return self._saver.put(config, sanitized_cp, metadata, new_versions)
        return config

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        if self._saver is not None:
            sanitized_writes = [(k, _sanitize_for_msgpack(v)) for k, v in writes]
            self._saver.put_writes(config, sanitized_writes, task_id, task_path)

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        if self._saver is not None:
            yield from self._saver.list(config, filter=filter, before=before, limit=limit)

    async def close(self) -> None:
        """Closes the underlying aiosqlite connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            self._saver = None


_checkpointer_instance: Optional[AsyncSqliteCheckpointer] = None


def get_checkpointer() -> AsyncSqliteCheckpointer:
    """Creates and returns persistent Async SQLite checkpointer for LangGraph StateGraph."""
    global _checkpointer_instance
    if _checkpointer_instance is None:
        _checkpointer_instance = AsyncSqliteCheckpointer(CHECKPOINT_DB_PATH)
    return _checkpointer_instance


__all__ = [
    "AsyncSqliteSaver",
    "AsyncSqliteCheckpointer",
    "get_checkpointer",
    "STORAGE_DIR",
    "CHECKPOINT_DB_PATH",
]
