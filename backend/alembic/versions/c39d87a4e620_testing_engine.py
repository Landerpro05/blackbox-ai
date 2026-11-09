"""Persist analysis progress, limits, pages and evidence without rebuilding tables.

Revision ID: c39d87a4e620
Revises: b72c4f2810a1
"""

from alembic import op
import sqlalchemy as sa

revision = "c39d87a4e620"
down_revision = "b72c4f2810a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = [
        sa.Column(
            "workspace_id", sa.String(64), nullable=False, server_default="local"
        ),
        sa.Column("target_url", sa.String(2048), nullable=False, server_default=""),
        sa.Column("limits", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("issues_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "cancellation_requested", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("active_slot", sa.Integer(), nullable=True),
    ]
    for column in columns:
        op.add_column("runs", column)
    op.create_index("ix_runs_workspace_id", "runs", ["workspace_id"])
    op.create_index("uq_runs_active_slot", "runs", ["active_slot"], unique=True)
    op.add_column(
        "issues", sa.Column("title", sa.String(200), nullable=False, server_default="")
    )
    op.execute(
        "UPDATE runs SET workspace_id = (SELECT workspace_id FROM projects WHERE projects.id = runs.project_id), target_url = (SELECT base_url FROM projects WHERE projects.id = runs.project_id), issues_found = (SELECT COUNT(*) FROM issues WHERE issues.run_id = runs.id)"
    )
    op.create_table(
        "test_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "test_run_id",
            sa.String(36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("load_time_ms", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("screenshot_path", sa.String(100), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_test_pages_test_run_id", "test_pages", ["test_run_id"])


def downgrade() -> None:
    op.drop_table("test_pages")
    op.drop_column("issues", "title")
    op.drop_index("uq_runs_active_slot", table_name="runs")
    op.drop_index("ix_runs_workspace_id", table_name="runs")
    for name in (
        "active_slot",
        "cancellation_requested",
        "error_message",
        "duration_ms",
        "request_count",
        "issues_found",
        "limits",
        "target_url",
        "workspace_id",
    ):
        op.drop_column("runs", name)
