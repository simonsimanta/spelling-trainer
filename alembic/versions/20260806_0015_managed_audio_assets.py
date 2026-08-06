"""Add managed TTS audio assets and cache lifecycle metadata."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0015"
down_revision: Union[str, None] = "20260806_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("app_settings") as batch:
        batch.alter_column(
            "tts_voice",
            existing_type=sa.String(length=40),
            server_default="cedar",
            existing_nullable=False,
        )

    op.create_table(
        "spelling_audio_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("asset_kind", sa.String(length=40), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("dictation_text_id", sa.Integer(), nullable=True),
        sa.Column("session_item_id", sa.Integer(), nullable=True),
        sa.Column("segment_index", sa.Integer(), nullable=True),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=10), server_default="en-GB", nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("voice", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("audio_format", sa.String(length=20), server_default="mp3", nullable=False),
        sa.Column("instructions", sa.Text(), server_default="", nullable=False),
        sa.Column("instructions_hash", sa.String(length=64), nullable=False),
        sa.Column("pronunciation_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("byte_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("access_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["spelling_words.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["dictation_text_id"], ["spelling_dictation_texts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_item_id"], ["spelling_session_items.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_spelling_audio_asset_fingerprint"),
    )
    for column in (
        "id",
        "fingerprint",
        "asset_kind",
        "word_id",
        "dictation_text_id",
        "session_item_id",
        "status",
        "last_accessed_at",
    ):
        op.create_index(
            f"ix_spelling_audio_assets_{column}",
            "spelling_audio_assets",
            [column],
            unique=False,
        )

    if _is_postgresql():
        op.execute('ALTER TABLE public."spelling_audio_assets" ENABLE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY "deny_browser_data_api" ON public."spelling_audio_assets" '
            "AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)"
        )


def downgrade() -> None:
    if _is_postgresql():
        op.execute('DROP POLICY "deny_browser_data_api" ON public."spelling_audio_assets"')
        op.execute('ALTER TABLE public."spelling_audio_assets" DISABLE ROW LEVEL SECURITY')

    op.drop_table("spelling_audio_assets")
    with op.batch_alter_table("app_settings") as batch:
        batch.alter_column(
            "tts_voice",
            existing_type=sa.String(length=40),
            server_default="alloy",
            existing_nullable=False,
        )
