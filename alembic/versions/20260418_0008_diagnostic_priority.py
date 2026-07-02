"""Add diagnostic status and priority score to spelling words."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260418_0008"
down_revision: Union[str, None] = "20260418_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "spelling_words",
        sa.Column("diagnostic_status", sa.String(length=30), nullable=False, server_default="untested"),
    )
    op.add_column(
        "spelling_words",
        sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("spelling_words", "priority_score")
    op.drop_column("spelling_words", "diagnostic_status")
