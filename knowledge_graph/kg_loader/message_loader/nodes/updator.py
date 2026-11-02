import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from knowledge_graph.config import Neo4jConfig
from knowledge_graph.database import Neo4jClient
from knowledge_graph.maritime_kg_mcp.tools.cypher_tool import execute_read_cypher
from knowledge_graph.maritime_kg_mcp.tools.node_tools import create_nodes, update_nodes
from knowledge_graph.kg_loader.message_loader.llm_factory import get_chat_llm
from knowledge_graph.kg_loader.message_loader.prompts_loader import get_prompt_template
from knowledge_graph.kg_loader.message_loader.state import MessageLoaderState

logger = logging.getLogger(__name__)

def _get_client() -> Neo4jClient:
    """Returns connected Neo4jClient instance."""
    client = Neo4jClient(Neo4jConfig())
    client.connect()
    return client

def _insert_message_node_and_sender(
    client: Neo4jClient,
    state: MessageLoaderState,
    run_id: str
) -> None:
    """Programmatically inserts/merges the Message node and connects its sender relationship."""
    message_id = state["message_id"]
    filename = state.get("filename", f"{message_id}.txt")
    message_type = state.get("message_type", "Agent email")
    message_kind = state.get("message_kind", "agent_email")
    trust_tier = state.get("trust_tier", "T2")
    headers = state.get("headers", {})
    sender = headers.get("From", "Unknown")
    recipient = headers.get("To", "Unknown")
    sent_at_utc = state.get("sent_at_utc")
    subject = headers.get("Subject", "")
    cleaned_body = state.get("cleaned_body", "")
    raw_message = state.get("raw_message", "")
    is_malicious = bool(state.get("is_malicious", False))
    injection_excerpt = state.get("injection_excerpt")

    # 1. Merge Message Node
    merge_cypher = """
    MERGE (msg:Message {message_id: $message_id})
    ON CREATE SET
        msg.filename = $filename,
        msg.message_type = $message_type,
        msg.message_kind = $message_kind,
        msg.trust_tier = $trust_tier,
        msg.sender = $sender,
        msg.recipient = $recipient,
        msg.sent_at_utc = CASE WHEN $sent_at_utc IS NOT NULL THEN datetime($sent_at_utc) ELSE null END,
        msg.subject = $subject,
        msg.cleaned_body = $cleaned_body,
        msg.raw_message = $raw_message,
        msg.is_malicious = $is_malicious,
        msg.injection_excerpt = $injection_excerpt,
        msg.extraction_run_id = $run_id,
        msg.created_at = datetime()
    ON MATCH SET
        msg.message_type = $message_type,
        msg.message_kind = $message_kind,
        msg.trust_tier = $trust_tier,
        msg.cleaned_body = $cleaned_body,
        msg.is_malicious = $is_malicious,
        msg.injection_excerpt = $injection_excerpt,
        msg.extraction_run_id = $run_id,
        msg.updated_at = datetime()
    """
    client.execute_query(merge_cypher, {
        "message_id": message_id,
        "filename": filename,
        "message_type": message_type,
        "message_kind": message_kind,
        "trust_tier": trust_tier,
        "sender": sender,
        "recipient": recipient,
        "sent_at_utc": sent_at_utc,
        "subject": subject,
        "cleaned_body": cleaned_body,
        "raw_message": raw_message,
        "is_malicious": is_malicious,
        "injection_excerpt": injection_excerpt,
        "run_id": run_id
    })

    # 2. Establish Sender Edge (Idempotent MERGE)
    sender_edge = state.get("sender_edge_type")
    target_label = state.get("sender_target_label")
    target_val = state.get("sender_target_value")

    if sender_edge and target_label and target_val:
        if target_label == "Organization":
            org_slug = target_val.lower().replace(" ", "-").replace(",", "")
            link_q = f"""
            MATCH (msg:Message {{message_id: $message_id}})
            MERGE (org:Organization {{org_id: $org_id}})
            ON CREATE SET org.name = $org_name, org.org_type = 'port_agent'
            MERGE (msg)-[r:{sender_edge}]->(org)
            SET r.temporal = 'past',
                r.event_time_utc = CASE WHEN $sent_at_utc IS NOT NULL THEN datetime($sent_at_utc) ELSE null END
            """
            client.execute_query(link_q, {
                "message_id": message_id,
                "org_id": org_slug,
                "org_name": sender.split(",")[0].strip(),
                "sent_at_utc": sent_at_utc
            })
        elif target_label == "Vessel":
            link_q = f"""
            MATCH (msg:Message {{message_id: $message_id}})
            MATCH (v:Vessel)
            WHERE toLower(v.name) CONTAINS toLower($vname) OR toLower($vname) CONTAINS toLower(v.name)
            WITH msg, v LIMIT 1
            MERGE (msg)-[r:{sender_edge}]->(v)
            SET r.temporal = 'past',
                r.event_time_utc = CASE WHEN $sent_at_utc IS NOT NULL THEN datetime($sent_at_utc) ELSE null END
            """
            client.execute_query(link_q, {
                "message_id": message_id,
                "vname": target_val,
                "sent_at_utc": sent_at_utc
            })
        elif target_label == "TechnicalManager":
            link_q = f"""
            MATCH (msg:Message {{message_id: $message_id}})
            MERGE (tm:TechnicalManager {{manager_id: $manager_id}})
            ON CREATE SET tm.name = $tm_name
            MERGE (msg)-[r:{sender_edge}]->(tm)
            SET r.temporal = 'past',
                r.event_time_utc = CASE WHEN $sent_at_utc IS NOT NULL THEN datetime($sent_at_utc) ELSE null END
            """
            client.execute_query(link_q, {
                "message_id": message_id,
                "manager_id": target_val,
                "tm_name": sender.split(",")[0].strip(),
                "sent_at_utc": sent_at_utc
            })
        elif target_label == "Customer":
            link_q = f"""
            MATCH (msg:Message {{message_id: $message_id}})
            MERGE (c:Customer {{customer_id: $customer_id}})
            ON CREATE SET c.name = $cust_name
            MERGE (msg)-[r:{sender_edge}]->(c)
            SET r.temporal = 'past',
                r.event_time_utc = CASE WHEN $sent_at_utc IS NOT NULL THEN datetime($sent_at_utc) ELSE null END
            """
            client.execute_query(link_q, {
                "message_id": message_id,
                "customer_id": target_val,
                "cust_name": sender.split("<")[0].strip(),
                "sent_at_utc": sent_at_utc
            })

