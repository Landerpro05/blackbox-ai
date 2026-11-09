"""Import models so Alembic can discover the complete metadata."""

from app.models.entities import (
    Issue,
    Project,
    Run,
    RunStatus,
    Severity,
    TestRun,
    TestIssue,
    TestPage,
)

__all__ = [
    "Issue",
    "Project",
    "Run",
    "RunStatus",
    "Severity",
    "TestRun",
    "TestIssue",
    "TestPage",
]
