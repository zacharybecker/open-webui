"""Add data_source table

Revision ID: e1a3f1d2b4c6
Revises: c440947495f3
Create Date: 2026-01-14

"""

from alembic import op
import sqlalchemy as sa

revision = "e1a3f1d2b4c6"
down_revision = "c440947495f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "data_source",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column(
            "knowledge_id",
            sa.Text(),
            sa.ForeignKey("knowledge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("credentials", sa.JSON(), nullable=True),
        sa.Column("sync_config", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("last_sync_at", sa.BigInteger(), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Create indexes for common queries
    op.create_index(
        "ix_data_source_knowledge_id",
        "data_source",
        ["knowledge_id"],
    )
    op.create_index(
        "ix_data_source_user_id",
        "data_source",
        ["user_id"],
    )
    op.create_index(
        "ix_data_source_source_type",
        "data_source",
        ["source_type"],
    )


def downgrade():
    op.drop_index("ix_data_source_source_type", table_name="data_source")
    op.drop_index("ix_data_source_user_id", table_name="data_source")
    op.drop_index("ix_data_source_knowledge_id", table_name="data_source")
    op.drop_table("data_source")
