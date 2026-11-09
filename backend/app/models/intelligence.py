from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import new_id, utc_now


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        CheckConstraint("mode IN ('rules','llm')", name="ck_ai_mode"),
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_ai_status",
        ),
        Index("uq_ai_active_slot", "active_slot", unique=True),
        Index("ix_ai_run_created", "run_id", "created_at"),
        Index("ix_ai_workspace_created", "workspace_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    workspace_id: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    prompt_version: Mapped[str] = mapped_column(String(30))
    context_hash: Mapped[str] = mapped_column(String(64))
    evidence_json: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    estimated_input_tokens: Mapped[int] = mapped_column(default=0)
    estimated_output_tokens: Mapped[int] = mapped_column(default=0)
    reserved_tokens: Mapped[int] = mapped_column(default=0)
    reserved_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    actual_input_tokens: Mapped[int | None] = mapped_column()
    actual_output_tokens: Mapped[int | None] = mapped_column()
    active_slot: Mapped[int | None] = mapped_column()
