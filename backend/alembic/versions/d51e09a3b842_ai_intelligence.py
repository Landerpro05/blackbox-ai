"""Persist bounded intelligence results without changing historical testing data."""

import sqlalchemy as sa
from alembic import op

revision = "d51e09a3b842"
down_revision = "c39d87a4e620"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("prompt_version", sa.String(30), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("actual_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=True),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.CheckConstraint("mode IN ('rules','llm')", name="ck_ai_mode"),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_ai_status",
        ),
    )
    op.create_index("uq_ai_active_slot", "ai_analyses", ["active_slot"], unique=True)
    op.create_index("ix_ai_run_created", "ai_analyses", ["run_id", "created_at"])
    op.create_index(
        "ix_ai_workspace_created", "ai_analyses", ["workspace_id", "created_at"]
    )


def downgrade():
    op.drop_table("ai_analyses")
