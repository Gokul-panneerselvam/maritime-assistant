"""
Ingestion Reporter for Maritime Message Loader.

Generates structured JSON and Markdown audit logs saved in `ingestion_report_logs/`.
Captures:
- Ingestion run metrics and execution durations
- Total messages processed, succeeded, failed, skipped
- Adversarial prompt injections detected and quarantined
- Graph mutations: nodes created, nodes updated, edges added
- Granular per-message execution details and ReAct agent decisions
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_REPORT_DIR = Path("ingestion_report_logs")

def generate_ingestion_report(
    run_id: str,
    messages_dir: str,
    results: List[Dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Compiles and writes structured JSON and Markdown audit reports for a message batch ingestion run.

    Args:
        run_id: Unique batch execution identifier.
        messages_dir: Source folder containing ingested message files.
        results: List of MessageLoaderState result dictionaries.
        start_time: Execution start timestamp.
        end_time: Execution end timestamp.
        output_dir: Destination directory for log artifacts (defaults to 'ingestion_report_logs').

    Returns:
        Summary report dictionary.
    """
    report_folder = output_dir or DEFAULT_REPORT_DIR
    report_folder.mkdir(parents=True, exist_ok=True)

    timestamp_str = end_time.strftime("%Y%m%d_%H%M%S")
    duration_sec = round((end_time - start_time).total_seconds(), 2)

    total_discovered = len(results)
    succeeded = sum(1 for r in results if r.get("status") in ("SUCCESS", "PARTIAL_SUCCESS"))
    failed = sum(1 for r in results if r.get("status") == "FAILED")
    skipped = sum(1 for r in results if r.get("status") == "SKIPPED")

    total_malicious = sum(1 for r in results if r.get("is_malicious", False))
    total_messages_created = sum(1 for r in results if r.get("message_node_created", False))

    total_nodes_created = sum(len(r.get("nodes_created", [])) for r in results)
    total_nodes_updated = sum(len(r.get("nodes_updated", [])) for r in results)
    total_edges_added = sum(len(r.get("edges_added", [])) for r in results)

    # Detailed per-message summaries
    message_summaries: List[Dict[str, Any]] = []
    malicious_entries: List[Dict[str, Any]] = []

    for r in results:
        summary_item = {
            "message_id": r.get("message_id"),
            "filename": r.get("filename"),
            "status": r.get("status", "UNKNOWN"),
            "message_type": r.get("message_type"),
            "message_kind": r.get("message_kind"),
            "trust_tier": r.get("trust_tier"),
            "is_malicious": r.get("is_malicious", False),
            "injection_excerpt": r.get("injection_excerpt"),
            "nodes_created_count": len(r.get("nodes_created", [])),
            "nodes_updated_count": len(r.get("nodes_updated", [])),
            "edges_added_count": len(r.get("edges_added", [])),
            "nodes_created": r.get("nodes_created", []),
            "nodes_updated": r.get("nodes_updated", []),
            "edges_added": r.get("edges_added", []),
            "agent_reasoning": r.get("agent_reasoning", ""),
            "errors": r.get("errors", [])
        }
        message_summaries.append(summary_item)

        if r.get("is_malicious"):
            malicious_entries.append({
                "message_id": r.get("message_id"),
                "filename": r.get("filename"),
                "injection_excerpt": r.get("injection_excerpt")
            })

    report_data = {
        "run_id": run_id,
        "timestamp_utc": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": duration_sec,
        "messages_dir": str(messages_dir),
        "metrics": {
            "total_discovered": total_discovered,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "malicious_detected": total_malicious,
            "messages_persisted": total_messages_created,
            "nodes_created": total_nodes_created,
            "nodes_updated": total_nodes_updated,
            "edges_added": total_edges_added,
        },
        "malicious_quarantined": malicious_entries,
        "messages": message_summaries,
    }

    # 1. Save JSON Report
    json_path = report_folder / f"report_{timestamp_str}_{run_id[:8]}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)
    logger.info("Ingestion report JSON saved to: %s", json_path)

    # 2. Save Markdown Report
    md_path = report_folder / f"report_{timestamp_str}_{run_id[:8]}.md"
    md_content = _build_markdown_report(report_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info("Ingestion report Markdown saved to: %s", md_path)

    report_data["json_path"] = str(json_path)
    report_data["md_path"] = str(md_path)
    return report_data

def _build_markdown_report(data: Dict[str, Any]) -> str:
    """Generates a GitHub-flavored Markdown ingestion report."""
    metrics = data["metrics"]
    lines = [
        f"# Maritime Knowledge Graph Ingestion Report",
        f"",
        f"- **Run ID**: `{data['run_id']}`",
        f"- **Timestamp (UTC)**: `{data['timestamp_utc']}`",
        f"- **Duration**: `{data['duration_seconds']}s`",
        f"- **Source Folder**: `{data['messages_dir']}`",
        f"",
        f"## Executive Summary",
        f"",
        f"| Metric | Count |",
        f"| :--- | :--- |",
        f"| **Total Messages Processed** | {metrics['total_discovered']} |",
        f"| **Succeeded** | {metrics['succeeded']} |",
        f"| **Failed** | {metrics['failed']} |",
        f"| **Skipped** | {metrics['skipped']} |",
        f"| **Prompt Injections Quarantined** | {metrics['malicious_detected']} |",
        f"| **Message Nodes Persisted** | {metrics['messages_persisted']} |",
        f"| **Domain Nodes Created** | {metrics['nodes_created']} |",
        f"| **Existing Nodes Updated** | {metrics['nodes_updated']} |",
        f"| **Semantic Edges Attached** | {metrics['edges_added']} |",
        f"",
    ]

    if data.get("malicious_quarantined"):
        lines.extend([
            f"## Security & Adversarial Threat Quarantine",
            f"",
            f"> [!WARNING]",
            f"> The following messages contained prompt injection or jailbreak attempts. They were safely quarantined with `is_malicious = true` and malicious excerpts isolated from entity extraction.",
            f"",
            f"| Message ID | Filename | Quarantined Prompt Excerpt |",
            f"| :--- | :--- | :--- |",
        ])
        for m in data["malicious_quarantined"]:
            excerpt = (m.get("injection_excerpt") or "").replace("\n", " ")[:120]
            lines.append(f"| `{m['message_id']}` | `{m['filename']}` | `{excerpt}...` |")
        lines.append("")

    lines.extend([
        f"## Granular Message Processing Details",
        f"",
        f"| Message ID | Type | Trust Tier | Status | Nodes Created | Nodes Updated | Edges Added | Injected |",
        f"| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for m in data["messages"]:
        mal_flag = "⚠️ YES" if m.get("is_malicious") else "No"
        status_badge = m.get("status", "UNKNOWN")
        lines.append(
            f"| `{m['message_id']}` | {m.get('message_type', 'N/A')} | {m.get('trust_tier', 'N/A')} | "
            f"**{status_badge}** | {m.get('nodes_created_count', 0)} | {m.get('nodes_updated_count', 0)} | "
            f"{m.get('edges_added_count', 0)} | {mal_flag} |"
        )

    # Edge addition details
    has_edges = any(m.get("edges_added") for m in data["messages"])
    if has_edges:
        lines.extend([
            f"",
            f"## Knowledge Graph Relationships Established",
            f"",
            f"| Message ID | Relationship | From Node | To Node | Temporal | Event Time (UTC) |",
            f"| :--- | :--- | :--- | :--- | :---: | :---: |",
        ])
        for m in data["messages"]:
            for e in m.get("edges_added", []):
                rel = e.get("relationship_type") or e.get("rel_type") or e.get("type", "RELATED_TO")
                from_id = e.get("from_id") or m.get("message_id")
                
                target_val = e.get("target_value") or e.get("to_id") or e.get("target_id")
                target_lbl = e.get("target_label", "")
                if target_val:
                    to_id = f"(:{target_lbl} {{{target_val}}})" if target_lbl else str(target_val)
                elif isinstance(e.get("to_node"), dict):
                    to_info = e["to_node"]
                    lbl = to_info.get("label", "")
                    val = next((v for k, v in to_info.items() if k != "label"), "N/A")
                    to_id = f"(:{lbl} {{{val}}})" if lbl else str(val)
                else:
                    to_id = "N/A"

                props = e.get("properties") or {}
                temporal = props.get("temporal") or e.get("temporal", "past")
                etime = props.get("event_time_utc") or e.get("event_time_utc", "N/A")
                lines.append(f"| `{m['message_id']}` | `[:{rel}]` | `(:Message {{{from_id}}})` | `{to_id}` | {temporal} | {etime} |")

    return "\n".join(lines)

