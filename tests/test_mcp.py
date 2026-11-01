import unittest
from unittest.mock import MagicMock
from knowledge_graph.maritime_kg_mcp.security import (
    validate_read_only_cypher,
    enforce_query_limit,
    MAX_ROWS_LIMIT
)
from knowledge_graph.maritime_kg_mcp.tools.cypher_tool import execute_read_cypher
from knowledge_graph.maritime_kg_mcp.tools.schema_tool import get_graph_schema
from knowledge_graph.maritime_kg_mcp.tools.vessel_tools import search_vessels, get_vessel_details
from knowledge_graph.maritime_kg_mcp.tools.voyage_tools import search_voyages, get_voyage_timeline
from knowledge_graph.maritime_kg_mcp.tools.port_tools import search_ports, get_port_congestion
from knowledge_graph.maritime_kg_mcp.tools.incident_tools import search_incidents
from knowledge_graph.maritime_kg_mcp.tools.booking_tools import track_booking, get_rolled_bookings
from knowledge_graph.maritime_kg_mcp.tools.summary_tool import get_operational_summary
from knowledge_graph.maritime_kg_mcp.tools.node_tools import create_nodes, update_nodes

class TestMCPSecurity(unittest.TestCase):
    def test_valid_read_queries(self):
        valid_queries = [
            "MATCH (v:Vessel) RETURN v.name",
            "MATCH (voy:Voyage)-[:DEPARTS_FROM]->(p:Port) WHERE p.port_code = 'SGSIN' RETURN voy",
            "// comment\nMATCH (n) RETURN n LIMIT 10",
            "/* block comment */ MATCH (c:Customer) RETURN c.name",
            "CALL db.labels()",
            "SHOW CONSTRAINTS",
        ]
        for q in valid_queries:
            is_valid, err = validate_read_only_cypher(q)
            self.assertTrue(is_valid, f"Expected '{q}' to be valid, got error: {err}")
            self.assertIsNone(err)

    def test_blocked_mutating_queries(self):
        mutating_queries = [
            "CREATE (v:Vessel {name: 'Malicious'})",
            "MATCH (v:Vessel) CREATE (n:Test)",
            "MERGE (p:Port {port_code: 'EVIL'})",
            "MATCH (v:Vessel) SET v.name = 'Hacked'",
            "MATCH (n) DELETE n",
            "MATCH (n) DETACH DELETE n",
            "MATCH (v:Vessel) REMOVE v.imo",
            "DROP CONSTRAINT unique_vessel_id",
            "ALTER DATABASE neo4j SET ACCESS READ ONLY",
            "LOAD CSV FROM 'http://malicious.com' AS row CREATE (n)",
            "CALL dbms.security.createUser('attacker', 'pass')",
            "CALL apoc.cypher.runSchemaFile('hack.cypher')",
            "// stealthy\nMATCH (n) DELETE n",
            "/* stealthy */ MATCH (n) SET n.val = 1",
        ]
        for q in mutating_queries:
            is_valid, err = validate_read_only_cypher(q)
            self.assertFalse(is_valid, f"Expected '{q}' to be blocked!")
            self.assertIn("Permission denied", err)

    def test_enforce_query_limit(self):
        # Appends limit if none present
        q1 = "MATCH (v:Vessel) RETURN v.name"
        limited1 = enforce_query_limit(q1, 50)
        self.assertIn("LIMIT 50", limited1)

        # Caps excessive limit at MAX_ROWS_LIMIT
        q2 = f"MATCH (v:Vessel) RETURN v.name LIMIT {MAX_ROWS_LIMIT + 500}"
        limited2 = enforce_query_limit(q2, 100)
        self.assertIn(f"LIMIT {MAX_ROWS_LIMIT}", limited2)
        self.assertNotIn(f"LIMIT {MAX_ROWS_LIMIT + 500}", limited2)

