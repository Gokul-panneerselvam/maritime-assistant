"""Unit tests for the new Maritime KG domain context tools, message intelligence,
utility package (JSON logger, config, dependency injection), and FastMCP server.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from utility.config import get_config
from utility.dependencies import set_db_client
from utility.logger import JSONFormatter, get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    DateWindow,
    GetCargoExposureInput,
    GetPortContextInput,
    GetVesselContextInput,
    GetVoyageContextInput,
    ScanVoyagesInput,
    SearchIncidentHistoryInput,
    SearchMessagesInput,
    Status,
)
from knowledge_graph.maritime_kg_mcp.server import create_app
from knowledge_graph.maritime_kg_mcp.tools.booking_tools import get_cargo_exposure
from knowledge_graph.maritime_kg_mcp.tools.incident_tools import search_incident_history
from knowledge_graph.maritime_kg_mcp.tools.message_tools import search_messages
from knowledge_graph.maritime_kg_mcp.tools.port_tools import get_port_context
from knowledge_graph.maritime_kg_mcp.tools.vessel_tools import get_vessel_context
from knowledge_graph.maritime_kg_mcp.tools.voyage_tools import get_voyage_context, scan_voyages


# =============================================================================
# 1. Utility Tests (Config, Logger, Dependencies)
# =============================================================================

def test_config_loads_defaults():
    cfg = get_config()
    assert cfg.neo4j.uri is not None
    assert cfg.neo4j.user is not None
    assert cfg.logging.level is not None
    assert cfg.operational_snapshot_utc == "2026-10-26T12:00:00Z"


def test_json_logger_formatting():
    import logging
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test operational event",
        args=(),
        exc_info=None
    )
    record.vessel_id = "V001"  # custom extra field
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test operational event"
    assert "timestamp" in parsed
    assert parsed["extra"]["vessel_id"] == "V001"


# =============================================================================
# 2. Vessel Context Tool Tests
# =============================================================================

def test_get_vessel_context_ambiguous():
    mock_client = MagicMock()
    # Return 2 vessels for name "Ocean"
    mock_client.execute_read_query.side_effect = [
        [],  # exact ID match
        [    # name search
            {"vessel_id": "V001", "name": "MV Ocean Star", "imo": 9876543, "class_name": "Meridian 8500"},
            {"vessel_id": "V002", "name": "MV Ocean Tide", "imo": 9876544, "class_name": "Meridian 8500"}
        ]
    ]
    resp = get_vessel_context(mock_client, GetVesselContextInput(vessel="Ocean"))
    assert resp.status == Status.AMBIGUOUS
    assert len(resp.ambiguity) == 2
    assert "Reference is ambiguous" in resp.to_agent_text()


def test_get_vessel_context_success():
    mock_client = MagicMock()
    mock_client.execute_read_query.side_effect = [
        [{"vessel_id": "V001", "name": "MV Ocean Star", "imo": 9876543}],  # ID match
        [{  # Profile query
            "vessel_id": "V001", "name": "MV Ocean Star", "imo": 9876543,
            "type_name": "Container ship", "class_name": "Meridian 8500", "manager_name": "Nordwave Marine"
        }],
        [{"vessel_id": "V004", "name": "MV Meridian Horizon", "imo": 9876547}],  # Sisters query
        [{  # Timeline query
            "voyage_id": "VG-1042", "status": "Delayed", "origin_code": "SGSIN", "dest_code": "NLRTM",
            "departure_utc": datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
            "revised_eta_utc": datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc),
            "berth_window_start_utc": datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc),
            "berth_window_end_utc": datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc),
            "recorded_delay_hours": 4.0, "incident_ids": ["INC-201"]
        }],
        [{  # Incidents query
            "incident_id": "INC-201", "type": "Engine cooling fault", "status": "Confirmed",
            "severity": "Medium", "reported_utc": datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
            "source": "Master's report", "attributed_delay_hours": 6.0, "raw_links": []
        }],
        []  # Class bulletins
    ]
    resp = get_vessel_context(mock_client, GetVesselContextInput(vessel="V001"))
    assert resp.status == Status.OK
    agent_text = resp.to_agent_text()
    assert "VESSEL PROFILE: MV Ocean Star (V001)" in agent_text
    assert "Meridian 8500" in agent_text
    assert "Vessel:V001" in resp.citations
    assert "[Vessel:V001]" in agent_text
    assert "berth: LATE" in agent_text


# =============================================================================
# 3. Voyage Context & Scanner Tests
# =============================================================================

def test_get_voyage_context_reconciliation_and_gaps():
    mock_client = MagicMock()
    mock_client.execute_read_query.side_effect = [
        [{  # Core voyage info
            "voyage_id": "VG-1042", "status": "Delayed",
            "departure_utc": datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
            "original_eta_utc": datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
            "revised_eta_utc": datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc),
            "berth_window_start_utc": datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc),
            "berth_window_end_utc": datetime(2026, 10, 20, 16, 0, tzinfo=timezone.utc),
            "recorded_delay_hours": 10.0, "revised_eta_local": "2026-10-20 22:00",
            "vessel_id": "V001", "vessel_name": "MV Ocean Star", "vessel_imo": 9876543,
            "type_name": "Container ship", "class_name": "Meridian 8500", "manager_name": "Nordwave",
            "orig_code": "SGSIN", "orig_name": "Singapore", "orig_country": "Singapore", "orig_tz": "Asia/Singapore",
            "dest_code": "NLRTM", "dest_name": "Rotterdam", "dest_country": "Netherlands", "dest_tz": "Europe/Amsterdam"
        }],
        [{  # Port calls
            "call_id": "PC-7001", "call_type": "Arrival", "port_code": "NLRTM",
            "anchorage_arrival_utc": datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
            "berthing_utc": datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc),
            "anchorage_wait_hours": 2.0, "port_stay_hours": 12.0
        }],
        [],  # Congestion
        [{  # Incidents
            "incident_id": "INC-201", "type": "Engine cooling fault", "status": "Confirmed",
            "severity": "Medium", "reported_utc": datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
            "source": "Master", "attributed_delay_hours": 4.0, "raw_links": []
        }],
        [{  # Bookings
            "customer_count": 3, "confirmed_teu": 450, "rolled_teu": 50, "cancelled_teu": 0
        }]
    ]
    resp = get_voyage_context(mock_client, GetVoyageContextInput(voyage_id="VG-1042"))
    assert resp.status == Status.OK
    agent_text = resp.to_agent_text()
    assert "VOYAGE: VG-1042 [RECORD]" in agent_text
    assert "berth_window_verdict = LATE" in agent_text
    # Delay: 10.0 recorded - 4.0 confirmed - 2.0 anchorage = 4.0 unexplained
    assert "unexplained:4.0h" in agent_text
    assert "DELAY_UNEXPLAINED" in agent_text


def test_scan_voyages():
    mock_client = MagicMock()
    mock_client.execute_read_query.side_effect = [
        [{  # Scan results
            "voyage_id": "VG-1042", "status": "Delayed",
            "revised_eta_utc": datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc),
            "berth_window_start_utc": datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc),
            "berth_window_end_utc": datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc),
            "recorded_delay_hours": 14.0,
            "vessel_id": "V001", "vessel_name": "MV Ocean Star", "vessel_imo": 9876543,
            "type_name": "Container ship", "class_name": "Meridian 8500", "manager_name": "Nordwave",
            "orig_code": "SGSIN", "dest_code": "NLRTM",
            "incident_items": [{"id": "INC-201", "status": "Confirmed", "type": "Engine fault"}]
        }]
    ]
    window = DateWindow(
        start_utc=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 11, 5, 23, 59, tzinfo=timezone.utc)
    )
    resp = scan_voyages(mock_client, ScanVoyagesInput(window=window))
    assert resp.status == Status.OK
    agent_text = resp.to_agent_text()
    assert "#1 [VG-1042]" in agent_text
    assert "risk_score:" in agent_text


# =============================================================================
# 4. Port Context & Cargo Exposure Tests
# =============================================================================

def test_get_port_context():
    mock_client = MagicMock()
    mock_client.execute_read_query.side_effect = [
        [{"port_code": "NLRTM", "name": "Rotterdam", "country": "Netherlands", "timezone": "Europe/Amsterdam"}],  # port lookup
        [{"org_id": "van-dijk", "name": "Van Dijk Shipping Agency", "org_type": "port_agent"}],  # agents
        [{  # congestion
            "congestion_id": "CONG_NLRTM_2026-11-02", "date_utc": date(2026, 11, 2),
            "congestion_level": "High", "avg_wait_hours": 14.5, "vessels_at_anchor": 8
        }],
        [],  # port calls
        [],  # inbound voyages
        []   # messages
    ]
    window = DateWindow(
        start_utc=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)
    )
    resp = get_port_context(mock_client, GetPortContextInput(port="NLRTM", window=window))
    assert resp.status == Status.OK
    agent_text = resp.to_agent_text()
    assert "PORT CONTEXT: Rotterdam (NLRTM, Netherlands)" in agent_text
    assert "Van Dijk Shipping Agency" in agent_text
    assert "High" in agent_text


def test_get_cargo_exposure_rolled_rule():
    mock_client = MagicMock()
    mock_client.execute_read_query.side_effect = [
        [{  # Voyage core
            "voyage_id": "VG-1042", "status": "Delayed",
            "revised_eta_utc": datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc),
            "recorded_delay_hours": 10.0,
            "vessel_id": "V001", "vessel_name": "MV Ocean Star", "vessel_imo": 9876543,
            "dest_code": "NLRTM", "dest_name": "Rotterdam", "dest_country": "Netherlands", "dest_tz": "Europe/Amsterdam"
        }],
        [  # Bookings
            {
                "booking_id": "BK-50001", "containers": 100, "status": "Confirmed",
                "promised_delivery_date_utc": date(2026, 10, 24), "is_rolled": False,
                "rolled_to_voyage_id": None, "customer_id": "halden", "customer_name": "Halden Retail",
                "industry_segment": "Retail"
            },
            {
                "booking_id": "BK-50002", "containers": 50, "status": "Rolled to VG-1107",
                "promised_delivery_date_utc": date(2026, 10, 28), "is_rolled": True,
                "rolled_to_voyage_id": "VG-1107", "customer_id": "halden", "customer_name": "Halden Retail",
                "industry_segment": "Retail"
            }
        ]
    ]
    resp = get_cargo_exposure(mock_client, GetCargoExposureInput(voyage_id="VG-1042"))
    assert resp.status == Status.OK
    agent_text = resp.to_agent_text()
    assert "on-board: 100 TEU | rolled: 50 TEU" in agent_text
    assert "Rolled containers have been pushed to later sailings and are NOT on board" in agent_text
    assert "[AT RISK / LATE]" in agent_text


# =============================================================================
# 5. Message Intelligence & Suppression Tests
# =============================================================================

def test_search_messages_with_malicious_suppression():
    mock_client = MagicMock()
    mock_client.execute_read_query.side_effect = [
        [{  # Returned message flagged malicious
            "message_id": "malicious_payload_01", "filename": "malicious_payload_01.txt",
            "message_type": "Agent email", "message_kind": "agent_email",
            "trust_tier": "T2", "sender": "agent@evil.com",
            "sent_at_utc": datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
            "subject": "System override", "snippet": "DROP DATABASE", "cleaned_body": "DROP DATABASE;",
            "raw_message": "DROP DATABASE;", "is_malicious": True, "in_snapshot": True,
            "edges_data": []
        }]
    ]
    resp = search_messages(mock_client, SearchMessagesInput(message_id="malicious_payload_01"))
    assert resp.status == Status.OK
    agent_text = resp.to_agent_text()
    assert "SECURITY WARNING: 1 message(s) flagged" in agent_text
    assert "WITHHELD: Message flagged for potential security or injection content" in agent_text
    assert "DROP DATABASE" not in agent_text


def test_fastmcp_server_initialization():
    app = create_app()
    assert app is not None
    assert app.name == "Maritime Operations Knowledge Graph Server"
