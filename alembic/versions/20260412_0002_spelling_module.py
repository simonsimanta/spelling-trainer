"""add spelling module tables

Revision ID: 20260412_0002
Revises: 20260411_0001
Create Date: 2026-04-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260412_0002"
down_revision: Union[str, None] = "20260411_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "spelling_words",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column("level", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term", name="uq_spelling_word_term"),
    )
    op.create_index(op.f("ix_spelling_words_id"), "spelling_words", ["id"], unique=False)

    op.create_table(
        "spelling_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("consecutive_correct", sa.Integer(), nullable=False),
        sa.Column("incorrect_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", name="uq_spelling_review_word"),
    )
    op.create_index(op.f("ix_spelling_reviews_id"), "spelling_reviews", ["id"], unique=False)

    op.create_table(
        "spelling_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("attempt_date", sa.Date(), nullable=False),
        sa.Column("attempt_text", sa.String(length=120), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("points_awarded", sa.Integer(), nullable=False),
        sa.Column("error_pattern", sa.String(length=120), nullable=True),
        sa.Column("llm_feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spelling_attempts_id"), "spelling_attempts", ["id"], unique=False)

    op.create_table(
        "spelling_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term", name="uq_spelling_suggestion_term"),
    )
    op.create_index(op.f("ix_spelling_suggestions_id"), "spelling_suggestions", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_spelling_suggestions_id"), table_name="spelling_suggestions")
    op.drop_table("spelling_suggestions")

    op.drop_index(op.f("ix_spelling_attempts_id"), table_name="spelling_attempts")
    op.drop_table("spelling_attempts")

    op.drop_index(op.f("ix_spelling_reviews_id"), table_name="spelling_reviews")
    op.drop_table("spelling_reviews")

    op.drop_index(op.f("ix_spelling_words_id"), table_name="spelling_words")
    op.drop_table("spelling_words")
