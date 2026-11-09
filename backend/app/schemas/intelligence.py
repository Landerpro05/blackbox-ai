from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.schemas.common import UTCDatetime

ShortText = Annotated[str, Field(min_length=1, max_length=350)]
EvidenceIDs = Annotated[
    list[Annotated[str, Field(max_length=60)]], Field(min_length=1, max_length=10)
]
Steps = Annotated[list[ShortText], Field(min_length=1, max_length=5)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AnalysisCreate(StrictModel):
    mode: Literal["rules", "llm"] = "rules"
    authorize_external: StrictBool = False
    max_findings: Annotated[StrictInt, Field(ge=1, le=8)] = 5
    include_history: StrictBool = True
    consent_provider: Annotated[str | None, Field(max_length=30)] = None
    consent_model: Annotated[str | None, Field(max_length=100)] = None


class Finding(StrictModel):
    hypothesis: Annotated[str, Field(min_length=1, max_length=1000)]
    confidence: Literal["low", "medium", "high"]
    evidence_ids: EvidenceIDs
    diagnostic_steps: Steps
    recommendations: Steps
    limitations: Steps


class TestPlan(StrictModel):
    template: Literal["http_status", "no_page_errors", "no_console_errors"]
    objective: ShortText
    evidence_ids: EvidenceIDs
    preconditions: Steps
    actions: Steps
    assertions: Steps
    limitations: Steps


class Relation(StrictModel):
    hypothesis: ShortText
    evidence_ids: Annotated[
        list[Annotated[str, Field(max_length=60)]], Field(min_length=2, max_length=10)
    ]


class EngineResult(StrictModel):
    summary: Annotated[str, Field(min_length=1, max_length=1800)]
    findings: Annotated[list[Finding], Field(max_length=8)]
    recommendations: Annotated[list[ShortText], Field(max_length=8)]
    suggested_tests: Annotated[list[TestPlan], Field(max_length=8)]
    hypothetical_relations: Annotated[list[Relation], Field(max_length=8)]
    limitations: Steps


class SuggestedTest(TestPlan):
    code: Annotated[str, Field(max_length=4000)]


class StoredResult(EngineResult):
    suggested_tests: Annotated[list[SuggestedTest], Field(max_length=8)]


class AnalysisResponse(BaseModel):
    id: str
    run_id: str
    mode: Literal["rules", "llm"]
    mode_label: str
    provider: str
    model: str
    status: str
    prompt_version: str
    created_at: UTCDatetime
    completed_at: UTCDatetime | None
    external_authorized_at: UTCDatetime | None
    error_message: str | None
    estimated_input_tokens: int
    estimated_output_tokens: int
    reserved_tokens: int
    reserved_cost_usd: str | None
    actual_input_tokens: int | None
    actual_output_tokens: int | None
    evidence: dict
    result: StoredResult | None


class AnalysisList(BaseModel):
    items: list[AnalysisResponse]
    total: int
    limit: int
    offset: int
