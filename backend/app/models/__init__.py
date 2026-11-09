"""Import models so Alembic can discover the complete metadata."""
from app.models.entities import (
    Issue,
    Project,
    Run,
    RunStatus,
    Severity,
    TestIssue,
    TestPage,
    TestRun,
)
from app.models.intelligence import AIAnalysis

__all__ = [
    "AIAnalysis",
    "Issue",
    "Project",
    "Run",
    "RunStatus",
    "Severity",
    "TestIssue",
    "TestPage",
    "TestRun",
]
