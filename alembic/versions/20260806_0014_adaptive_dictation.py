"""Add adaptive multi-target dictation submissions and progression."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0014"
down_revision: Union[str, None] = "20260806_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("spelling_sessions") as batch:
        batch.add_column(sa.Column("dictation_level", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("dictation_target_accuracy", sa.Float(), nullable=True))
        batch.add_column(sa.Column("dictation_word_accuracy", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column("dictation_submission_count", sa.Integer(), server_default="0", nullable=False)
        )

    with op.batch_alter_table("spelling_session_items") as batch:
        batch.add_column(sa.Column("dictation_text_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_spelling_session_items_dictation_text_id",
            "spelling_dictation_texts",
            ["dictation_text_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_spelling_session_items_dictation_text_id", ["dictation_text_id"], unique=False
        )

    op.create_table(
        "spelling_dictation_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("current_level", sa.String(length=20), server_default="sentence", nullable=False),
        sa.Column("previous_level", sa.String(length=20), nullable=True),
        sa.Column("last_evaluated_session_id", sa.Integer(), nullable=True),
        sa.Column("level_started_at", sa.DateTime(), nullable=False),
        sa.Column("level_changed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["last_evaluated_session_id"], ["spelling_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "spelling_dictation_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("session_item_id", sa.Integer(), nullable=False),
        sa.Column("text_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("attempt_text", sa.Text(), nullable=False),
        sa.Column("expected_word_count", sa.Integer(), nullable=False),
        sa.Column("attempt_word_count", sa.Integer(), nullable=False),
        sa.Column("word_error_rate", sa.Float(), nullable=False),
        sa.Column("word_accuracy", sa.Float(), nullable=False),
        sa.Column("target_accuracy", sa.Float(), nullable=False),
        sa.Column("capitalization_accuracy", sa.Float(), nullable=False),
        sa.Column("punctuation_accuracy", sa.Float(), nullable=False),
        sa.Column("omissions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("additions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("substitutions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("replay_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["spelling_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_item_id"], ["spelling_session_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["text_id"], ["spelling_dictation_texts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_item_id", name="uq_spelling_dictation_submission_item"),
    )
    op.create_index(
        "ix_spelling_dictation_submissions_id", "spelling_dictation_submissions", ["id"], unique=False
    )
    op.create_index(
        "ix_spelling_dictation_submissions_session_id",
        "spelling_dictation_submissions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_spelling_dictation_submissions_session_item_id",
        "spelling_dictation_submissions",
        ["session_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_spelling_dictation_submissions_text_id",
        "spelling_dictation_submissions",
        ["text_id"],
        unique=False,
    )

    with op.batch_alter_table("spelling_attempts") as batch:
        batch.add_column(sa.Column("dictation_submission_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_spelling_attempts_dictation_submission_id",
            "spelling_dictation_submissions",
            ["dictation_submission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_spelling_attempts_dictation_submission_id", ["dictation_submission_id"], unique=False
        )

    op.create_table(
        "spelling_dictation_target_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("text_target_id", sa.Integer(), nullable=True),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("attempt_id", sa.Integer(), nullable=True),
        sa.Column("target_term", sa.String(length=120), nullable=False),
        sa.Column("attempt_term", sa.String(length=120), nullable=True),
        sa.Column("is_correct", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_type", sa.String(length=30), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("feeds_practice", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["spelling_attempts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["spelling_dictation_submissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["text_target_id"], ["spelling_dictation_text_targets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "target_term", name="uq_spelling_dictation_result_target"),
    )
    for column in ("id", "submission_id", "text_target_id", "word_id", "attempt_id"):
        op.create_index(
            f"ix_spelling_dictation_target_results_{column}",
            "spelling_dictation_target_results",
            [column],
            unique=False,
        )

    if _is_postgresql():
        for table_name in (
            "spelling_dictation_progress",
            "spelling_dictation_submissions",
            "spelling_dictation_target_results",
        ):
            op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY "deny_browser_data_api" ON public."{table_name}" '
                "AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)"
            )


def downgrade() -> None:
    if _is_postgresql():
        for table_name in (
            "spelling_dictation_target_results",
            "spelling_dictation_submissions",
            "spelling_dictation_progress",
        ):
            op.execute(f'DROP POLICY "deny_browser_data_api" ON public."{table_name}"')
            op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')

    for column in reversed(("id", "submission_id", "text_target_id", "word_id", "attempt_id")):
        op.drop_index(
            f"ix_spelling_dictation_target_results_{column}",
            table_name="spelling_dictation_target_results",
        )
    op.drop_table("spelling_dictation_target_results")

    with op.batch_alter_table("spelling_attempts") as batch:
        batch.drop_index("ix_spelling_attempts_dictation_submission_id")
        batch.drop_constraint("fk_spelling_attempts_dictation_submission_id", type_="foreignkey")
        batch.drop_column("dictation_submission_id")

    op.drop_index("ix_spelling_dictation_submissions_text_id", table_name="spelling_dictation_submissions")
    op.drop_index(
        "ix_spelling_dictation_submissions_session_item_id",
        table_name="spelling_dictation_submissions",
    )
    op.drop_index("ix_spelling_dictation_submissions_session_id", table_name="spelling_dictation_submissions")
    op.drop_index("ix_spelling_dictation_submissions_id", table_name="spelling_dictation_submissions")
    op.drop_table("spelling_dictation_submissions")
    op.drop_table("spelling_dictation_progress")

    with op.batch_alter_table("spelling_session_items") as batch:
        batch.drop_index("ix_spelling_session_items_dictation_text_id")
        batch.drop_constraint("fk_spelling_session_items_dictation_text_id", type_="foreignkey")
        batch.drop_column("dictation_text_id")

    with op.batch_alter_table("spelling_sessions") as batch:
        batch.drop_column("dictation_submission_count")
        batch.drop_column("dictation_word_accuracy")
        batch.drop_column("dictation_target_accuracy")
        batch.drop_column("dictation_level")
