"""Add spelling attempt mastery state snapshots."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260418_0007"
down_revision: Union[str, None] = "20260417_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("spelling_attempts", sa.Column("mastery_state_before", sa.String(length=40), nullable=True))
    op.add_column("spelling_attempts", sa.Column("mastery_state_after", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("spelling_attempts", "mastery_state_after")
    op.drop_column("spelling_attempts", "mastery_state_before")
