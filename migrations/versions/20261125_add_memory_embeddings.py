"""add pgvector extension and memory_embeddings table

Revision ID: 4d7a2c9e1f60
Revises: 9b1e4f2a7c3d
Create Date: 2026-11-25 01:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = "4d7a2c9e1f60"
down_revision = "9b1e4f2a7c3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "memory_embeddings",
        sa.Column("memory_id", sa.String(length=36), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("memory_id"),
    )
    op.create_index(
        op.f("ix_memory_embeddings_model"), "memory_embeddings", ["model"], unique=False
    )
    op.create_index(
        "idx_memory_embeddings_hnsw",
        "memory_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("idx_memory_embeddings_hnsw", table_name="memory_embeddings")
    op.drop_index(op.f("ix_memory_embeddings_model"), table_name="memory_embeddings")
    op.drop_table("memory_embeddings")
    op.execute("DROP EXTENSION IF EXISTS vector")
