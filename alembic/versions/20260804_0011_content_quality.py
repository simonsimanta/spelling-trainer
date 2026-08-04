"""Track spelling content quality, fallbacks, and manual review."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260804_0011"
down_revision: Union[str, None] = "20260801_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("spelling_word_content", sa.Column("chunked_form", sa.String(length=255), nullable=True))
    op.add_column("spelling_word_content", sa.Column("mnemonic", sa.Text(), nullable=True))
    op.add_column(
        "spelling_word_content",
        sa.Column("generation_source", sa.String(length=30), server_default="ai", nullable=False),
    )
    op.add_column(
        "spelling_word_content",
        sa.Column("quality_warnings", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column("spelling_word_content", sa.Column("review_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("spelling_word_content", "review_notes")
    op.drop_column("spelling_word_content", "quality_warnings")
    op.drop_column("spelling_word_content", "generation_source")
    op.drop_column("spelling_word_content", "mnemonic")
    op.drop_column("spelling_word_content", "chunked_form")
