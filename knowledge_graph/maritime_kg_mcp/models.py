"""Maritime KG tools: input signatures (what the agent sends) and output models
(what your server builds before rendering to graph-text).

Design contract
---------------
* Every tool takes a small typed input (Pydantic model = the tool's JSON schema).
* Every tool builds a typed result model (the *Result classes below), then a
  renderer turns it into graph-text: edges, attributes, connected nodes.
* The agent receives only the text, wrapped in the common ToolResponse envelope
  (status line, text, citations, hints). The typed models exist so you can unit
  test, validate and render consistently.
* Entity arguments ("vessel", "port", ...) accept an ID, a name or an IMO. The
  server resolves them against the roster and returns AMBIGUOUS with options
  when more than one vessel matches ("Ocean").
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# 1. Shared building blocks
# =============================================================================


class Status(str, Enum):
    OK = "OK"
    NO_DATA = "NO_DATA"          # nothing matched; `searched` says what was tried
    AMBIGUOUS = "AMBIGUOUS"      # entity reference matched several; see `ambiguity`
    ERROR = "ERROR"              # bad input or DB failure; `text` explains


class Tier(str, Enum):
    """Evidence label printed next to incidents and messages."""
    CONFIRMED = "CONFIRMED"      # Incident status Confirmed, or Message T1/T2
    UNVERIFIED = "UNVERIFIED"    # Reported / Under review, or T3/T4 uncorroborated
    DISMISSED = "DISMISSED"      # Incident status Dismissed (never a cause)
    RECORD = "RECORD"            # system-of-record property (voyage, port call, ...)


class DateWindow(BaseModel):
    """UTC window, inclusive. The entity-resolution node should produce these."""
    start_utc: datetime
    end_utc: datetime

    @field_validator("start_utc", "end_utc", mode="before")
    @classmethod
    def _parse_and_utc(cls, v: Any) -> datetime:
        if hasattr(v, "to_native"):
            v = v.to_native()
        if isinstance(v, str):
            # Parse ISO string
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        raise ValueError("datetime must be timezone-aware UTC (e.g. 2026-11-02T00:00:00Z)")

    @model_validator(mode="after")
    def _order(self):
        if self.end_utc < self.start_utc:
            raise ValueError("end_utc must be >= start_utc")
        return self


class AmbiguityOption(BaseModel):
    key: str = Field(description="Canonical ID, e.g. V001")
    label: str = Field(description="Canonical display, e.g. 'MV Ocean Star (V001, Meridian 8500)'")


class ToolResponse(BaseModel):
    """Envelope returned by EVERY tool. Only to_agent_text() reaches the LLM."""
    status: Status
    text: str = Field("", description="Graph-text body (see renderer). Empty unless status is OK.")
    citations: list[str] = Field(
        default_factory=list,
        description="Every citation tag present in `text`, e.g. ['Voyage:VG-1042','Incident:INC-201','File:noon_2026-10-06_ocean_star.txt']. "
                    "The agent may only cite tags from this list."
    )
    truncated: bool = False
    next_hints: list[str] = Field(
        default_factory=list,
        description="Optional pointers such as 'search_messages(message_id=...) for full text'."
    )
    ambiguity: list[AmbiguityOption] = Field(default_factory=list)
    searched: dict = Field(
        default_factory=dict,
        description="On NO_DATA: the resolved entities and filters that were queried."
    )

    def to_agent_text(self) -> str:
        head = f"STATUS: {self.status.value}"
        if self.status is Status.NO_DATA:
            return f"{head}\nNo matching records in the Maritime Knowledge Graph.\nSEARCHED: {self.searched}\nDo not retry with variations."
        if self.status is Status.AMBIGUOUS:
            opts = "\n".join(f"  - {o.key}: {o.label}" for o in self.ambiguity)
            return f"{head}\nReference is ambiguous. Ask the user or pick one:\n{opts}"
        if self.status is Status.ERROR:
            return f"{head}\n{self.text}"
        tail = []
        if self.truncated:
            tail.append("TRUNCATED: more results exist; narrow the filters.")
        if self.next_hints:
            tail.append("HINTS: " + " | ".join(self.next_hints))
        tail.append("CITABLE: " + ", ".join(f"[{c}]" for c in self.citations))
        return head + "\n" + self.text + "\n" + "\n".join(tail)


class MaritimeBaseModel(BaseModel):
    """Base model that automatically coerces Neo4j temporal types (neo4j.time.DateTime/Date) to native python types."""
    @model_validator(mode="before")
    @classmethod
    def _coerce_neo4j_types(cls, data: Any) -> Any:
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if hasattr(v, "to_native"):
                    cleaned[k] = v.to_native()
                elif isinstance(v, list):
                    cleaned[k] = [item.to_native() if hasattr(item, "to_native") else item for item in v]
                else:
                    cleaned[k] = v
            return cleaned
        return data


# ---- Node models (mirror kg_schema_design.md; only fields the agent needs) ----

class VesselNode(MaritimeBaseModel):
    vessel_id: str
    name: str
    imo: int


class VesselProfile(VesselNode):
    type_name: str                    # "Container ship" | "Feeder" | "Bulk carrier"
    class_name: str                   # "Meridian 8500" ...
    manager_name: str


class PortNode(MaritimeBaseModel):
    port_code: str
    name: str
    country: str
    timezone: str


class VoyageNode(MaritimeBaseModel):
    voyage_id: str
    status: str                       # Completed | Delayed | Scheduled | On schedule
    departure_utc: Optional[datetime] = None
    original_eta_utc: Optional[datetime] = None
    revised_eta_utc: Optional[datetime] = None
    berth_window_start_utc: Optional[datetime] = None
    berth_window_end_utc: Optional[datetime] = None
    recorded_delay_hours: Optional[float] = None
    # *_local strings are display-only; include them in text, never compute on them
    revised_eta_local: Optional[str] = None
    berth_window_start_local: Optional[str] = None
    berth_window_end_local: Optional[str] = None


class PortCallNode(MaritimeBaseModel):
    call_id: str
    call_type: str                    # "Arrival" | "Departure"
    port_code: str
    vessel_id: str
    anchorage_arrival_utc: Optional[datetime] = None
    berth_scheduled_utc: Optional[datetime] = None
    berthing_utc: Optional[datetime] = None
    departure_utc: Optional[datetime] = None
    anchorage_wait_hours: Optional[float] = None
    port_stay_hours: Optional[float] = None


class IncidentNode(MaritimeBaseModel):
    incident_id: str
    type: str
    status: str                       # Confirmed | Reported | Under review | Dismissed
    severity: Optional[str] = None    # Low | Medium | High | Unknown | None
    reported_utc: Optional[datetime] = None
    source: Optional[str] = None
    attributed_delay_hours: Optional[float] = None


class CongestionNode(MaritimeBaseModel):
    congestion_id: str
    port_code: str                    # taken from the HAS_CONGESTION edge
    date_utc: date
    congestion_level: str
    avg_wait_hours: Optional[float] = None
    vessels_at_anchor: Optional[int] = None


class CustomerNode(MaritimeBaseModel):
    customer_id: str
    name: str
    industry_segment: Optional[str] = None


class BookingNode(MaritimeBaseModel):
    booking_id: str
    containers: int
    status: str                       # Confirmed | Cancelled | Rolled to VG-xxxx | Rolled to next sailing
    promised_delivery_date_utc: Optional[date] = None
    is_rolled: bool = False


class OrganizationNode(MaritimeBaseModel):
    org_id: str
    name: str
    org_type: str = "port_agent"


class MessageNode(MaritimeBaseModel):
    message_id: str
    filename: str
    message_type: str
    message_kind: str                 # noon_report | agent_email | crew_message | technical_bulletin | ...
    trust_tier: Literal["T1", "T2", "T3", "T4"]
    sender: str
    sent_at_utc: datetime
    subject: str
    snippet: Optional[str] = Field(None, description="First ~300 chars of cleaned_body")
    cleaned_body: Optional[str] = None
    raw_message: Optional[str] = None
    is_malicious: bool = False        # if True the renderer prints a stub and NEVER the body
    in_snapshot: bool = True          # sent_at_utc <= 2026-10-26T12:00:00Z


MessageEdge = Literal[
    "SENT_BY_VESSEL", "SENT_BY_ORG", "ISSUED_BY_MANAGER", "SENT_BY_CUSTOMER",
    "ABOUT_VESSEL", "ABOUT_VOYAGE", "ABOUT_PORT_CALL", "ABOUT_CLASS", "EVENT_AT_PORT",
    "DESCRIBES_CONGESTION", "REPORTS_INCIDENT", "CORROBORATES_INCIDENT",
    "REVISES", "REVISES_INCIDENT", "CORRECTS_INCIDENT", "REFERENCES_VESSEL", "REFERENCES_VESSEL_TYPE",
    "REFERENCES_CLASS", "REFERENCES_MANAGER", "REFERENCES_PORT", "REFERENCES_VOYAGE",
    "REFERENCES_BOOKING", "REFERENCES_CUSTOMER", "CORRECTS_MESSAGE", "REFERENCES_MESSAGE",
]


class MessageLink(MaritimeBaseModel):
    """A Message edge into some node, with its edge properties."""
    edge_type: MessageEdge
    temporal: Optional[Literal["past", "current", "planned"]] = None
    event_time_utc: Optional[datetime] = None
    message: MessageNode


class IncidentEvidence(MaritimeBaseModel):
    incident: IncidentNode
    tier: Tier
    voyage_id: Optional[str] = None
    vessel: Optional[VesselNode] = None
    links: list[MessageLink] = Field(
        default_factory=list,
        description="REPORTS/CORROBORATES/REVISES/CORRECTS edges, ordered by message sent_at_utc"
    )
    superseded_notes: list[str] = Field(
        default_factory=list,
        description="e.g. 'attributed_delay_hours revised 12 -> 18 by tb_... (T2, 2026-10-14)'"
    )


# ---- Computed blocks: printed on 'computed:' lines, never as facts ----

class BerthVerdict(str, Enum):
    INSIDE_WINDOW = "INSIDE_WINDOW"
    LATE = "LATE"                     # revised_eta_utc > berth_window_end_utc
    EARLY = "EARLY"                   # revised_eta_utc < berth_window_start_utc
    UNKNOWN = "UNKNOWN"               # any bound missing


class BerthWindowAssessment(MaritimeBaseModel):
    verdict: BerthVerdict
    margin_hours: Optional[float] = Field(
        None,
        description="+ve = hours after window end (late); -ve = hours before window start (early); 0 if inside"
    )


class DelayReconciliation(MaritimeBaseModel):
    recorded_delay_hours: Optional[float] = None
    eta_slip_hours: Optional[float] = Field(None, description="revised_eta_utc - original_eta_utc")
    confirmed_attributed_hours: float = 0.0
    unverified_attributed_hours: float = 0.0
    anchorage_wait_hours: float = 0.0
    unexplained_hours: Optional[float] = Field(
        None,
        description="recorded_delay - confirmed_attributed - anchorage_wait (clamped at none if inputs missing)"
    )
    discrepancy: bool = Field(False, description="True if recorded_delay and eta_slip differ by > 0.5h")


class Gap(MaritimeBaseModel):
    """Raw material for 'what should ops check next'."""
    kind: Literal[
        "INCIDENT_UNCORROBORATED", "INCIDENT_UNDER_REVIEW", "NO_RECENT_NOON_REPORT",
        "NO_PORT_CALL_RECORD", "CONGESTION_DATA_MISSING", "DELAY_UNEXPLAINED",
        "CONFLICTING_SOURCES", "CORRECTION_PENDING", "BOOKING_PROMISE_AT_RISK",
    ]
    detail: str
    related_ids: list[str] = Field(default_factory=list)


# =============================================================================
# 2. Tool 1: get_voyage_context
# =============================================================================

class GetVoyageContextInput(BaseModel):
    """Everything connected to one voyage (or the few voyages matching a selector)."""
    voyage_id: Optional[str] = Field(None, description="Exact ID, e.g. VG-1042. Wins over the selector.")
    vessel: Optional[str] = Field(None, description="Vessel ID, name or IMO (selector)")
    which: Literal["current", "latest", "next", "in_window"] = Field(
        "current",
        description="current = status Delayed/On schedule and not Completed at snapshot; "
                    "latest = most recent by departure; next = next Scheduled; in_window = use `window`"
    )
    origin_port: Optional[str] = None
    dest_port: Optional[str] = None
    window: Optional[DateWindow] = Field(
        None,
        description="Matches voyages whose revised ETA OR berth window OR departure falls in the window"
    )
    max_voyages: int = Field(3, ge=1, le=5)
    congestion_days_around_eta: int = Field(
        2, ge=0, le=7,
        description="Destination congestion rows within +/- N days of revised ETA (and of berthing if known)"
    )
    include_bookings_summary: bool = True
    message_detail: Literal["none", "snippet"] = "snippet"

    @model_validator(mode="after")
    def _need_anchor(self):
        if not (self.voyage_id or self.vessel or self.dest_port or self.origin_port):
            raise ValueError("Provide voyage_id, or at least one selector (vessel / dest_port / origin_port)")
        return self


class BookingsSummary(MaritimeBaseModel):
    customers: int
    total_containers_confirmed: int
    total_containers_rolled: int
    total_containers_cancelled: int


class VoyageDossier(MaritimeBaseModel):
    voyage: VoyageNode
    vessel: VesselProfile
    origin: PortNode
    destination: PortNode
    port_calls: list[PortCallNode] = []
    destination_congestion: list[CongestionNode] = []
    incidents: list[IncidentEvidence] = []
    messages_about_voyage: list[MessageLink] = Field(
        default_factory=list,
        description="ABOUT_VOYAGE / REFERENCES_VOYAGE / ABOUT_PORT_CALL not already attached to an incident"
    )
    bookings: Optional[BookingsSummary] = None
    berth_window: BerthWindowAssessment
    delay: DelayReconciliation
    gaps: list[Gap] = []


class GetVoyageContextResult(MaritimeBaseModel):
    dossiers: list[VoyageDossier]
    matched_total: int = Field(description="How many voyages matched; > len(dossiers) means truncated")


# =============================================================================
# 3. Tool 2: get_vessel_context
# =============================================================================

class GetVesselContextInput(BaseModel):
    """Vessel profile, sister ships, voyage timeline, incident and message footprint."""
    vessel: str = Field(description="Vessel ID, name or IMO")
    voyages_limit: int = Field(8, ge=1, le=20, description="Most recent N voyages in the timeline")
    incidents: Literal["open", "all"] = "all"
    include_sisters: bool = True
    include_manager_fleet: bool = False
    message_days_back: int = Field(30, ge=1, le=180)


class VoyageTimelineRow(BaseModel):
    voyage: VoyageNode
    origin_code: str
    dest_code: str
    incident_ids: list[str] = []
    berth_window: BerthWindowAssessment


class GetVesselContextResult(MaritimeBaseModel):
    vessel: VesselProfile
    sister_vessels: list[VesselNode] = Field(default_factory=list, description="Same VesselClass, excluding this vessel")
    manager_fleet: list[VesselNode] = []
    current_voyage_id: Optional[str] = None
    timeline: list[VoyageTimelineRow] = []
    incidents: list[IncidentEvidence] = []
    class_messages: list[MessageLink] = Field(default_factory=list, description="ABOUT_CLASS bulletins for this vessel's class")
    vessel_messages: list[MessageLink] = Field(default_factory=list, description="SENT_BY_VESSEL / ABOUT_VESSEL within message_days_back")


# =============================================================================
# 4. Tool 3: search_incident_history
# =============================================================================

class SearchIncidentHistoryInput(BaseModel):
    """Find recurrences of an incident across vessel / class / manager / fleet."""
    incident_id: Optional[str] = Field(None, description="Use an existing incident as the pattern (type + corrected component)")
    incident_type: Optional[str] = Field(None, description="e.g. 'Engine cooling fault'")
    keyword: Optional[str] = Field(
        None,
        description="Matched against linked message text, e.g. 'cooling water pump'. Catches components named only in messages or corrections"
    )
    anchor_vessel: Optional[str] = Field(None, description="Vessel ID/name/IMO that defines the vessel, class and manager scopes")
    scopes: list[Literal["vessel", "class", "manager", "fleet"]] = Field(
        ["vessel", "class", "manager"],
        description="Scopes are reported separately and de-duplicated (an incident appears once, in its narrowest scope)"
    )
    window: Optional[DateWindow] = None
    statuses: list[Literal["Confirmed", "Reported", "Under review", "Dismissed"]] = ["Confirmed", "Reported", "Under review"]
    limit_per_scope: int = Field(10, ge=1, le=25)

    @model_validator(mode="after")
    def _need_pattern(self):
        if not (self.incident_id or self.incident_type or self.keyword):
            raise ValueError("Provide incident_id, incident_type or keyword")
        if any(s != "fleet" for s in self.scopes) and not self.anchor_vessel and not self.incident_id:
            raise ValueError("vessel/class/manager scopes need anchor_vessel (or incident_id)")
        return self


class ScopeResult(BaseModel):
    scope: Literal["vessel", "class", "manager", "fleet"]
    scope_label: str = Field(description="e.g. 'Meridian 8500 (V001, V004, V005, V012, ...)'")
    incidents: list[IncidentEvidence]
    total_matches: int
    distinct_vessels: int
    total_attributed_delay_hours: float = Field(0.0, description="Confirmed incidents only")


class GetIncidentHistoryResult(BaseModel):
    pattern: dict = Field(description="Resolved pattern: type, keyword, component after corrections")
    scopes: list[ScopeResult]
    bulletins: list[MessageLink] = Field(
        default_factory=list,
        description="ABOUT_CLASS / ISSUED_BY_MANAGER technical bulletins and corrections matching the pattern"
    )
    correction_chain_notes: list[str] = Field(
        default_factory=list,
        description="e.g. 'INC-201 originally cooling pump, CORRECTS_INCIDENT by tb_... -> thermostat'"
    )


# =============================================================================
# 5. Tool 4: get_cargo_exposure
# =============================================================================

class GetCargoExposureInput(BaseModel):
    """Who is affected by a voyage's delay, and how many containers."""
    voyage_id: Optional[str] = None
    vessel: Optional[str] = Field(None, description="With which='current' resolves the vessel's current voyage")
    which: Literal["current", "latest", "next"] = "current"
    customer: Optional[str] = Field(None, description="Restrict to one customer (ID or name)")
    include_statuses: list[Literal["Confirmed", "Rolled", "Cancelled"]] = ["Confirmed", "Rolled", "Cancelled"]
    include_customer_messages: bool = True

    @model_validator(mode="after")
    def _need_anchor(self):
        if not (self.voyage_id or self.vessel):
            raise ValueError("Provide voyage_id or vessel")
        return self


