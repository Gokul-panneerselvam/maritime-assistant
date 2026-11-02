"""
Message Batch Runner for Maritime Operational Messages.

Batch processes message files through the MessageLoaderGraph:
- Discovers messages in a specified directory
- Executes the 3-node LangGraph workflow per message (extractor -> entity_resolver -> kg_updator)
- Ensures idempotency via Neo4j MERGE and pre-existence checks
- Handles prompt injections and malformed messages gracefully
- Generates detailed JSON and Markdown audit logs in `ingestion_report_logs/`
"""

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables (including LangSmith tracing configs)
load_dotenv(override=True)

from knowledge_graph.config import Neo4jConfig
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.message_loader.graph import create_message_loader_graph
from knowledge_graph.kg_loader.message_loader.reporter import generate_ingestion_report

logger = logging.getLogger(__name__)


def check_message_exists_in_kg(client: Neo4jClient, message_id: str) -> bool:
    """Checks whether a Message node already exists in the Knowledge Graph."""
    try:
        q = "MATCH (m:Message {message_id: $message_id}) RETURN count(m) AS cnt"
        records = client.execute_query(q, {"message_id": message_id})
        return bool(records and records[0].get("cnt", 0) > 0)
    except Exception as e:
        logger.warning("Failed to check message existence in KG: %s", e)
        return False

def run_message_batch(
    messages_dir: str | Path,
    output_dir: Optional[str | Path] = None,
    skip_existing: bool = False,
    limit: Optional[int] = None,
    client: Optional[Neo4jClient] = None
) -> Dict[str, Any]:
    """
    Executes batch ingestion of maritime messages through the MessageLoaderGraph.

    Args:
        messages_dir: Path to directory containing raw message files (.txt, .eml, etc.).
        output_dir: Directory where reports should be saved.
        skip_existing: If True, skips files whose message_id already exists in Neo4j.
        limit: Optional maximum number of messages to process.
        client: Optional shared Neo4jClient instance.

    Returns:
        Summary report dictionary.
    """
    messages_path = Path(messages_dir).resolve()
    if not messages_path.exists() or not messages_path.is_dir():
        raise FileNotFoundError(f"Messages directory not found: {messages_path}")

    # Discover candidate files (sorting for deterministic processing order)
    files = sorted([f for f in messages_path.iterdir() if f.is_file()])
    if limit and limit > 0:
        files = files[:limit]

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    start_time = datetime.now(timezone.utc)

    logger.info("Starting message batch ingestion [run_id: %s] on directory: %s (%d files)", run_id, messages_path, len(files))

    # Initialize graph
    graph = create_message_loader_graph()

    # Initialize Neo4j client for skip checks
    neo4j_client = client or Neo4jClient(Neo4jConfig())
    if skip_existing:
        try:
            neo4j_client.connect()
        except Exception as e:
            logger.warning("Could not connect to Neo4j for pre-existence checks: %s", e)

    results: List[Dict[str, Any]] = []

    for idx, file_path in enumerate(files, start=1):
        message_id = file_path.stem
        logger.info("[%d/%d] Processing message: %s (%s)", idx, len(files), message_id, file_path.name)

        # Check existing if skip_existing is enabled
        if skip_existing and check_message_exists_in_kg(neo4j_client, message_id):
            logger.info("Message '%s' already exists in KG. Skipping.", message_id)
            results.append({
                "message_id": message_id,
                "filename": file_path.name,
                "file_path": str(file_path),
                "status": "SKIPPED",
                "message_node_created": False,
                "nodes_created": [],
                "nodes_updated": [],
                "edges_added": [],
                "errors": []
            })
            continue

        initial_state = {
            "file_path": str(file_path),
            "filename": file_path.name,
            "message_id": message_id,
            "run_id": run_id,
            "errors": []
        }

        try:
            run_config = {
                "run_name": f"message_{message_id}",
                "tags": ["message_loader", "maritime_kg", messages_path.name],
                "metadata": {
                    "message_id": message_id,
                    "filename": file_path.name,
                    "run_id": run_id
                }
            }
            state_result = graph.invoke(initial_state, config=run_config)
            status = state_result.get("status") or ("SUCCESS" if not state_result.get("errors") else "PARTIAL_SUCCESS")
            state_result["status"] = status
            results.append(state_result)
            logger.info("Finished '%s' with status: %s", message_id, status)
        except Exception as e:
            logger.error("Fatal error processing message '%s': %s", message_id, e, exc_info=True)
            results.append({
                "message_id": message_id,
                "filename": file_path.name,
                "file_path": str(file_path),
                "status": "FAILED",
                "message_node_created": False,
                "nodes_created": [],
                "nodes_updated": [],
                "edges_added": [],
                "errors": [str(e)]
            })

    end_time = datetime.now(timezone.utc)

    # Generate structured JSON and Markdown audit reports
    report_dest = Path(output_dir) if output_dir else None
    report_data = generate_ingestion_report(
        run_id=run_id,
        messages_dir=str(messages_path),
        results=results,
        start_time=start_time,
        end_time=end_time,
        output_dir=report_dest
    )

    metrics = report_data["metrics"]
    print("=" * 60)
    print("MARITIME MESSAGE INGESTION SUMMARY")
    print("=" * 60)
    print(f"Run ID:            {run_id}")
    print(f"Duration:          {report_data['duration_seconds']}s")
    print(f"Total Discovered:  {metrics['total_discovered']}")
    print(f"Succeeded:         {metrics['succeeded']}")
    print(f"Failed:            {metrics['failed']}")
    print(f"Skipped:           {metrics['skipped']}")
    print(f"Threats Flagged:   {metrics['malicious_detected']}")
    print(f"Messages Persisted:{metrics['messages_persisted']}")
    print(f"Nodes Created:     {metrics['nodes_created']}")
    print(f"Nodes Updated:     {metrics['nodes_updated']}")
    print(f"Edges Added:       {metrics['edges_added']}")
    print(f"JSON Report:       {report_data.get('json_path')}")
    print(f"Markdown Report:   {report_data.get('md_path')}")
    print("=" * 60)

    return report_data

def main():
    """Command-line entrypoint for message ingestion."""
    parser = argparse.ArgumentParser(description="Ingest maritime operational messages into Knowledge Graph.")
    parser.add_argument(
        "--messages-dir",
        "-d",
        default="synthetic_dataset/data/messages/core",
        help="Path to folder containing messages (default: synthetic_dataset/data/messages/core)"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="ingestion_report_logs",
        help="Path to report output directory (default: ingestion_report_logs)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip messages that already exist in Neo4j"
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit number of messages to process"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose DEBUG logging"
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    try:
        report = run_message_batch(
            messages_dir=args.messages_dir,
            output_dir=args.output_dir,
            skip_existing=args.skip_existing,
            limit=args.limit
        )
        sys.exit(0 if report["metrics"]["failed"] == 0 else 1)
    except Exception as e:
        logger.error("Batch execution failed: %s", e, exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
