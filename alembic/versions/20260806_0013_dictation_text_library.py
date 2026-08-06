"""Add the hybrid dictation text library."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0013"
down_revision: Union[str, None] = "20260806_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "spelling_dictation_texts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("locale", sa.String(length=10), server_default="en-GB", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="reviewed", nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("sentence_count", sa.Integer(), nullable=False),
        sa.Column("quality_warnings", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("allow_ai_adaptation", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("adapted_from_id", sa.Integer(), nullable=True),
        sa.Column("adaptation_key", sa.String(length=64), nullable=True),
        sa.Column("ai_model", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["adapted_from_id"], ["spelling_dictation_texts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adaptation_key", name="uq_spelling_dictation_text_adaptation_key"),
        sa.UniqueConstraint("content_hash", name="uq_spelling_dictation_text_content_hash"),
    )
    op.create_index("ix_spelling_dictation_texts_id", "spelling_dictation_texts", ["id"], unique=False)
    op.create_index(
        "ix_spelling_dictation_texts_adapted_from_id",
        "spelling_dictation_texts",
        ["adapted_from_id"],
        unique=False,
    )
    op.create_index(
        "ix_spelling_dictation_texts_level_status_last_used",
        "spelling_dictation_texts",
        ["level", "status", "last_used_at"],
        unique=False,
    )

    op.create_table(
        "spelling_dictation_text_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text_id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("target_term", sa.String(length=120), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["text_id"], ["spelling_dictation_texts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("text_id", "target_term", name="uq_spelling_dictation_target_term"),
    )
    op.create_index(
        "ix_spelling_dictation_text_targets_id", "spelling_dictation_text_targets", ["id"], unique=False
    )
    op.create_index(
        "ix_spelling_dictation_text_targets_text_id",
        "spelling_dictation_text_targets",
        ["text_id"],
        unique=False,
    )
    op.create_index(
        "ix_spelling_dictation_text_targets_word_id",
        "spelling_dictation_text_targets",
        ["word_id"],
        unique=False,
    )

    if _is_postgresql():
        for table_name in ("spelling_dictation_texts", "spelling_dictation_text_targets"):
            op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY "deny_browser_data_api" ON public."{table_name}" '
                "AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)"
            )


def downgrade() -> None:
    if _is_postgresql():
        for table_name in ("spelling_dictation_text_targets", "spelling_dictation_texts"):
            op.execute(f'DROP POLICY "deny_browser_data_api" ON public."{table_name}"')
            op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')

    op.drop_index("ix_spelling_dictation_text_targets_word_id", table_name="spelling_dictation_text_targets")
    op.drop_index("ix_spelling_dictation_text_targets_text_id", table_name="spelling_dictation_text_targets")
    op.drop_index("ix_spelling_dictation_text_targets_id", table_name="spelling_dictation_text_targets")
    op.drop_table("spelling_dictation_text_targets")
    op.drop_index("ix_spelling_dictation_texts_level_status_last_used", table_name="spelling_dictation_texts")
    op.drop_index("ix_spelling_dictation_texts_adapted_from_id", table_name="spelling_dictation_texts")
    op.drop_index("ix_spelling_dictation_texts_id", table_name="spelling_dictation_texts")
    op.drop_table("spelling_dictation_texts")
