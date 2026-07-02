"""reset spelling v2 sessions, patterns, and richer attempts

Revision ID: 20260415_0003
Revises: 20260412_0002
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260415_0003"
down_revision: Union[str, None] = "20260412_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_table_if_exists(table_name: str) -> None:
    if table_name in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(table_name)


def upgrade() -> None:
    # Spelling history is intentionally reset here so the v2 schema can be
    # created consistently on SQLite and Postgres without ALTER constraint hacks.
    for table_name in [
        "spelling_user_pattern_stats",
        "spelling_confusion_group_words",
        "spelling_confusion_groups",
        "spelling_word_patterns",
        "spelling_patterns",
        "spelling_suggestions",
        "spelling_attempts",
        "spelling_session_items",
        "spelling_sessions",
        "spelling_reviews",
        "spelling_words",
    ]:
        _drop_table_if_exists(table_name)

    op.create_table(
        "spelling_words",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column("level", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("ipa", sa.String(length=255), nullable=True),
        sa.Column("phonetic_hint", sa.String(length=255), nullable=True),
        sa.Column("chunked_form", sa.String(length=255), nullable=True),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column("difficulty_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("frequency_rank", sa.Integer(), nullable=True),
        sa.Column("source_list", sa.String(length=255), nullable=True),
        sa.Column("is_confusable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mastery_threshold", sa.Integer(), nullable=False, server_default="5"),
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
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.3"),
        sa.Column("stability_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("lapse_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("average_response_ms", sa.Float(), nullable=True),
        sa.Column("forced_correction_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_stage", sa.String(length=20), nullable=False, server_default="learning"),
        sa.Column("mastery_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("consecutive_forced_corrections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", name="uq_spelling_review_word"),
    )
    op.create_index(op.f("ix_spelling_reviews_id"), "spelling_reviews", ["id"], unique=False)

    op.create_table(
        "spelling_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("session_type", sa.String(length=40), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_first_try", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forced_corrections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confusion_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sentence_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spelling_sessions_id"), "spelling_sessions", ["id"], unique=False)

    op.create_table(
        "spelling_session_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("item_type", sa.String(length=40), nullable=False),
        sa.Column("source_reason", sa.String(length=255), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("forced_correction_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["session_id"], ["spelling_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "order_index", name="uq_spelling_session_item_order"),
    )
    op.create_index(op.f("ix_spelling_session_items_id"), "spelling_session_items", ["id"], unique=False)
    op.create_index("ix_spelling_session_items_session_id", "spelling_session_items", ["session_id"])
    op.create_index("ix_spelling_session_items_word_id", "spelling_session_items", ["word_id"])

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
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=40), nullable=False, server_default="word_dictation"),
        sa.Column("input_method", sa.String(length=50), nullable=False, server_default="typed"),
        sa.Column("diff_json", sa.JSON(), nullable=True),
        sa.Column("chunk_feedback", sa.Text(), nullable=True),
        sa.Column("phonetic_feedback", sa.JSON(), nullable=True),
        sa.Column("retry_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("was_forced_correction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("session_item_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["spelling_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_item_id"], ["spelling_session_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spelling_attempts_id"), "spelling_attempts", ["id"], unique=False)
    op.create_index("ix_spelling_attempts_session_id", "spelling_attempts", ["session_id"])
    op.create_index("ix_spelling_attempts_session_item_id", "spelling_attempts", ["session_item_id"])

    op.create_table(
        "spelling_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term", name="uq_spelling_suggestion_term"),
    )
    op.create_index(op.f("ix_spelling_suggestions_id"), "spelling_suggestions", ["id"], unique=False)

    op.create_table(
        "spelling_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("examples", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("difficulty_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_spelling_pattern_code"),
    )
    op.create_index(op.f("ix_spelling_patterns_id"), "spelling_patterns", ["id"], unique=False)

    op.create_table(
        "spelling_word_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False, server_default="1.0"),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["spelling_patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", "pattern_id", name="uq_spelling_word_pattern"),
    )
    op.create_index(op.f("ix_spelling_word_patterns_id"), "spelling_word_patterns", ["id"], unique=False)

    op.create_table(
        "spelling_confusion_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("difficulty_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_spelling_confusion_group_name"),
    )
    op.create_index(op.f("ix_spelling_confusion_groups_id"), "spelling_confusion_groups", ["id"], unique=False)

    op.create_table(
        "spelling_confusion_group_words",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["group_id"], ["spelling_confusion_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "word_id", name="uq_spelling_confusion_group_word"),
    )
    op.create_index(op.f("ix_spelling_confusion_group_words_id"), "spelling_confusion_group_words", ["id"], unique=False)

    op.create_table(
        "spelling_user_pattern_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("total_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("incorrect_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_error_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mastery_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pattern_id"], ["spelling_patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pattern_id", name="uq_spelling_user_pattern_stat_pattern"),
    )
    op.create_index(op.f("ix_spelling_user_pattern_stats_id"), "spelling_user_pattern_stats", ["id"], unique=False)


def downgrade() -> None:
    for table_name in [
        "spelling_user_pattern_stats",
        "spelling_confusion_group_words",
        "spelling_confusion_groups",
        "spelling_word_patterns",
        "spelling_patterns",
        "spelling_suggestions",
        "spelling_attempts",
        "spelling_session_items",
        "spelling_sessions",
        "spelling_reviews",
        "spelling_words",
    ]:
        op.drop_table(table_name)

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