def _fetch_graph_context_for_message(
    client: Neo4jClient,
    body: str,
    entities: List[Dict[str, Any]]
) -> str:
    """Pre-queries Knowledge Graph for existing voyages, vessels, and incidents mentioned in message."""
    voyages = list(set(re.findall(r"VG-\d+", body)))
    vessels = list(set(re.findall(r"MV [A-Z][a-zA-Z ]+", body)))

    for ent in entities:
        std = ent.get("standardized_text", "").strip("`")
        if re.match(r"^VG-\d+", std) and std not in voyages:
            voyages.append(std)
        elif std.startswith("MV ") and std not in vessels:
            vessels.append(std)

    context_lines: List[str] = []
    for vid in voyages:
        try:
            q = """
            MATCH (v:Voyage {voyage_id: $vid})
            OPTIONAL MATCH (v)<-[:OPERATES_VOYAGE]-(ves:Vessel)
            OPTIONAL MATCH (v)-[:EXPERIENCED_INCIDENT]->(i:Incident)
            RETURN v.voyage_id AS voyage_id, v.status AS status, v.recorded_delay_hours AS delay,
                   ves.name AS vessel_name, ves.vessel_id AS vessel_id,
                   collect({
                       incident_id: i.incident_id,
                       type: i.type,
                       status: i.status,
                       delay_hours: i.attributed_delay_hours,
                       component: i.component
                   }) AS incidents
            """
            recs = client.execute_query(q, {"vid": vid})
            if recs and recs[0].get("voyage_id"):
                r = recs[0]
                incs = [inc for inc in r.get("incidents", []) if inc.get("incident_id")]
                context_lines.append(
                    f"Voyage: {r['voyage_id']} (Status: {r['status']}, Delay: {r['delay']}h, Assigned Vessel: {r.get('vessel_name')} [vessel_id: '{r.get('vessel_id')}'])"
                )
                if incs:
                    inc_str = "; ".join([
                        f"{inc['incident_id']} (type: '{inc['type']}', delay: {inc['delay_hours']}h, status: '{inc['status']}')"
                        for inc in incs
                    ])
                    context_lines.append(f"  Existing Incidents for {r['voyage_id']}: {inc_str}")
                else:
                    context_lines.append(f"  Existing Incidents for {r['voyage_id']}: None recorded yet.")
        except Exception as e:
            logger.warning("Error fetching voyage context for '%s': %s", vid, e)

    for vname in vessels:
        try:
            vq = "MATCH (v:Vessel) WHERE toLower(v.name) = toLower($vname) RETURN v.vessel_id AS vid, v.name AS name, v.imo AS imo LIMIT 1"
            vrecs = client.execute_query(vq, {"vname": vname.strip("`").strip()})
            if vrecs:
                vr = vrecs[0]
                context_lines.append(f"Vessel: {vr['name']} (vessel_id: '{vr['vid']}', IMO: {vr['imo']})")
        except Exception as e:
            logger.warning("Error fetching vessel context for '%s': %s", vname, e)

    if not context_lines:
        return "No pre-existing graph records found for extracted voyage/vessel mentions."
    return "\n".join(context_lines)

