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
from app.models.lab import CaseResult, SuiteCase, TestEnvironment, TestSuite

__all__ = [
    "AIAnalysis",
    "CaseResult",
    "Issue",
    "Project",
    "Run",
    "RunStatus",
    "Severity",
    "SuiteCase",
    "TestEnvironment",
    "TestIssue",
    "TestPage",
    "TestRun",
    "TestSuite",
]
