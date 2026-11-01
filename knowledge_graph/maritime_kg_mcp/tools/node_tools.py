import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

# Strict regex to ensure labels and relationship types are safe against Cypher injection
IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Complete schema registry for the 13 Maritime Knowledge Graph node labels
NODE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "Vessel": {
        "pk": "vessel_id",
        "unique_keys": ["vessel_id", "imo"],
        "required_on_create": ["vessel_id", "name"],
        "allowed_properties": {"vessel_id", "name", "imo"},
        "datetime_properties": set(),
        "int_properties": {"imo"},
    },
    "VesselType": {
        "pk": "type_id",
        "unique_keys": ["type_id"],
        "required_on_create": ["type_id", "name"],
        "allowed_properties": {"type_id", "name", "description"},
        "datetime_properties": set(),
    },
    "VesselClass": {
        "pk": "class_id",
        "unique_keys": ["class_id"],
        "required_on_create": ["class_id", "name"],
        "allowed_properties": {"class_id", "name", "nominal_capacity_teu"},
        "datetime_properties": set(),
        "int_properties": {"nominal_capacity_teu"},
    },
    "TechnicalManager": {
        "pk": "manager_id",
        "unique_keys": ["manager_id"],
        "required_on_create": ["manager_id", "name"],
        "allowed_properties": {"manager_id", "name", "contact_email"},
        "datetime_properties": set(),
    },
    "Port": {
        "pk": "port_code",
        "unique_keys": ["port_code"],
        "required_on_create": ["port_code", "name"],
        "allowed_properties": {"port_code", "name", "country", "timezone"},
        "datetime_properties": set(),
    },
    "Voyage": {
        "pk": "voyage_id",
        "unique_keys": ["voyage_id"],
        "required_on_create": ["voyage_id"],
        "allowed_properties": {
            "voyage_id", "vessel_id", "origin", "destination",
            "departure_local", "departure_utc",
            "original_eta_local", "original_eta_utc",
            "revised_eta_local", "revised_eta_utc",
            "berth_window_start_local", "berth_window_start_utc",
            "berth_window_end_local", "berth_window_end_utc",
            "status", "recorded_delay_hours"
        },
        "datetime_properties": {
            "departure_utc", "original_eta_utc", "revised_eta_utc",
            "berth_window_start_utc", "berth_window_end_utc"
        },
        "float_properties": {"recorded_delay_hours"},
    },
    "PortCall": {
        "pk": "call_id",
        "unique_keys": ["call_id"],
        "required_on_create": ["call_id"],
        "allowed_properties": {
            "call_id", "voyage_id", "vessel_id", "port", "call_type",
            "anchorage_arrival_utc", "berth_scheduled_utc",
            "berthing_utc", "departure_utc",
            "anchorage_wait_hours", "port_stay_hours"
        },
        "datetime_properties": {
            "anchorage_arrival_utc", "berth_scheduled_utc",
            "berthing_utc", "departure_utc"
        },
        "float_properties": {"anchorage_wait_hours", "port_stay_hours"},
    },
    "Incident": {
        "pk": "incident_id",
        "unique_keys": ["incident_id"],
        "required_on_create": ["incident_id", "type"],
        "allowed_properties": {
            "incident_id", "voyage_id", "type", "status", "severity",
            "reported_utc", "source", "attributed_delay_hours", "component", "description"
        },
        "datetime_properties": {"reported_utc"},
        "float_properties": {"attributed_delay_hours"},
    },
    "Congestion": {
        "pk": "congestion_id",
        "unique_keys": ["congestion_id"],
        "required_on_create": ["congestion_id", "date_utc"],
        "allowed_properties": {
            "congestion_id", "port", "date_utc", "congestion_level",
            "avg_wait_hours", "vessels_at_anchor", "source"
        },
        "datetime_properties": {"date_utc"},
        "float_properties": {"avg_wait_hours"},
        "int_properties": {"vessels_at_anchor"},
    },
    "Booking": {
        "pk": "booking_id",
        "unique_keys": ["booking_id"],
        "required_on_create": ["booking_id"],
        "allowed_properties": {
            "booking_id", "customer", "voyage_id", "containers",
            "status", "promised_delivery_date_utc", "is_rolled"
        },
        "datetime_properties": {"promised_delivery_date_utc"},
        "int_properties": {"containers"},
        "bool_properties": {"is_rolled"},
    },
    "Customer": {
        "pk": "customer_id",
        "unique_keys": ["customer_id"],
        "required_on_create": ["customer_id", "name"],
        "allowed_properties": {"customer_id", "name", "industry_segment"},
        "datetime_properties": set(),
    },
    "Organization": {
        "pk": "org_id",
        "unique_keys": ["org_id"],
        "required_on_create": ["org_id", "name"],
        "allowed_properties": {"org_id", "name", "org_type"},
        "datetime_properties": set(),
    },
    "Message": {
        "pk": "message_id",
        "unique_keys": ["message_id"],
        "required_on_create": ["message_id", "sender", "subject"],
        "allowed_properties": {
            "message_id", "filename", "message_type", "message_kind",
            "trust_tier", "sender", "recipient", "sent_at_utc",
            "in_snapshot", "subject", "cleaned_body", "raw_message",
            "is_malicious", "injection_excerpt", "extraction_run_id"
        },
        "datetime_properties": {"sent_at_utc"},
        "bool_properties": {"in_snapshot", "is_malicious"},
    },
}

