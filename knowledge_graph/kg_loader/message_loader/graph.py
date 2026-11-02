"""
MessageLoaderGraph: 3-node LangGraph workflow for processing maritime operational messages.

Workflow:
  START -> extractor -> entity_resolver -> kg_updator -> END

Nodes:
  1. extractor: Parses RFC headers (From, To, Date, Subject), extracts body, normalizes header date,
     and isolates prompt injections.
  2. entity_resolver: Resolves sender taxonomy, canonicalizes maritime entities in backticks,
     and resolves temporal/date expressions to ISO 8601 UTC in backticks.
  3. kg_updator: Programmatically inserts Message node and sender edge, then runs a ReAct agent
     with read_query, create_nodes, and update_nodes to link and update the KG.
"""

import logging
from langgraph.graph import StateGraph, START, END
from knowledge_graph.kg_loader.message_loader.state import MessageLoaderState
from knowledge_graph.kg_loader.message_loader.nodes.extractor import extractor_node
from knowledge_graph.kg_loader.message_loader.nodes.resolver import entity_resolver_node
from knowledge_graph.kg_loader.message_loader.nodes.updator import kg_updator_node

logger = logging.getLogger(__name__)

def create_message_loader_graph():
    """
    Builds and compiles the 3-node MessageLoaderGraph.

    Returns:
        Compiled StateGraph runnable that accepts MessageLoaderState inputs.
    """
    workflow = StateGraph(MessageLoaderState)

    # Register workflow nodes
    workflow.add_node("extractor", extractor_node)
    workflow.add_node("entity_resolver", entity_resolver_node)
    workflow.add_node("kg_updator", kg_updator_node)

    # Sequential edges
    workflow.add_edge(START, "extractor")
    workflow.add_edge("extractor", "entity_resolver")
    workflow.add_edge("entity_resolver", "kg_updator")
    workflow.add_edge("kg_updator", END)

    logger.info("MessageLoaderGraph initialized and compiled successfully.")
    return workflow.compile()

