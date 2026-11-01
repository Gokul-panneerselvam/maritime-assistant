import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.kg_loader.loaders.base import read_csv_rows, execute_batched_query
from knowledge_graph.kg_loader.normalizers import normalize_type_id

logger = logging.getLogger(__name__)

VESSELS_CYPHER = """
UNWIND $batch AS row
MERGE (v:Vessel {vessel_id: row.vessel_id})
ON CREATE SET
    v.name = row.name,
    v.imo = row.imo
ON MATCH SET
    v.name = row.name,
    v.imo = row.imo

MERGE (vt:VesselType {type_id: row.type_id})
ON CREATE SET vt.name = row.type_name
ON MATCH SET vt.name = row.type_name
MERGE (v)-[:OF_TYPE]->(vt)

MERGE (vc:VesselClass {class_id: row.class_id})
ON CREATE SET vc.name = row.class_name
ON MATCH SET vc.name = row.class_name
MERGE (v)-[:OF_CLASS]->(vc)

MERGE (tm:TechnicalManager {manager_id: row.manager_id})
ON CREATE SET tm.name = row.manager_name
ON MATCH SET tm.name = row.manager_name
MERGE (v)-[:MANAGED_BY]->(tm)
"""

def load_vessels(
    file_path: Path,
    client: Optional[Neo4jClient] = None,
    batch_size: int = 500,
    dry_run: bool = False
) -> int:
    """
    Ingests vessels.csv into Vessel, VesselType, VesselClass, and TechnicalManager nodes
    and establishes [:OF_TYPE], [:OF_CLASS], and [:MANAGED_BY] relationships.
    """
    rows = read_csv_rows(file_path)
    records: List[Dict[str, Any]] = []

    for r in rows:
        vessel_id = r["vessel_id"].strip()
        name = r["name"].strip()
        imo = int(r["imo"].strip())
        vtype = r["type"].strip()
        vclass = r["vessel_class"].strip()
        manager = r["technical_manager"].strip()

        records.append({
            "vessel_id": vessel_id,
            "name": name,
            "imo": imo,
            "type_id": normalize_type_id(vtype),
            "type_name": vtype,
            "class_id": vclass,
            "class_name": vclass,
            "manager_id": manager,
            "manager_name": manager
        })

    logger.info("Prepared %d Vessel records from %s", len(records), file_path.name)
    return execute_batched_query(client, VESSELS_CYPHER, records, batch_size=batch_size, dry_run=dry_run)