def _validate_identifier(name: str, kind: str = "identifier") -> None:
    """Ensures label or relationship type is a safe alphanumeric string."""
    if not name or not IDENTIFIER_REGEX.match(name):
        raise ValueError(f"Invalid {kind} '{name}'. Must be alphanumeric/underscores only.")

def _serialize_neo4j_value(val: Any) -> Any:
    """Recursively serializes Neo4j DateTime/Date and complex objects into JSON-compatible values."""
    if isinstance(val, dict):
        return {k: _serialize_neo4j_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_serialize_neo4j_value(item) for item in val]
    elif hasattr(val, "isoformat"):
        return val.isoformat()
    elif hasattr(val, "to_native"):
        return val.to_native().isoformat()
    return val

def _normalize_datetime_str(val: Any) -> Optional[str]:
    """Normalizes various datetime strings to ISO UTC format (YYYY-MM-DDTHH:MM:SSZ)."""
    if val is None:
        return None
    val_str = str(val).strip()
    # Strip trailing UTC designation if present
    val_str = re.sub(r"\s+UTC$", "Z", val_str, flags=re.IGNORECASE)
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(val_str.rstrip("Z"), fmt.rstrip("Z"))
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(val_str)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return val_str

def _separate_props(label: str, props: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Separates regular scalar properties from datetime properties for proper Cypher handling.
    """
    meta = NODE_REGISTRY.get(label, {})
    dt_keys = meta.get("datetime_properties", set())
    regular_props: Dict[str, Any] = {}
    datetime_props: Dict[str, str] = {}

    for k, v in props.items():
        if k in dt_keys or k.endswith("_utc"):
            if v is not None:
                datetime_props[k] = _normalize_datetime_str(v)
            else:
                datetime_props[k] = None
        else:
            regular_props[k] = v

    return regular_props, datetime_props

def _create_single_node(
    client: Neo4jClient,
    label: str,
    properties: Dict[str, Any],
    edges: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Internal implementation for creating a single validated node and its edges."""
    _validate_identifier(label, "node label")
    meta = NODE_REGISTRY.get(label, {})
    pk_field = meta.get("pk", "id")

    # 1. Attribute constraint validation (required fields)
    required_keys = meta.get("required_on_create", [pk_field])
    missing = [k for k in required_keys if k not in properties or properties[k] is None or properties[k] == ""]
    if missing:
        return {
            "success": False,
            "error": f"AttributeConstraintError: Missing required attributes {missing} for node label '{label}'."
        }

    pk_val = properties[pk_field]

    # 2. Duplicate Check: Primary Key
    dup_query = f"MATCH (n:{label} {{{pk_field}: $val}}) RETURN count(n) AS cnt"
    records = client.execute_query(dup_query, {"val": pk_val})
    if records and records[0].get("cnt", 0) > 0:
        return {
            "success": False,
            "error": f"DuplicateNodeError: A node with label '{label}' and {pk_field}='{pk_val}' already exists. Use 'update_nodes' to modify existing nodes.",
            "node_label": label,
            "primary_key": pk_field,
            "primary_key_value": pk_val,
        }

    # Duplicate Check: Alternate unique keys (e.g., Vessel.imo)
    for ukey in meta.get("unique_keys", []):
        if ukey != pk_field and ukey in properties and properties[ukey] is not None:
            uval = properties[ukey]
            dup_ukey_q = f"MATCH (n:{label} {{{ukey}: $val}}) RETURN n.{pk_field} AS existing_pk LIMIT 1"
            res = client.execute_query(dup_ukey_q, {"val": uval})
            if res and len(res) > 0:
                existing_pk = res[0].get("existing_pk")
                return {
                    "success": False,
                    "error": f"DuplicateNodeError: A node with label '{label}' and unique attribute '{ukey}'={uval} already exists (primary key '{existing_pk}').",
                    "node_label": label,
                    "conflicting_key": ukey,
                    "conflicting_value": uval,
                }

    # 3. Create the Node in Neo4j
    regular_props, datetime_props = _separate_props(label, properties)

    set_clauses = ["SET n += $props"]
    cypher_params = {"props": regular_props}

    for dt_k, dt_v in datetime_props.items():
        if dt_v is not None:
            set_clauses.append(f"SET n.{dt_k} = datetime(${dt_k})")
            cypher_params[dt_k] = dt_v
        else:
            set_clauses.append(f"SET n.{dt_k} = null")

    create_cypher = f"""
    CREATE (n:{label})
    {chr(10).join(set_clauses)}
    RETURN properties(n) AS props, elementId(n) AS element_id
    """
    created_res = client.execute_query(create_cypher, cypher_params)
    if not created_res:
        return {"success": False, "error": f"Failed to create node '{label}' in graph database."}

    node_data = created_res[0].get("props", {})
    element_id = created_res[0].get("element_id")

    # 4. Process Edge Additions
    created_edges: List[Dict[str, Any]] = []
    failed_edges: List[Dict[str, Any]] = []

    if edges:
        for edge in edges:
            rel_type = edge.get("relationship_type", "").strip()
            target_label = edge.get("target_label", "").strip()
            target_value = edge.get("target_value")
            direction = edge.get("direction", "OUTGOING").upper().strip()
            edge_props = edge.get("properties") or {}

            if not rel_type or not target_label or target_value is None:
                failed_edges.append({
                    "edge": edge,
                    "reason": "Missing required edge fields ('relationship_type', 'target_label', 'target_value')."
                })
                continue

            try:
                _validate_identifier(rel_type, "relationship type")
                _validate_identifier(target_label, "target label")
            except ValueError as e:
                failed_edges.append({"edge": edge, "reason": str(e)})
                continue

            target_meta = NODE_REGISTRY.get(target_label, {})
            target_key = edge.get("target_key") or target_meta.get("pk", "id")
            _validate_identifier(target_key, "target key")

            # Check if target exists
            target_check_q = f"MATCH (t:{target_label} {{{target_key}: $tval}}) RETURN count(t) AS cnt"
            t_res = client.execute_query(target_check_q, {"tval": target_value})
            if not t_res or t_res[0].get("cnt", 0) == 0:
                failed_edges.append({
                    "relationship_type": rel_type,
                    "target_label": target_label,
                    "target_key": target_key,
                    "target_value": target_value,
                    "reason": f"Target node ({target_label} {{{target_key}: '{target_value}'}}) does not exist."
                })
                continue

            # Build edge creation cypher
            edge_reg_props, edge_dt_props = _separate_props("Edge", edge_props)
            edge_sets = ["SET r += $edge_props"]
            edge_params = {
                "pk_val": pk_val,
                "tval": target_value,
                "edge_props": edge_reg_props
            }
            for dt_k, dt_v in edge_dt_props.items():
                if dt_v is not None:
                    edge_sets.append(f"SET r.{dt_k} = datetime(${dt_k})")
                    edge_params[dt_k] = dt_v

            set_str = " ".join(edge_sets)
            if direction == "INCOMING":
                link_cypher = f"""
                MATCH (n:{label} {{{pk_field}: $pk_val}}), (t:{target_label} {{{target_key}: $tval}})
                MERGE (t)-[r:{rel_type}]->(n)
                {set_str}
                RETURN type(r) AS rel_type, properties(r) AS rel_props
                """
            else:
                link_cypher = f"""
                MATCH (n:{label} {{{pk_field}: $pk_val}}), (t:{target_label} {{{target_key}: $tval}})
                MERGE (n)-[r:{rel_type}]->(t)
                {set_str}
                RETURN type(r) AS rel_type, properties(r) AS rel_props
                """

            edge_res = client.execute_query(link_cypher, edge_params)
            if edge_res:
                created_edges.append({
                    "relationship_type": rel_type,
                    "direction": direction,
                    "target_label": target_label,
                    "target_key": target_key,
                    "target_value": target_value,
                    "properties": _serialize_neo4j_value(edge_res[0].get("rel_props", {}))
                })

    return {
        "success": True,
        "action": "create_node",
        "node": {
            "label": label,
            "primary_key": pk_field,
            "primary_key_value": pk_val,
            "element_id": element_id,
            "properties": _serialize_neo4j_value(node_data),
        },
        "created_edges": created_edges,
        "failed_edges": failed_edges,
        "summary": (
            f"Successfully created {label} node ({pk_field}='{pk_val}') with {len(created_edges)} edge(s)."
            + (f" ({len(failed_edges)} edge(s) failed)." if failed_edges else "")
        )
    }

def create_nodes(
    client: Neo4jClient,
    label: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    nodes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Creates new nodes in the Maritime Knowledge Graph with duplicate checks and attribute constraints.
    Supports single-node creation or batch creation via 'nodes' parameter.
    Returns the created node details and edges for downstream agent reasoning.
    """
    # Batch creation
    if nodes is not None and isinstance(nodes, list):
        created_list: List[Dict[str, Any]] = []
        errors_list: List[Dict[str, Any]] = []

        for idx, item in enumerate(nodes):
            n_label = item.get("label")
            n_props = item.get("properties") or {}
            n_edges = item.get("edges")
            if not n_label:
                errors_list.append({"index": idx, "error": "Missing 'label' in node payload."})
                continue
            res = _create_single_node(client, n_label, n_props, n_edges)
            if res.get("success"):
                created_list.append(res)
            else:
                errors_list.append({"index": idx, "label": n_label, "error": res.get("error")})

        return {
            "success": len(errors_list) == 0,
            "action": "batch_create_nodes",
            "total_requested": len(nodes),
            "total_created": len(created_list),
            "total_errors": len(errors_list),
            "created_nodes": [c["node"] for c in created_list],
            "results": created_list,
            "errors": errors_list,
            "summary": f"Batch create completed: {len(created_list)} succeeded, {len(errors_list)} failed."
        }

    # Single node creation
    if not label or properties is None:
        return {
            "success": False,
            "error": "Invalid arguments: 'label' and 'properties' are required for single node creation. Alternatively pass 'nodes' list."
        }

    return _create_single_node(client, label, properties, edges)

def _update_single_node(
    client: Neo4jClient,
    label: str,
    key_value: Any,
    key_field: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    edges: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Internal implementation for updating an existing validated node and adding/updating edges."""
    _validate_identifier(label, "node label")
    meta = NODE_REGISTRY.get(label, {})
    lookup_field = key_field or meta.get("pk", "id")
    _validate_identifier(lookup_field, "lookup key field")

    # 1. Existence Check: Node MUST exist
    check_q = f"MATCH (n:{label} {{{lookup_field}: $val}}) RETURN properties(n) AS props, elementId(n) AS element_id"
    exists_res = client.execute_query(check_q, {"val": key_value})
    if not exists_res:
        return {
            "success": False,
            "error": (
                f"NodeNotFoundError: Node ({label} {{{lookup_field}: '{key_value}'}}) does not exist in the graph. "
                f"'update_nodes' only updates existing valid nodes. Use 'create_nodes' to add new nodes."
            ),
            "node_label": label,
            "key_field": lookup_field,
            "key_value": key_value,
        }

    element_id = exists_res[0].get("element_id")
    current_props = exists_res[0].get("props", {})

    # 2. Update Properties (if provided)
    updated_keys: List[str] = []
    if properties:
        regular_props, datetime_props = _separate_props(label, properties)
        set_clauses = ["SET n += $props"]
        cypher_params = {"val": key_value, "props": regular_props}

        for dt_k, dt_v in datetime_props.items():
            if dt_v is not None:
                set_clauses.append(f"SET n.{dt_k} = datetime(${dt_k})")
                cypher_params[dt_k] = dt_v
            else:
                set_clauses.append(f"SET n.{dt_k} = null")

        update_q = f"""
        MATCH (n:{label} {{{lookup_field}: $val}})
        {chr(10).join(set_clauses)}
        RETURN properties(n) AS props
        """
        upd_res = client.execute_query(update_q, cypher_params)
        if upd_res:
            current_props = upd_res[0].get("props", {})
            updated_keys = list(properties.keys())

    # 3. Add / Update Edges
    added_edges: List[Dict[str, Any]] = []
    failed_edges: List[Dict[str, Any]] = []

    if edges:
        for edge in edges:
            rel_type = edge.get("relationship_type", "").strip()
            target_label = edge.get("target_label", "").strip()
            target_value = edge.get("target_value")
            direction = edge.get("direction", "OUTGOING").upper().strip()
            edge_props = edge.get("properties") or {}

            if not rel_type or not target_label or target_value is None:
                failed_edges.append({
                    "edge": edge,
                    "reason": "Missing required edge fields ('relationship_type', 'target_label', 'target_value')."
                })
                continue

            try:
                _validate_identifier(rel_type, "relationship type")
                _validate_identifier(target_label, "target label")
            except ValueError as e:
                failed_edges.append({"edge": edge, "reason": str(e)})
                continue

            target_meta = NODE_REGISTRY.get(target_label, {})
            target_key = edge.get("target_key") or target_meta.get("pk", "id")
            _validate_identifier(target_key, "target key")

            # Verify target node exists
            target_check_q = f"MATCH (t:{target_label} {{{target_key}: $tval}}) RETURN count(t) AS cnt"
            t_res = client.execute_query(target_check_q, {"tval": target_value})
            if not t_res or t_res[0].get("cnt", 0) == 0:
                failed_edges.append({
                    "relationship_type": rel_type,
                    "target_label": target_label,
                    "target_key": target_key,
                    "target_value": target_value,
                    "reason": f"Target node ({target_label} {{{target_key}: '{target_value}'}}) does not exist."
                })
                continue

            # Build edge creation/update cypher
            edge_reg_props, edge_dt_props = _separate_props("Edge", edge_props)
            edge_sets = ["SET r += $edge_props"]
            edge_params = {
                "val": key_value,
                "tval": target_value,
                "edge_props": edge_reg_props
            }
            for dt_k, dt_v in edge_dt_props.items():
                if dt_v is not None:
                    edge_sets.append(f"SET r.{dt_k} = datetime(${dt_k})")
                    edge_params[dt_k] = dt_v

            set_str = " ".join(edge_sets)
            if direction == "INCOMING":
                link_cypher = f"""
                MATCH (n:{label} {{{lookup_field}: $val}}), (t:{target_label} {{{target_key}: $tval}})
                MERGE (t)-[r:{rel_type}]->(n)
                {set_str}
                RETURN type(r) AS rel_type, properties(r) AS rel_props
                """
            else:
                link_cypher = f"""
                MATCH (n:{label} {{{lookup_field}: $val}}), (t:{target_label} {{{target_key}: $tval}})
                MERGE (n)-[r:{rel_type}]->(t)
                {set_str}
                RETURN type(r) AS rel_type, properties(r) AS rel_props
                """

            edge_res = client.execute_query(link_cypher, edge_params)
            if edge_res:
                added_edges.append({
                    "relationship_type": rel_type,
                    "direction": direction,
                    "target_label": target_label,
                    "target_key": target_key,
                    "target_value": target_value,
                    "properties": _serialize_neo4j_value(edge_res[0].get("rel_props", {}))
                })

    # 4. Fetch 360-degree connected relationships
    connected_q = f"""
    MATCH (n:{label} {{{lookup_field}: $val}})
    OPTIONAL MATCH (n)-[r]-(m)
    RETURN type(r) AS rel_type,
           labels(m) AS target_labels,
           properties(m) AS target_properties,
           startNode(r) = n AS is_outgoing,
           properties(r) AS edge_properties
    """
    conn_res = client.execute_query(connected_q, {"val": key_value})
    connected_edges: List[Dict[str, Any]] = []
    if conn_res:
        for row in conn_res:
            if row.get("rel_type") is not None:
                connected_edges.append({
                    "relationship_type": row.get("rel_type"),
                    "direction": "OUTGOING" if row.get("is_outgoing") else "INCOMING",
                    "target_labels": row.get("target_labels", []),
                    "target_properties": _serialize_neo4j_value(row.get("target_properties", {})),
                    "edge_properties": _serialize_neo4j_value(row.get("edge_properties", {}))
                })

    return {
        "success": True,
        "action": "update_node",
        "node": {
            "label": label,
            "primary_key": lookup_field,
            "primary_key_value": key_value,
            "element_id": element_id,
            "updated_attributes": updated_keys,
            "properties": _serialize_neo4j_value(current_props),
        },
        "added_edges": added_edges,
        "failed_edges": failed_edges,
        "connected_edges": connected_edges,
        "summary": (
            f"Successfully updated {label} node ({lookup_field}='{key_value}'): "
            f"updated {len(updated_keys)} attribute(s), added {len(added_edges)} edge(s)."
            + (f" ({len(failed_edges)} edge(s) failed)." if failed_edges else "")
        )
    }

def update_nodes(
    client: Neo4jClient,
    label: Optional[str] = None,
    key_value: Optional[Any] = None,
    key_field: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    nodes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Updates existing valid nodes in the Maritime Knowledge Graph.
    Ensures the target node exists before applying changes (rejects non-existent nodes).
    Supports updating node attributes, creating/updating edges, or batch updating via 'nodes'.
    Returns comprehensive node profile and relationships for downstream agent reasoning.
    """
    # Batch update
    if nodes is not None and isinstance(nodes, list):
        updated_list: List[Dict[str, Any]] = []
        errors_list: List[Dict[str, Any]] = []

        for idx, item in enumerate(nodes):
            n_label = item.get("label")
            n_val = item.get("key_value")
            n_key = item.get("key_field")
            n_props = item.get("properties")
            n_edges = item.get("edges")
            if not n_label or n_val is None:
                errors_list.append({"index": idx, "error": "Missing 'label' or 'key_value' in update payload."})
                continue
            res = _update_single_node(client, n_label, n_val, n_key, n_props, n_edges)
            if res.get("success"):
                updated_list.append(res)
            else:
                errors_list.append({"index": idx, "label": n_label, "key_value": n_val, "error": res.get("error")})

        return {
            "success": len(errors_list) == 0,
            "action": "batch_update_nodes",
            "total_requested": len(nodes),
            "total_updated": len(updated_list),
            "total_errors": len(errors_list),
            "updated_nodes": [u["node"] for u in updated_list],
            "results": updated_list,
            "errors": errors_list,
            "summary": f"Batch update completed: {len(updated_list)} succeeded, {len(errors_list)} failed."
        }

    # Single node update
    if not label or key_value is None:
        return {
            "success": False,
            "error": "Invalid arguments: 'label' and 'key_value' are required for single node update. Alternatively pass 'nodes' list."
        }

    return _update_single_node(client, label, key_value, key_field, properties, edges)

