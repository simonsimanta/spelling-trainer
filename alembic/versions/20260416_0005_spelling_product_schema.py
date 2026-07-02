"""spelling product lifecycle, audio manifest, and feedback cache

Revision ID: 20260416_0005
Revises: 20260415_0004
Create Date: 2026-04-16

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260416_0005"
down_revision: Union[str, None] = "20260415_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("spelling_words", sa.Column("cefr_level", sa.String(length=10), nullable=True))
    op.add_column("spelling_words", sa.Column("mastery_state", sa.String(length=30), nullable=False, server_default="new"))
    op.add_column("spelling_words", sa.Column("known_skipped", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("spelling_words", sa.Column("introduced_at", sa.DateTime(), nullable=True))
    op.add_column("spelling_words", sa.Column("last_seen_at", sa.DateTime(), nullable=True))

    op.create_table(
        "spelling_audio_manifest",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column("voice", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", "voice", "model", name="uq_spelling_audio_manifest_variant"),
    )
    op.create_index(op.f("ix_spelling_audio_manifest_id"), "spelling_audio_manifest", ["id"], unique=False)

    op.create_table(
        "spelling_feedback_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("normalized_attempt", sa.String(length=120), nullable=False),
        sa.Column("error_pattern", sa.String(length=120), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", "normalized_attempt", "error_pattern", name="uq_spelling_feedback_cache_key"),
    )
    op.create_index(op.f("ix_spelling_feedback_cache_id"), "spelling_feedback_cache", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_spelling_feedback_cache_id"), table_name="spelling_feedback_cache")
    op.drop_table("spelling_feedback_cache")
    op.drop_index(op.f("ix_spelling_audio_manifest_id"), table_name="spelling_audio_manifest")
    op.drop_table("spelling_audio_manifest")

    op.drop_column("spelling_words", "last_seen_at")
    op.drop_column("spelling_words", "introduced_at")
    op.drop_column("spelling_words", "known_skipped")
    op.drop_column("spelling_words", "mastery_state")
    op.drop_column("spelling_words", "cefr_level")
