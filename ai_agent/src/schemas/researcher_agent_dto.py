from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class NoDataReason(str, Enum):
    NO_MATCHING_DATA = "NO_MATCHING_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    DATA_SOURCE_ERROR = "DATA_SOURCE_ERROR"
    QUERY_OUT_OF_SCOPE = "QUERY_OUT_OF_SCOPE"


class Citation(BaseModel):
    node: str = Field(description="Knowledge-graph node label, e.g. Vessel, Voyage, PortCall")
    id: str = Field(description="Knowledge-graph node ID, e.g. V001, VOY-123, PC-102")


class ConfirmedFact(BaseModel):
    fact: str = Field(description="Concise fact directly supported by confirmed data")
    citations: List[Citation] = Field(default_factory=list)


class UnverifiedReport(BaseModel):
    report: str = Field(description="Concise unverified or pending report")
    citations: List[Citation] = Field(default_factory=list)


class SystemInference(BaseModel):
    inference: str = Field(description="Concise inference, projection, or calculation")
    rationale: str = Field(description="Why this inference follows from available evidence")
    citations: List[Citation] = Field(default_factory=list)


class ResearcherResponse(BaseModel):
    data_available: bool = Field(
        description=(
            "True only if retrieved tool data contains enough evidence to answer "
            "the user query. False if no relevant data, insufficient data, or a "
            "data-source error occurred."
        )
    )
    no_data_reason: Optional[NoDataReason] = Field(
        default=None,
        description=(
            "Required when data_available is false. Must be null when "
            "data_available is true."
        ),
    )
    no_data_explanation: Optional[str] = Field(
        default=None,
        description=(
            "Short explanation of what data was searched and why it is insufficient. "
            "Required when data_available is false."
        ),
    )
    summary: str = Field(
        description=(
            "Short operational answer. If data_available is false, summarize only "
            "that no sufficient data was found."
        )
    )
    confirmed_facts: List[ConfirmedFact] = Field(default_factory=list)
    unverified_reports: List[UnverifiedReport] = Field(default_factory=list)
    system_inferences: List[SystemInference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_no_data_consistency(self):
        if not self.data_available:
            if not self.no_data_reason:
                raise ValueError("no_data_reason is required when data_available is false")
            if not self.no_data_explanation:
                raise ValueError("no_data_explanation is required when data_available is false")
            if self.confirmed_facts or self.system_inferences:
                raise ValueError(
                    "confirmed_facts and system_inferences must be empty when "
                    "data_available is false"
                )
        else:
            if self.no_data_reason or self.no_data_explanation:
                raise ValueError(
                    "no_data_reason and no_data_explanation must be null when "
                    "data_available is true"
                )

        return self


__all__ = [
    "NoDataReason",
    "Citation",
    "ConfirmedFact",
    "UnverifiedReport",
    "SystemInference",
    "ResearcherResponse",
]