def kg_updator_node(state: MessageLoaderState) -> Dict[str, Any]:
    """
    KG Updator Node:
    1. Programmatically inserts/merges the Message node and its sender relationship into Neo4j.
    2. Spawns a LangChain ReAct agent equipped with execute_read_query, create_nodes, and update_nodes.
    3. The agent inspects existing graph nodes, cross-validates incidents/delays, creates unlogged incidents,
       updates existing records, and attaches semantic edges to the Message node.
    4. Records all mutations and agent reasoning into state for the ingestion report.
    """
    client = _get_client()
    run_id = state.get("run_id") or str(uuid.uuid4())

    # Step 3A: Programmatic insertion of Message node and sender edge
    _insert_message_node_and_sender(client, state, run_id)

    # Step 3B: LangChain ReAct Agent with mutation tracking
    created_nodes_log: List[Dict[str, Any]] = []
    updated_nodes_log: List[Dict[str, Any]] = []
    edges_added_log: List[Dict[str, Any]] = []

    @tool
    def execute_read_query(query: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes a validated read-only Cypher query against the Maritime Knowledge Graph.
        Use this to check for existing voyages, incidents, port calls, vessels, or congestion records.
        """
        res = execute_read_cypher(client, query, parameters, limit=10)
        if res.get("success") and "records" in res:
            compacted = []
            for rec in res["records"][:10]:
                compact_rec = {k: v for k, v in rec.items() if v is not None}
                compacted.append(compact_rec)
            res["records"] = compacted
        return res

    @tool
    def create_graph_nodes(
        label: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        edges: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Creates new nodes (e.g. Incident) with duplicate checks and schema constraints.
        Optionally links edges upon creation (e.g. [:EXPERIENCED_INCIDENT], [:AFFECTS_VESSEL], [:REPORTS_INCIDENT]).
        """
        res = create_nodes(client, label=label, properties=properties, edges=edges)
        if "node" in res:
            created_nodes_log.append(res["node"])
        if "created_edges" in res and res["created_edges"]:
            edges_added_log.extend(res["created_edges"])
        return res

    @tool
    def update_graph_nodes(
        label: Optional[str] = None,
        key_value: Optional[Any] = None,
        key_field: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        edges: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Updates an existing valid node and adds/modifies relationships.
        Strictly requires the target node to exist.
        Use this to update incident status, delay hours, voyage revised ETA, or attach Message edges.
        """
        res = update_nodes(client, label=label, key_value=key_value, key_field=key_field, properties=properties, edges=edges)
        if "node" in res and (res.get("updated_properties") or not edges):
            updated_nodes_log.append(res["node"])
        if "added_edges" in res and res["added_edges"]:
            edges_added_log.extend(res["added_edges"])
        return res

    tools = [execute_read_query, create_graph_nodes, update_graph_nodes]

    # Initialize Chat LLM via unified factory (supports Groq and Gemini)
    llm = get_chat_llm(temperature=0.0)

    # Pre-fetch relevant Knowledge Graph context for extracted entities
    graph_context = _fetch_graph_context_for_message(
        client=client,
        body=state.get("cleaned_body", state.get("raw_body", "")),
        entities=state.get("entity_replacements", [])
    )

    prompt_cfg = get_prompt_template("kg_updator_agent")
    system_prompt = prompt_cfg["system"].format(
        message_id=state["message_id"],
        message_type=state.get("message_type", "Agent email"),
        trust_tier=state.get("trust_tier", "T2"),
        cleaned_body=state.get("cleaned_body", ""),
        entities=json.dumps(state.get("entity_replacements", [])),
        dates=json.dumps(state.get("date_replacements", [])),
        graph_context=graph_context
    )

    agent_executor = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=system_prompt)
    )

    user_msg = (
        f"OPERATIONAL MESSAGE TO PROCESS:\n"
        f"Message ID: {state['message_id']}\n"
        f"Cleaned Text:\n\"{state.get('cleaned_body')}\"\n\n"
        f"MANDATORY TASK:\n"
        f"Call `update_graph_nodes` to link (:Message {{message_id: '{state['message_id']}'}}) to its related "
        f"Voyage ([:ABOUT_VOYAGE]), Vessel ([:ABOUT_VESSEL]), and Incidents ([:CORROBORATES_INCIDENT] or [:REPORTS_INCIDENT]).\n"
        f"If any incidents need attribute updates or creation, perform them.\n"
        f"Execute your tool calls now."
    )

    agent_reasoning = ""
    errors = state.get("errors", [])
    try:
        agent_config = {
            "run_name": f"kg_updator_agent_{state['message_id']}",
            "metadata": {"message_id": state["message_id"]}
        }
        agent_res = agent_executor.invoke(
            {"messages": [HumanMessage(content=user_msg)]},
            config=agent_config
        )
        messages = agent_res.get("messages", [])
        for m in reversed(messages):
            if hasattr(m, "content") and m.content and not isinstance(m, ToolMessage):
                agent_reasoning = str(m.content)
                break
    except Exception as e:
        logger.error("KG Updator Agent execution error for '%s': %s", state["message_id"], e)
        errors.append(f"AgentExecutionError: {str(e)}")

    return {
        "message_node_created": True,
        "nodes_created": created_nodes_log,
        "nodes_updated": updated_nodes_log,
        "edges_added": edges_added_log,
        "agent_reasoning": agent_reasoning,
        "status": "SUCCESS" if not errors else "PARTIAL_SUCCESS",
        "errors": errors
    }
