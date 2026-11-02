"""
Message Loader Package for Maritime Knowledge Graph.

Provides the LangGraph workflow, nodes, and runner for parsing, standardizing,
and ingesting unstructured maritime communications into the Neo4j Knowledge Graph.
"""

from knowledge_graph.kg_loader.message_loader.graph import create_message_loader_graph
from knowledge_graph.kg_loader.message_loader.reporter import generate_ingestion_report
from knowledge_graph.kg_loader.message_loader.runner import run_message_batch
from knowledge_graph.kg_loader.message_loader.state import (
    DateSpan,
    MessageLoaderState,
    ReplacementSpan,
)

__all__ = [
    "create_message_loader_graph",
    "generate_ingestion_report",
    "run_message_batch",
    "MessageLoaderState",
    "ReplacementSpan",
    "DateSpan",
]

