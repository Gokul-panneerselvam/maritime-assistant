"""
Evaluation Engine Data Models & Schemas.
Defines benchmark questions, metric scores, evaluation results, and benchmark reports.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DataAvailabilityStatus(str, Enum):
    """Data availability and query nature status."""
    ANSWERABLE = "Answerable with Data"
    UNANSWERABLE_FALSE_ASSUMPTION = "Unanswerable / False Assumption"
    UNANSWERABLE_FEED_OFFLINE = "Unanswerable / False Assumption & Feed Offline"
    OUT_OF_SCOPE = "Out of Scope"
    PROFANITY_TOXIC = "Profanity / Toxic Content"


class QuestionCategory(str, Enum):
    """Operational categories for benchmark queries."""
    DELAY_ROOT_CAUSE = "Delay Root Cause & Operational Actions"
    CROSS_FLEET_INCIDENT = "Cross-Fleet Incident History"
    FALSE_ASSUMPTION = "False Assumption Refutation"
    CARGO_EXPOSURE = "Cargo Impact & Customer Exposure"
    BERTH_CONGESTION = "Port Berth Window & Congestion"
    GUARDRAIL_SCOPE = "Guardrail Scope Enforcement (Out-of-Scope)"
    GUARDRAIL_SAFETY = "Guardrail Safety & Profanity Defense"


class DateWindow(BaseModel):
    """Expected ISO-8601 UTC window a relative or local date phrase must resolve to."""
    phrase: str = Field(description="Date phrase as written in the query, e.g. 'last month'")
    start_utc: str = Field(description="Window start, e.g. 2026-09-01T00:00:00Z")
    end_utc: str = Field(description="Window end, e.g. 2026-09-30T23:59:59Z")
    tolerance_hours: float = Field(
        default=0.0,
        description="Slack applied to both ends when matching resolver output (e.g. port-local day vs UTC day)"
    )


class ExpectedResolution(BaseModel):
    """Expected output of the entity resolution node (Node 2)."""
    vessel_ids: List[str] = Field(default_factory=list, description="Canonical vessel IDs, e.g. V001")
    port_codes: List[str] = Field(default_factory=list, description="UN/LOCODEs, e.g. NLRTM")
    voyage_ids: List[str] = Field(
        default_factory=list,
        description="Voyage IDs that are explicit in the query text; the resolver has no data access, so implied voyages are not listed"
    )
    date_windows: List[DateWindow] = Field(default_factory=list)
    allow_extra_vessels: bool = Field(
        default=False,
        description=(
            "If True, extra resolved vessels are not penalized (score is recall of vessel_ids). "
            "Used for same-class / same-manager questions where the resolver legitimately expands the fleet group."
        )
    )
    should_clarify: bool = Field(default=False, description="True if the resolver is expected to ask a clarification question")


class BenchmarkQuestion(BaseModel):
    """Defines a standardized benchmark evaluation case with ground-truth expectations."""
    id: str = Field(description="Unique question identifier, e.g. Q1, Q6, Q11, Q12")
    pair_id: str = Field(description="Evaluation pair or category identifier, e.g. Pair-1, Pair-2, Guardrail")
    is_reference: bool = Field(description="True if original reference question (Q1-Q5), False if parallel or guardrail")
    parallel_counterpart_id: Optional[str] = Field(default=None, description="Paired question ID (e.g. Q6 for Q1)")
    query: str = Field(description="The prompt submitted to the agent")
    category: QuestionCategory = Field(description="Operational category")
    data_availability: DataAvailabilityStatus = Field(description="Availability classification")
    
    # Ground truth expectations
    expected_status: str = Field(
        default="SUCCESS",
        description="Expected MaritimeAgentResponse status: SUCCESS, FALSE_PREMISE, DATA_UNAVAILABLE, or OUT_OF_SCOPE_REFUSAL"
    )
    target_vessels: List[str] = Field(
        default_factory=list,
        description="Vessel names or IDs expected to be identified"
    )
    target_voyages: List[str] = Field(
        default_factory=list,
        description="Voyage IDs expected to be identified"
    )
    target_ports: List[str] = Field(
        default_factory=list,
        description="Port codes or names relevant to the query"
    )
    target_incidents: List[str] = Field(
        default_factory=list,
        description="Incident IDs relevant to the query"
    )
    expected_delay_hours: Optional[float] = Field(
        default=None,
        description="Total or specific delay hours expected in answer"
    )
    expected_container_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Customer-to-confirmed container counts on board"
    )
    expected_false_assumptions: List[str] = Field(
        default_factory=list,
        description="Key false assumptions that must be explicitly refuted"
    )
    negative_constraints: List[str] = Field(
        default_factory=list,
        description="Hallucinations, prompt injection lures, or false claims that must NEVER appear"
    )
    expected_operational_checks: List[str] = Field(
        default_factory=list,
        description="Key operational follow-up recommendations expected from dispatch ops"
    )
    cross_fleet_checks: Dict[str, Any] = Field(
        default_factory=dict,
        description="Expected cross-fleet incident findings (same vessel, same class, same technical manager)"
    )
    guardrail_expected_verdict: Optional[str] = Field(
        default=None,
        description="Expected guardrail verdict if a guardrail question (e.g. OUT_OF_SCOPE, TOXIC_CONTENT)"
    )
    acceptable_statuses: List[str] = Field(
        default_factory=list,
        description=(
            "Statuses the current pipeline can realistically emit for this case besides expected_status "
            "(e.g. the validator never emits FALSE_PREMISE). Scored as partial credit, not a full match."
        )
    )
    expected_resolution: Optional[ExpectedResolution] = Field(
        default=None,
        description="Expected entity-resolution output; None for guardrail cases where the resolver must not run"
    )
    expected_plan_elements: List[str] = Field(
        default_factory=list,
        description="Things the research plan must cover, judged semantically by the planner evaluator"
    )
    expected_tools: List[str] = Field(
        default_factory=list,
        description="MCP domain tools a good plan or trajectory is expected to use"
    )
    expected_numeric_facts: Dict[str, float] = Field(
        default_factory=dict,
        description="Named numbers that must appear correctly in the answer (hours, counts, totals)"
    )
    expected_citations: List[str] = Field(
        default_factory=list,
        description="Entity citations ('Incident:INC-201') or message files ('File:noon_...txt') a grounded answer should cite"
    )
    ground_truth_summary: str = Field(
        description="Comprehensive narrative explanation of the verified ground truth"
    )


class MetricScore(BaseModel):
    """Score for a specific evaluation dimension."""
    metric_name: str = Field(description="Name of the metric, e.g. Epistemic Segregation")
    score: float = Field(ge=0.0, le=1.0, description="Normalized score between 0.0 and 1.0")
    passed: bool = Field(description="True if score >= passing threshold")
    weight: float = Field(default=1.0, description="Weight of this metric in composite score")
    reason: str = Field(description="Explanation of score justification")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed sub-metrics")


class EvaluationResult(BaseModel):
    """Complete evaluation outcome for a single benchmark question."""
    question_id: str
    pair_id: str
    is_reference: bool
    query: str
    category: str
    data_availability: str
    response_status: str
    status_match: bool
    agent_summary: str
    metrics: Dict[str, MetricScore]
    overall_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    latency_sec: float = 0.0
    negative_constraint_violations: List[str] = Field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None
    node_trace: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Per-node updates, tool calls and timings captured from a live run (None for offline runs)"
    )


class BenchmarkSummary(BaseModel):
    """Aggregate benchmark performance report."""
    timestamp: str
    total_questions: int
    passed_questions: int
    overall_pass_rate: float
    average_score: float
    
    # Pillar Scores
    epistemic_fidelity_score: float
    factual_accuracy_score: float
    robustness_score: float
    operational_actionability_score: float
    guardrail_safety_score: float
    
    # Cohort Breakdown
    reference_average_score: float
    parallel_average_score: float
    guardrail_average_score: float
    category_scores: Dict[str, float] = Field(default_factory=dict)
    
    # Detailed results
    results: List[EvaluationResult] = Field(default_factory=list)
