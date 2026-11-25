"""use jsonb for metadata and add self-supersession check

Revision ID: 9b1e4f2a7c3d
Revises: c6f3a8d0c6d4
Create Date: 2026-11-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "9b1e4f2a7c3d"
down_revision = "c6f3a8d0c6d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "memories",
        "metadata",
        type_=postgresql.JSONB(),
        existing_type=sa.JSON(),
        existing_nullable=False,
        postgresql_using="metadata::jsonb",
    )
    op.create_check_constraint(
        "check_no_self_supersession", "memories", "id != superseded_by_id"
    )


def downgrade() -> None:
    op.drop_constraint("check_no_self_supersession", "memories", type_="check")
    op.alter_column(
        "memories",
        "metadata",
        type_=sa.JSON(),
        existing_type=postgresql.JSONB(),
        existing_nullable=False,
        postgresql_using="metadata::json",
    )
