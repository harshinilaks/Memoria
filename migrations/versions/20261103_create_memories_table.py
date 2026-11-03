"""create memories table

Revision ID: c6f3a8d0c6d4
Revises: 
Create Date: 2026-11-03 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6f3a8d0c6d4"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=False),
        sa.Column("repository_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "memory_type",
            sa.Enum("FACT", "DECISION", "OBSERVATION", "HYPOTHESIS", name="memorytype"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "SUPERSEDED", "ARCHIVED", name="memorystatus"),
            nullable=False,
        ),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["memories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memories_agent_id"), "memories", ["agent_id"], unique=False)
    op.create_index(op.f("ix_memories_namespace"), "memories", ["namespace"], unique=False)
    op.create_index(op.f("ix_memories_repository_id"), "memories", ["repository_id"], unique=False)
    op.create_index(op.f("ix_memories_session_id"), "memories", ["session_id"], unique=False)
    op.create_index(op.f("ix_memories_memory_type"), "memories", ["memory_type"], unique=False)
    op.create_index(op.f("ix_memories_status"), "memories", ["status"], unique=False)
    op.create_index("idx_namespace_status", "memories", ["namespace", "status"], unique=False)
    op.create_index("idx_repository_session", "memories", ["repository_id", "session_id"], unique=False)
    op.create_index("idx_agent_session", "memories", ["agent_id", "session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_agent_session", table_name="memories")
    op.drop_index("idx_repository_session", table_name="memories")
    op.drop_index("idx_namespace_status", table_name="memories")
    op.drop_index(op.f("ix_memories_status"), table_name="memories")
    op.drop_index(op.f("ix_memories_memory_type"), table_name="memories")
    op.drop_index(op.f("ix_memories_session_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_repository_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_namespace"), table_name="memories")
    op.drop_index(op.f("ix_memories_agent_id"), table_name="memories")
    op.drop_table("memories")
