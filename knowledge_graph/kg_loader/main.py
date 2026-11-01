import argparse
import logging
import sys
from pathlib import Path

# Enable direct script execution as well as module execution (-m)
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_graph.config import DataConfig, Neo4jConfig
from knowledge_graph.kg_loader.pipeline import IngestionPipeline

def setup_logging(verbose: bool = False):
    """Sets up formatted console logging."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=format_str, datefmt="%Y-%m-%d %H:%M:%S")

def main():
    parser = argparse.ArgumentParser(
        description="Maritime Knowledge Graph CSV Ingestion Pipeline to Neo4j"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Path to synthetic dataset CSV directory (default: synthetic_dataset/data)"
    )
    parser.add_argument(
        "--uri",
        type=str,
        default=None,
        help="Neo4j connection URI (override .env NEO4J_URI)"
    )
    parser.add_argument(
        "--user",
        type=str,
        default=None,
        help="Neo4j username (override .env NEO4J_USER)"
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Neo4j password (override .env NEO4J_PASSWORD)"
    )
    parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="Neo4j database name (override .env NEO4J_DATABASE)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for UNWIND transactions (default: 500)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing database nodes and relationships before ingestion"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse, validate, and compute transformations without connecting to Neo4j"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    neo4j_config = Neo4jConfig()
    if args.uri:
        neo4j_config.uri = args.uri
    if args.user:
        neo4j_config.user = args.user
    if args.password:
        neo4j_config.password = args.password
    if args.database:
        neo4j_config.database = args.database

    data_config = DataConfig()
    if args.data_dir:
        data_config.data_dir = args.data_dir

    pipeline = IngestionPipeline(
        neo4j_config=neo4j_config,
        data_config=data_config,
        batch_size=args.batch_size
    )

    try:
        stats = pipeline.run(dry_run=args.dry_run, clear_db=args.clear)
        print("\n--- Ingestion Summary ---")
        for key, val in stats.items():
            if key != "graph_counts":
                print(f"{key}: {val}")
        if "graph_counts" in stats:
            print("\n--- Graph Database Counts ---")
            print(f"Total Nodes: {stats['graph_counts']['total_nodes']}")
            print(f"Total Relationships: {stats['graph_counts']['total_relationships']}")
            print("Nodes by Label:")
            for lbl, cnt in stats['graph_counts']['nodes_by_label'].items():
                print(f"  {lbl}: {cnt}")
            print("Relationships by Type:")
            for rel, cnt in stats['graph_counts']['relationships_by_type'].items():
                print(f"  {rel}: {cnt}")
        print("-------------------------\n")
    except Exception as e:
        logging.error("Pipeline failed: %s", e, exc_info=args.verbose)
        sys.exit(1)

if __name__ == "__main__":
    main()

