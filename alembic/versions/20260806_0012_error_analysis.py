"""Add structured spelling error analysis and suggestion evidence."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0012"
down_revision: Union[str, None] = "20260804_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("english_variant", sa.String(length=10), server_default="en-GB", nullable=False),
    )
    op.add_column("spelling_suggestions", sa.Column("pattern_code", sa.String(length=80), nullable=True))
    op.add_column(
        "spelling_suggestions",
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "spelling_suggestions",
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "spelling_suggestions",
        sa.Column("validation_status", sa.String(length=30), server_default="pending", nullable=False),
    )
    op.add_column("spelling_suggestions", sa.Column("last_suggested_at", sa.DateTime(), nullable=True))

    op.add_column("spelling_feedback_cache", sa.Column("analysis_json", sa.JSON(), nullable=True))
    op.add_column(
        "spelling_feedback_cache",
        sa.Column("model", sa.String(length=80), server_default="", nullable=False),
    )
    op.add_column(
        "spelling_feedback_cache",
        sa.Column("prompt_version", sa.String(length=40), server_default="legacy", nullable=False),
    )
    op.add_column(
        "spelling_feedback_cache",
        sa.Column("locale", sa.String(length=10), server_default="en-GB", nullable=False),
    )

    op.create_table(
        "spelling_error_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("primary_pattern", sa.String(length=80), nullable=False),
        sa.Column("secondary_patterns", sa.JSON(), nullable=False),
        sa.Column("edit_operations", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("memory_strategy", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("analysis_source", sa.String(length=30), server_default="fallback", nullable=False),
        sa.Column("model", sa.String(length=80), server_default="", nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("locale", sa.String(length=10), server_default="en-GB", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["spelling_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_spelling_error_analysis_attempt"),
    )
    op.create_index("ix_spelling_error_analyses_id", "spelling_error_analyses", ["id"], unique=False)
    op.create_index(
        "ix_spelling_error_analyses_attempt_id", "spelling_error_analyses", ["attempt_id"], unique=False
    )

    op.create_table(
        "spelling_suggestion_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("suggestion_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("source_word_id", sa.Integer(), nullable=False),
        sa.Column("pattern_code", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["spelling_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suggestion_id"], ["spelling_suggestions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suggestion_id", "attempt_id", name="uq_spelling_suggestion_evidence_attempt"),
    )
    op.create_index("ix_spelling_suggestion_evidence_id", "spelling_suggestion_evidence", ["id"], unique=False)
    op.create_index(
        "ix_spelling_suggestion_evidence_suggestion_id",
        "spelling_suggestion_evidence",
        ["suggestion_id"],
        unique=False,
    )
    op.create_index(
        "ix_spelling_suggestion_evidence_attempt_id",
        "spelling_suggestion_evidence",
        ["attempt_id"],
        unique=False,
    )
    op.create_index(
        "ix_spelling_suggestion_evidence_source_word_id",
        "spelling_suggestion_evidence",
        ["source_word_id"],
        unique=False,
    )

    if _is_postgresql():
        for table_name in ("spelling_error_analyses", "spelling_suggestion_evidence"):
            op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY "deny_browser_data_api" ON public."{table_name}" '
                "AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)"
            )


def downgrade() -> None:
    if _is_postgresql():
        for table_name in ("spelling_suggestion_evidence", "spelling_error_analyses"):
            op.execute(f'DROP POLICY "deny_browser_data_api" ON public."{table_name}"')
            op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')

    op.drop_index("ix_spelling_suggestion_evidence_source_word_id", table_name="spelling_suggestion_evidence")
    op.drop_index("ix_spelling_suggestion_evidence_attempt_id", table_name="spelling_suggestion_evidence")
    op.drop_index("ix_spelling_suggestion_evidence_suggestion_id", table_name="spelling_suggestion_evidence")
    op.drop_index("ix_spelling_suggestion_evidence_id", table_name="spelling_suggestion_evidence")
    op.drop_table("spelling_suggestion_evidence")
    op.drop_index("ix_spelling_error_analyses_attempt_id", table_name="spelling_error_analyses")
    op.drop_index("ix_spelling_error_analyses_id", table_name="spelling_error_analyses")
    op.drop_table("spelling_error_analyses")

    op.drop_column("spelling_feedback_cache", "locale")
    op.drop_column("spelling_feedback_cache", "prompt_version")
    op.drop_column("spelling_feedback_cache", "model")
    op.drop_column("spelling_feedback_cache", "analysis_json")
    op.drop_column("spelling_suggestions", "last_suggested_at")
    op.drop_column("spelling_suggestions", "validation_status")
    op.drop_column("spelling_suggestions", "evidence_count")
    op.drop_column("spelling_suggestions", "confidence")
    op.drop_column("spelling_suggestions", "pattern_code")
    op.drop_column("app_settings", "english_variant")
