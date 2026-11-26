"""add reinforcement_count and index superseded_by_id

Revision ID: 7c5b3e8d2a41
Revises: 4d7a2c9e1f60
Create Date: 2026-11-26 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c5b3e8d2a41"
down_revision = "4d7a2c9e1f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("reinforcement_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        op.f("ix_memories_superseded_by_id"), "memories", ["superseded_by_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_memories_superseded_by_id"), table_name="memories")
    op.drop_column("memories", "reinforcement_count")