class BookingLine(BaseModel):
    booking: BookingNode
    rolled_to_voyage_id: Optional[str] = None
    original_voyage_id: Optional[str] = None
    # computed: promised_delivery_date vs revised ETA at destination; None if either missing
    days_between_eta_and_promise: Optional[float] = Field(
        None, description="promised date (end of day UTC) minus revised ETA; negative = already late"
    )
    promise_at_risk: Optional[bool] = None


class CustomerExposure(BaseModel):
    customer: CustomerNode
    on_board_containers: int = Field(description="Confirmed bookings still BOOKED_ON this voyage and not rolled")
    rolled_containers: int
    cancelled_containers: int
    bookings: list[BookingLine]
    messages: list[MessageLink] = []


class GetCargoExposureResult(MaritimeBaseModel):
    voyage: VoyageNode
    vessel: VesselNode
    destination: PortNode
    customers: list[CustomerExposure] = Field(description="Sorted by on_board_containers desc")
    total_on_board: int
    total_rolled: int
    total_cancelled: int
    delay: DelayReconciliation


# =============================================================================
# 6. Tool 5: scan_voyages
# =============================================================================

class ScanVoyagesInput(BaseModel):
    """Fleet-wide discovery and ranking, e.g. 'vessels due at Rotterdam next week likely to miss berth'."""
    dest_port: Optional[str] = None
    origin_port: Optional[str] = None
    window: DateWindow
    window_field: Literal["revised_eta", "original_eta", "berth_window", "departure"] = "revised_eta"
    vessel_class: Optional[str] = None
    manager: Optional[str] = None
    vessel_type: Optional[str] = None
    statuses: list[str] = Field(default_factory=lambda: ["Delayed", "Scheduled", "On schedule"])
    only_risky: bool = Field(False, description="Keep only verdict LATE/EARLY, or risk_score >= min_risk")
    min_risk: int = Field(0, ge=0, le=100)
    rank_by: Literal["berth_risk", "delay", "eta"] = "berth_risk"
    limit: int = Field(15, ge=1, le=40)
    include_risk_factors: bool = True


