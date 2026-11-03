"""Entity resolution service for Maritime Knowledge Graph.
Resolves polymorphic entity identifiers (ID, name, IMO, UN/LOCODE) against the Neo4j graph.
Returns canonical matches or AmbiguityOption candidates when ambiguous.
Adheres to SOLID principles: Single responsibility for entity resolution.
"""

from __future__ import annotations

from typing import List, Optional, Tuple
from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import AmbiguityOption, PortNode, VesselNode

logger = get_logger(__name__)


def resolve_vessel(
    client: DatabaseClientProtocol, vessel_ref: str
) -> Tuple[Optional[VesselNode], List[AmbiguityOption]]:
    """Resolves a vessel reference (vessel_id, name, or IMO) against the graph.
    Returns:
        (VesselNode, []) if exactly one matches.
        (None, [AmbiguityOption...]) if multiple match.
        (None, []) if none match.
    """
    vessel_ref = vessel_ref.strip()
    if not vessel_ref:
        return None, []

    # Try exact match on vessel_id first
    cypher_id = """
    MATCH (v:Vessel {vessel_id: $ref})
    RETURN v.vessel_id AS vessel_id, v.name AS name, v.imo AS imo
    LIMIT 2
    """
    records = client.execute_read_query(cypher_id, {"ref": vessel_ref})
    if len(records) == 1:
        r = records[0]
        return VesselNode(vessel_id=r["vessel_id"], name=r["name"], imo=r["imo"]), []

    # Try integer IMO if digits
    if vessel_ref.isdigit():
        cypher_imo = """
        MATCH (v:Vessel {imo: toInteger($ref)})
        RETURN v.vessel_id AS vessel_id, v.name AS name, v.imo AS imo
        LIMIT 2
        """
        records = client.execute_read_query(cypher_imo, {"ref": vessel_ref})
        if len(records) == 1:
            r = records[0]
            return VesselNode(vessel_id=r["vessel_id"], name=r["name"], imo=r["imo"]), []

    # Search by name (case-insensitive contains or prefix)
    cypher_name = """
    MATCH (v:Vessel)
    OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
    WHERE toLower(v.name) CONTAINS toLower($ref)
       OR toLower(v.vessel_id) = toLower($ref)
    RETURN v.vessel_id AS vessel_id, v.name AS name, v.imo AS imo, vc.name AS class_name
    LIMIT 10
    """
    records = client.execute_read_query(cypher_name, {"ref": vessel_ref})

    if len(records) == 1:
        r = records[0]
        return VesselNode(vessel_id=r["vessel_id"], name=r["name"], imo=r["imo"]), []

    if len(records) > 1:
        # Multiple matches -> return AMBIGUOUS options
        options = [
            AmbiguityOption(
                key=r["vessel_id"],
                label=f"{r['name']} ({r['vessel_id']}, Class: {r.get('class_name') or 'N/A'}, IMO: {r['imo']})"
            )
            for r in records
        ]
        return None, options

    return None, []


def resolve_port(
    client: DatabaseClientProtocol, port_ref: str
) -> Tuple[Optional[PortNode], List[AmbiguityOption]]:
    """Resolves a port reference (port_code e.g. NLRTM, or name e.g. Rotterdam) against the graph.
    Returns:
        (PortNode, []) if single match.
        (None, [AmbiguityOption...]) if multiple match.
        (None, []) if none match.
    """
    port_ref = port_ref.strip()
    if not port_ref:
        return None, []

    # Try exact match on port_code
    cypher_code = """
    MATCH (p:Port)
    WHERE toUpper(p.port_code) = toUpper($ref)
    RETURN p.port_code AS port_code, p.name AS name, p.country AS country, p.timezone AS timezone
    LIMIT 2
    """
    records = client.execute_read_query(cypher_code, {"ref": port_ref})
    if len(records) == 1:
        r = records[0]
        return PortNode(
            port_code=r["port_code"],
            name=r["name"],
            country=r["country"],
            timezone=r.get("timezone", "UTC")
        ), []

    # Search by port name
    cypher_name = """
    MATCH (p:Port)
    WHERE toLower(p.name) CONTAINS toLower($ref)
       OR toLower(p.country) CONTAINS toLower($ref)
    RETURN p.port_code AS port_code, p.name AS name, p.country AS country, p.timezone AS timezone
    LIMIT 10
    """
    records = client.execute_read_query(cypher_name, {"ref": port_ref})

    if len(records) == 1:
        r = records[0]
        return PortNode(
            port_code=r["port_code"],
            name=r["name"],
            country=r["country"],
            timezone=r.get("timezone", "UTC")
        ), []

    if len(records) > 1:
        options = [
            AmbiguityOption(
                key=r["port_code"],
                label=f"{r['name']} ({r['port_code']}, {r['country']})"
            )
            for r in records
        ]
        return None, options

    return None, []

