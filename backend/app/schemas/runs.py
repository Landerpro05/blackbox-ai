from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.schemas.common import UTCDatetime


class RunLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_pages: Annotated[StrictInt, Field(ge=1, le=20)] = 10
    max_depth: Annotated[StrictInt, Field(ge=0, le=3)] = 2
    navigation_timeout_seconds: Annotated[StrictInt, Field(ge=1, le=30)] = 15
    timeout_seconds: Annotated[StrictInt, Field(ge=1, le=180)] = 120
    max_requests: Annotated[StrictInt, Field(ge=1, le=200)] = 100


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorize_demo: Literal[True]
    limits: RunLimits = Field(default_factory=RunLimits)

    @field_validator("authorize_demo", mode="before")
    @classmethod
    def explicit_authorization(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("Debes autorizar explícitamente la demostración.")
        return True


class RunResponse(BaseModel):
    id: str
    project_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    created_at: UTCDatetime
    started_at: UTCDatetime | None
    finished_at: UTCDatetime | None
    pages_scanned: int
    issues_found: int
    request_count: int
    duration_ms: int
    error_message: str | None
    cancellation_requested: bool
    limits: RunLimits


class IssueResponse(BaseModel):
    id: str
    test_run_id: str
    type: str
    severity: str
    title: str
    description: str
    url: str
    evidence_url: str | None
    created_at: UTCDatetime


class PageResponse(BaseModel):
    id: str
    test_run_id: str
    url: str
    status_code: int | None
    load_time_ms: int
    depth: int
    screenshot_url: str | None
    scanned_at: UTCDatetime
