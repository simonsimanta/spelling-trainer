"""initial schema

Revision ID: 20260411_0001
Revises: 
Create Date: 2026-04-11

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260411_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "habit_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_habit_categories_id"), "habit_categories", ["id"], unique=False)

    op.create_table(
        "habits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("target_per_week", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["habit_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_habits_id"), "habits", ["id"], unique=False)

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_date"),
    )
    op.create_index(op.f("ix_journal_entries_id"), "journal_entries", ["id"], unique=False)

    op.create_table(
        "daily_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("wake_time", sa.Time(), nullable=True),
        sa.Column("sleep_time", sa.Time(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("work_hours", sa.Integer(), nullable=True),
        sa.Column("no_junk", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("summary_date"),
    )
    op.create_index(op.f("ix_daily_summaries_id"), "daily_summaries", ["id"], unique=False)

    op.create_table(
        "daily_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("habit_id", "log_date", name="uq_habit_log_date"),
    )
    op.create_index(op.f("ix_daily_logs_id"), "daily_logs", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_daily_logs_id"), table_name="daily_logs")
    op.drop_table("daily_logs")

    op.drop_index(op.f("ix_daily_summaries_id"), table_name="daily_summaries")
    op.drop_table("daily_summaries")

    op.drop_index(op.f("ix_journal_entries_id"), table_name="journal_entries")
    op.drop_table("journal_entries")

    op.drop_index(op.f("ix_habits_id"), table_name="habits")
    op.drop_table("habits")

    op.drop_index(op.f("ix_habit_categories_id"), table_name="habit_categories")
    op.drop_table("habit_categories")
