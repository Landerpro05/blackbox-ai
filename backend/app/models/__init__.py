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
from app.models.security import (
    AuditEvent,
    AuthSession,
    RegistrationInvite,
    User,
    Workspace,
    WorkspaceMembership,
)

__all__ = [
    "AIAnalysis",
    "AuditEvent",
    "AuthSession",
    "CaseResult",
    "Issue",
    "Project",
    "RegistrationInvite",
    "Run",
    "RunStatus",
    "Severity",
    "SuiteCase",
    "TestEnvironment",
    "TestIssue",
    "TestPage",
    "TestRun",
    "TestSuite",
    "User",
    "Workspace",
    "WorkspaceMembership",
]