class RiskFactor(BaseModel):
    kind: Literal[
        "ETA_OUTSIDE_WINDOW", "LARGE_ETA_SLIP", "CONFIRMED_INCIDENT", "UNVERIFIED_INCIDENT",
        "DEST_CONGESTION_HIGH", "RECENT_ANCHORAGE_WAITS", "NO_RECENT_REPORT", "CLASS_FAULT_PATTERN",
    ]
    detail: str
    points: int = Field(description="Contribution to risk_score; weights fixed in server code and documented in the tool description")
    evidence_ids: list[str] = []
    tier: Tier


class ScanRow(BaseModel):
    rank: int
    voyage: VoyageNode
    vessel: VesselProfile
    origin_code: str
    dest_code: str
    berth_window: BerthWindowAssessment
    risk_score: int = Field(ge=0, le=100)
    risk_factors: list[RiskFactor] = []


class ScanVoyagesResult(MaritimeBaseModel):
    rows: list[ScanRow]
    matched_total: int
    dest_congestion_snapshot: list[CongestionNode] = Field(
        default_factory=list,
        description="Latest congestion rows (<= snapshot) at the destination port, if dest_port given"
    )
    scoring_note: str = "risk_score is a system inference: sum of factor points, capped at 100"


# =============================================================================
# 7. Tool 6: get_port_context
# =============================================================================

