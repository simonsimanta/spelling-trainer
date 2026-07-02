"""core 5k schema additions

Revision ID: 20260415_0004
Revises: 20260415_0003
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260415_0004"
down_revision: Union[str, None] = "20260415_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("spelling_words", sa.Column("short_meaning", sa.Text(), nullable=True))
    op.add_column("spelling_words", sa.Column("part_of_speech", sa.String(length=60), nullable=True))

    op.create_table(
        "spelling_word_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=40), nullable=False),
        sa.Column("source_level", sa.String(length=40), nullable=True),
        sa.Column("list_rank", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", "source_name", name="uq_spelling_word_source"),
    )
    op.create_index(op.f("ix_spelling_word_sources_id"), "spelling_word_sources", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_spelling_word_sources_id"), table_name="spelling_word_sources")
    op.drop_table("spelling_word_sources")

    op.drop_column("spelling_words", "part_of_speech")
    op.drop_column("spelling_words", "short_meaning")
