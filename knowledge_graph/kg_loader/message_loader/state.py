from typing import Any, Dict, List, Optional, TypedDict

class ReplacementSpan(TypedDict):
    raw_text: str
    standardized_text: str

class DateSpan(TypedDict):
    raw_text: str
    inferred_iso_utc: str
    date_type: str

class MessageLoaderState(TypedDict, total=False):
    # --- Input ---
    file_path: str
    filename: str
    message_id: str
    run_id: str

    # --- 1. Extractor Outputs ---
    headers: Dict[str, str]
    raw_body: str
    raw_message: str
    sent_at_utc: str
    is_malicious: bool
    injection_excerpt: Optional[str]

    # --- 2. Entity Resolver Outputs ---
    message_type: str
    message_kind: str
    trust_tier: str
    sender_edge_type: str
    sender_target_label: str
    sender_target_key: str
    sender_target_value: str

    entity_replacements: List[ReplacementSpan]
    date_replacements: List[DateSpan]
    cleaned_body: str

    # --- 3. KG Updator Outputs ---
    message_node_created: bool
    nodes_created: List[Dict[str, Any]]
    nodes_updated: List[Dict[str, Any]]
    edges_added: List[Dict[str, Any]]
    agent_reasoning: str
    status: str
    errors: List[str]