class GetPortContextInput(BaseModel):
    """Port with congestion series, agents, port calls and inbound voyages for a date window."""
    port: str = Field(description="UN/LOCODE, name or short name (Rotterdam)")
    window: DateWindow
    include_port_calls: bool = True
    include_inbound_voyages: bool = True
    include_messages: bool = True
    max_port_calls: int = Field(20, ge=1, le=50)


class PortCallRow(BaseModel):
    call: PortCallNode
    vessel: VesselNode
    voyage_id: Optional[str] = None
    links: list[MessageLink] = []


class InboundVoyageRow(BaseModel):
    voyage: VoyageNode
    vessel: VesselNode
    berth_window: BerthWindowAssessment


class GetPortContextResult(MaritimeBaseModel):
    port: PortNode
    agents: list[OrganizationNode] = Field(default_factory=list, description="Organizations BASED_AT this port")
    congestion: list[CongestionNode]
    congestion_summary: dict = Field(default_factory=dict, description="peak level/date, avg of avg_wait_hours, max vessels_at_anchor")
    port_calls: list[PortCallRow] = []
    inbound_voyages: list[InboundVoyageRow] = []
    messages: list[MessageLink] = Field(default_factory=list, description="EVENT_AT_PORT, REFERENCES_PORT, DESCRIBES_CONGESTION in window")
    gaps: list[Gap] = []


