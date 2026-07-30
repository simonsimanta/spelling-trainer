"""Add explainable selection scores to spelling session items."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_0009"
down_revision: Union[str, None] = "20260418_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "spelling_session_items",
        sa.Column("selection_score", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "spelling_session_items",
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("spelling_session_items", "score_breakdown")
    op.drop_column("spelling_session_items", "selection_score")
