from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import new_id, utc_now


class TestEnvironment(Base):
    __tablename__ = "test_environments"
    __test__ = False
    __table_args__ = (
        CheckConstraint("kind IN ('demo','local')", name="ck_environment_kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))
    base_url: Mapped[str] = mapped_column(String(2048))
    authorized_origin: Mapped[str] = mapped_column(String(200))
    limits: Mapped[dict] = mapped_column(JSON)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TestSuite(Base):
    __tablename__ = "test_suites"
    __test__ = False
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SuiteCase(Base):
    __tablename__ = "suite_cases"
    __table_args__ = (
        Index("uq_suite_case_position", "suite_id", "position", unique=True),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("test_suites.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column()
    enabled: Mapped[bool] = mapped_column(default=True)
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class CaseResult(Base):
    __tablename__ = "case_results"
    __table_args__ = (
        Index("ix_case_results_run_position", "run_id", "position"),
        CheckConstraint(
            "status IN ('pending','pass','fail','error','skipped')",
            name="ck_case_result_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("suite_cases.id", ondelete="SET NULL")
    )
    page_id: Mapped[str | None] = mapped_column(
        ForeignKey("test_pages.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column()
    definition: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    message: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(default=0)