# =============================================================================
# 8. Tool 7: search_messages (self-contained with text, message_id, filename)
# =============================================================================

class SearchMessagesInput(BaseModel):
    """Search and inspect operational messages by text query, exact filename, or message ID."""
    query: Optional[str] = Field(None, description="Keyword/phrase matched against subject and cleaned_body")
    message_id: Optional[str] = Field(None, description="Exact message ID, e.g. 'noon_2026-10-06_ocean_star'")
    filename: Optional[str] = Field(None, description="Exact filename, e.g. 'noon_2026-10-06_ocean_star.txt'")
    vessel: Optional[str] = None
    voyage_id: Optional[str] = None
    port: Optional[str] = None
    incident_id: Optional[str] = None
    kinds: list[Literal["noon_report", "agent_email", "crew_message", "technical_bulletin",
                        "technical_correction", "customer_forward"]] = Field(default_factory=list)
    trust_tiers: list[Literal["T1", "T2", "T3", "T4"]] = Field(default_factory=list)
    window: Optional[DateWindow] = None
    include_post_snapshot: bool = Field(False, description="Include messages with in_snapshot = false")
    include_raw: bool = Field(False, description="True returns raw_message instead of cleaned_body (still blocked if flagged malicious)")
    limit: int = Field(10, ge=1, le=25)


class MessageHit(BaseModel):
    message: MessageNode
    linked: list[str] = Field(default_factory=list, description="Compact edge list, e.g. 'ABOUT_VOYAGE->VG-1042', 'REPORTS_INCIDENT->INC-201'")
    match_snippet: Optional[str] = None
    body: Optional[str] = Field(None, description="Full cleaned_body or raw_message when queried by message_id/filename (None if is_malicious)")
    outgoing_edges: list[MessageLink] = Field(default_factory=list)
    target_labels: dict[str, str] = Field(default_factory=dict)


class SearchMessagesResult(MaritimeBaseModel):
    hits: list[MessageHit]
    total_matches: int
    flagged_malicious_count: int = Field(0, description="Reported as a number only; bodies of flagged messages are never returned")
    detailed_view: bool = Field(False, description="True when query was targeted to specific message_id or filename")

