"""Knowledge Graph Loader package."""
from knowledge_graph.kg_loader.pipeline import IngestionPipeline
from knowledge_graph.kg_loader.schema import init_schema

__all__ = ["IngestionPipeline", "init_schema"]

