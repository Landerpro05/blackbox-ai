from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models import RunStatus
from app.schemas.common import UTCDatetime


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "blackbox-ai"
    version: str = "0.1.0"
    environment: str
    database: Literal["connected"] = "connected"


class Metrics(BaseModel):
    projects: int
    runs: int
    issues: int
    critical_issues: int
    active_runs: int


class TrendPoint(BaseModel):
    date: date
    runs: int
    issues: int


class RecentRun(BaseModel):
    id: str
    project_name: str
    status: RunStatus
    pages_visited: int
    issue_count: int
    created_at: UTCDatetime


class ProjectOverview(BaseModel):
    id: str
    name: str
    base_url: str
    run_count: int


class DashboardResponse(BaseModel):
    metrics: Metrics
    trend: list[TrendPoint]
    recent_runs: list[RecentRun]
    projects: list[ProjectOverview]
    generated_at: UTCDatetime
