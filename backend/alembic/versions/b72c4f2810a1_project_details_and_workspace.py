"""Add project descriptions and a server-owned workspace scope.

Revision ID: b72c4f2810a1
Revises: 8d56efc7b5b4
"""

from alembic import op
import sqlalchemy as sa

revision = "b72c4f2810a1"
down_revision = "8d56efc7b5b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add columns without rebuilding projects: preserve related runs and issues.
    op.add_column(
        "projects",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "projects",
        sa.Column(
            "workspace_id", sa.String(64), nullable=False, server_default="local"
        ),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_column("projects", "workspace_id")
    op.drop_column("projects", "description")