class TestMCPToolsWithMock(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()

    def test_cypher_tool_blocks_mutating(self):
        res = execute_read_cypher(self.mock_client, "MATCH (n) DELETE n")
        self.assertFalse(res["success"])
        self.assertIn("Permission denied", res["error"])
        self.mock_client.execute_read_query.assert_not_called()

    def test_cypher_tool_executes_read(self):
        self.mock_client.execute_read_query.return_value = [{"name": "MV Ocean Star"}]
        res = execute_read_cypher(self.mock_client, "MATCH (v:Vessel) RETURN v.name", limit=10)
        self.assertTrue(res["success"])
        self.assertEqual(res["record_count"], 1)
        self.assertEqual(res["records"][0]["name"], "MV Ocean Star")

    def test_vessel_tools(self):
        self.mock_client.execute_read_query.return_value = [{"vessel_id": "V001", "name": "MV Ocean Star"}]
        res = search_vessels(self.mock_client, name="Ocean")
        self.assertTrue(res["success"])
        self.assertEqual(len(res["vessels"]), 1)

    def test_voyage_tools(self):
        self.mock_client.execute_read_query.return_value = [{"voyage_id": "VG-1042", "status": "Delayed"}]
        res = search_voyages(self.mock_client, status="Delayed")
        self.assertTrue(res["success"])
        self.assertEqual(res["voyages"][0]["status"], "Delayed")

    def test_booking_tools(self):
        self.mock_client.execute_read_query.return_value = [{"booking_id": "BK-50001", "is_rolled": False}]
        res = track_booking(self.mock_client, booking_id="BK-50001")
        self.assertTrue(res["success"])
        self.assertEqual(res["bookings"][0]["booking_id"], "BK-50001")

    def test_create_nodes_duplicate_rejection(self):
        # Mocking duplicate check: count > 0
        self.mock_client.execute_query.return_value = [{"cnt": 1}]
        res = create_nodes(
            self.mock_client,
            label="Incident",
            properties={"incident_id": "INC-201", "type": "Engine cooling fault"}
        )
        self.assertFalse(res["success"])
        self.assertIn("DuplicateNodeError", res["error"])

    def test_create_nodes_missing_required_constraint(self):
        # Missing required 'type' on Incident
        res = create_nodes(
            self.mock_client,
            label="Incident",
            properties={"incident_id": "INC-999"}
        )
        self.assertFalse(res["success"])
        self.assertIn("AttributeConstraintError", res["error"])

    def test_create_nodes_success(self):
        # Duplicate check returns 0, creation returns properties and element_id
        self.mock_client.execute_query.side_effect = [
            [{"cnt": 0}],  # duplicate check
            [{"props": {"incident_id": "INC-999", "type": "Pilot delay", "attributed_delay_hours": 2.0}, "element_id": "4:123"}],  # creation
            [{"cnt": 1}],  # target node existence check for edge
            [{"rel_type": "EXPERIENCED_INCIDENT", "rel_props": {"temporal": "past"}}]  # edge creation
        ]
        res = create_nodes(
            self.mock_client,
            label="Incident",
            properties={"incident_id": "INC-999", "type": "Pilot delay", "attributed_delay_hours": 2.0},
            edges=[{
                "relationship_type": "EXPERIENCED_INCIDENT",
                "direction": "INCOMING",
                "target_label": "Voyage",
                "target_value": "VG-2002",
                "properties": {"temporal": "past"}
            }]
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["node"]["primary_key_value"], "INC-999")
        self.assertEqual(len(res["created_edges"]), 1)
        self.assertEqual(res["created_edges"][0]["relationship_type"], "EXPERIENCED_INCIDENT")

    def test_update_nodes_missing_node_rejection(self):
        # Node does not exist
        self.mock_client.execute_query.return_value = []
        res = update_nodes(
            self.mock_client,
            label="Incident",
            key_value="INC-NONEXISTENT",
            properties={"status": "Confirmed"}
        )
        self.assertFalse(res["success"])
        self.assertIn("NodeNotFoundError", res["error"])

    def test_update_nodes_success(self):
        # Node exists, update returns updated properties, edge target exists, edge created, connections returned
        self.mock_client.execute_query.side_effect = [
            [{"props": {"incident_id": "INC-202", "status": "Reported"}, "element_id": "4:456"}],  # existence check
            [{"props": {"incident_id": "INC-202", "status": "Confirmed", "attributed_delay_hours": 8.0}}],  # property update
            [{"cnt": 1}],  # edge target check
            [{"rel_type": "ABOUT_INCIDENT", "rel_props": {}}],  # edge creation
            [{  # connected query
                "rel_type": "EXPERIENCED_INCIDENT",
                "target_labels": ["Voyage"],
                "target_properties": {"voyage_id": "VG-1042"},
                "is_outgoing": False,
                "edge_properties": {}
            }]
        ]
        res = update_nodes(
            self.mock_client,
            label="Incident",
            key_value="INC-202",
            properties={"status": "Confirmed", "attributed_delay_hours": 8.0},
            edges=[{
                "relationship_type": "ABOUT_INCIDENT",
                "target_label": "Voyage",
                "target_value": "VG-1042"
            }]
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["node"]["primary_key_value"], "INC-202")
        self.assertIn("status", res["node"]["updated_attributes"])
        self.assertEqual(len(res["added_edges"]), 1)
        self.assertEqual(len(res["connected_edges"]), 1)

    def test_batch_create_and_update(self):
        # Batch create
        self.mock_client.execute_query.side_effect = [
            [{"cnt": 0}],
            [{"props": {"port_code": "NEWP", "name": "New Port"}, "element_id": "4:789"}],
        ]
        res_create = create_nodes(
            self.mock_client,
            nodes=[{"label": "Port", "properties": {"port_code": "NEWP", "name": "New Port"}}]
        )
        self.assertTrue(res_create["success"])
        self.assertEqual(res_create["total_created"], 1)

        # Batch update
        self.mock_client.execute_query.side_effect = [
            [{"props": {"port_code": "NEWP", "name": "New Port"}, "element_id": "4:789"}],
            [{"props": {"port_code": "NEWP", "name": "Updated Port"}}],
            [] # connected query
        ]
        res_update = update_nodes(
            self.mock_client,
            nodes=[{"label": "Port", "key_value": "NEWP", "properties": {"name": "Updated Port"}}]
        )
        self.assertTrue(res_update["success"])
        self.assertEqual(res_update["total_updated"], 1)

if __name__ == "__main__":
    unittest.main()
