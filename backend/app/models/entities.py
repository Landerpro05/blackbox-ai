from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    JSON,
    Boolean,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def enum_column(enum: type[Enum], name: str) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [v.value for v in values],
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("max_pages BETWEEN 1 AND 50", name="ck_project_pages"),
        CheckConstraint("max_depth BETWEEN 0 AND 5", name="ck_project_depth"),
        CheckConstraint(
            "max_duration_seconds BETWEEN 10 AND 300", name="ck_project_duration"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    workspace_id: Mapped[str] = mapped_column(
        String(64), default="local", server_default="local", index=True
    )
    base_url: Mapped[str] = mapped_column(String(2048))
    max_pages: Mapped[int] = mapped_column(default=10, server_default="10")
    max_depth: Mapped[int] = mapped_column(default=2, server_default="2")
    max_duration_seconds: Mapped[int] = mapped_column(default=60, server_default="60")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    runs: Mapped[list["Run"]] = relationship(
        back_populates="project", passive_deletes=True
    )


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("pages_visited >= 0", name="ck_run_pages"),
        Index("ix_runs_created_at", "created_at"),
        Index("uq_runs_active_slot", "active_slot", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        enum_column(RunStatus, "run_status"), default=RunStatus.QUEUED
    )
    pages_visited: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workspace_id: Mapped[str] = mapped_column(
        String(64), default="local", server_default="local", index=True
    )
    target_url: Mapped[str] = mapped_column(String(2048), default="", server_default="")
    limits: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    issues_found: Mapped[int] = mapped_column(default=0, server_default="0")
    request_count: Mapped[int] = mapped_column(default=0, server_default="0")
    duration_ms: Mapped[int] = mapped_column(default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(String(500))
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    active_slot: Mapped[int | None] = mapped_column()
    project: Mapped[Project] = relationship(back_populates="runs")
    issues: Mapped[list["Issue"]] = relationship(
        back_populates="run", passive_deletes=True
    )
    pages: Mapped[list["TestPage"]] = relationship(
        back_populates="run", passive_deletes=True
    )


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved', 'ignored')", name="ck_issue_status"
        ),
        Index("ix_issues_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(60))
    severity: Mapped[Severity] = mapped_column(
        enum_column(Severity, "issue_severity"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(200), default="", server_default="")
    affected_url: Mapped[str] = mapped_column(String(2048))
    evidence_path: Mapped[str | None] = mapped_column(String(512))
    reproduction_steps: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    run: Mapped[Run] = relationship(back_populates="issues")


class TestPage(Base):
    __tablename__ = "test_pages"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    test_run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    status_code: Mapped[int | None] = mapped_column()
    load_time_ms: Mapped[int] = mapped_column()
    depth: Mapped[int] = mapped_column(default=0)
    screenshot_path: Mapped[str | None] = mapped_column(String(100))
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    run: Mapped[Run] = relationship(back_populates="pages")


# Preserve the existing tables, imports and historical records.
TestRun = Run
TestIssue = Issue
