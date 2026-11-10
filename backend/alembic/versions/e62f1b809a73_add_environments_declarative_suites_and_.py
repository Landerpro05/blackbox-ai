"""Add environments declarative suites and case results

Revision ID: e62f1b809a73
Revises: d51e09a3b842
"""

import sqlalchemy as sa
from alembic import op

revision = "e62f1b809a73"
down_revision = "d51e09a3b842"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_environments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("authorized_origin", sa.String(length=200), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('demo','local')", name="ck_environment_kind"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("test_environments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_test_environments_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "test_suites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("test_suites", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_test_suites_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "suite_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["suite_id"], ["test_suites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("suite_cases", schema=None) as batch_op:
        batch_op.create_index(
            "uq_suite_case_position", ["suite_id", "position"], unique=True
        )

    op.create_table(
        "case_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=True),
        sa.Column("page_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','pass','fail','error','skipped')",
            name="ck_case_result_status",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["suite_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["page_id"], ["test_pages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("case_results", schema=None) as batch_op:
        batch_op.create_index(
            "ix_case_results_run_position", ["run_id", "position"], unique=False
        )

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("environment_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(sa.Column("suite_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "environment_snapshot", sa.JSON(), server_default="{}", nullable=False
            )
        )
        batch_op.create_index(
            batch_op.f("ix_runs_suite_id"), ["suite_id"], unique=False
        )


def downgrade() -> None:
    # Native SQLite DROP COLUMN preserves runs and their existing child records.
    op.drop_index("ix_runs_suite_id", table_name="runs")
    op.drop_column("runs", "environment_snapshot")
    op.drop_column("runs", "suite_id")
    op.drop_column("runs", "environment_id")

    with op.batch_alter_table("case_results", schema=None) as batch_op:
        batch_op.drop_index("ix_case_results_run_position")

    op.drop_table("case_results")
    with op.batch_alter_table("suite_cases", schema=None) as batch_op:
        batch_op.drop_index("uq_suite_case_position")

    op.drop_table("suite_cases")
    with op.batch_alter_table("test_suites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_test_suites_project_id"))

    op.drop_table("test_suites")
    with op.batch_alter_table("test_environments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_test_environments_project_id"))

    op.drop_table("test_environments")
