"""spelling only app profile, content, and gamification

Revision ID: 20260417_0006
Revises: 20260416_0005
Create Date: 2026-04-17

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260417_0006"
down_revision: Union[str, None] = "20260416_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    for table_name in ["daily_logs", "daily_summaries", "journal_entries", "habits", "habit_categories"]:
        if _table_exists(table_name):
            op.drop_table(table_name)

    if not _column_exists("spelling_session_items", "choices"):
        op.add_column("spelling_session_items", sa.Column("choices", sa.JSON(), nullable=True))

    op.create_table(
        "learner_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default="Ananya"),
        sa.Column("avatar", sa.String(length=80), nullable=False, server_default="student"),
        sa.Column("level_label", sa.String(length=40), nullable=False, server_default="Level 4"),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("practice_time_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_goal", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("last_practice_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("theme", sa.String(length=40), nullable=False, server_default="light"),
        sa.Column("tts_voice", sa.String(length=40), nullable=False, server_default="alloy"),
        sa.Column("tts_model", sa.String(length=80), nullable=False, server_default="gpt-4o-mini-tts"),
        sa.Column("ai_model", sa.String(length=80), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("ai_generation_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content_bulk_limit", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "spelling_word_content",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=True),
        sa.Column("ipa", sa.String(length=255), nullable=True),
        sa.Column("part_of_speech", sa.String(length=80), nullable=True),
        sa.Column("examples", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("word_family", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="generated"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", name="uq_spelling_word_content_word"),
    )
    op.create_index(op.f("ix_spelling_word_content_id"), "spelling_word_content", ["id"], unique=False)

    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activity_events_id"), "activity_events", ["id"], unique=False)

    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unlocked_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_achievement_code"),
    )
    op.create_index(op.f("ix_achievements_id"), "achievements", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_achievements_id"), table_name="achievements")
    op.drop_table("achievements")
    op.drop_index(op.f("ix_activity_events_id"), table_name="activity_events")
    op.drop_table("activity_events")
    op.drop_index(op.f("ix_spelling_word_content_id"), table_name="spelling_word_content")
    op.drop_table("spelling_word_content")
    op.drop_table("app_settings")
    op.drop_table("learner_profile")
    if _column_exists("spelling_session_items", "choices"):
        op.drop_column("spelling_session_items", "choices")
