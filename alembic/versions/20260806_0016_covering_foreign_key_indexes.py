"""Restore covering indexes for spelling workflow foreign keys."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0016"
down_revision: Union[str, None] = "20260806_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESTORED_INDEXES = (
    ("ix_spelling_attempts_session_id", "spelling_attempts", "session_id"),
    (
        "ix_spelling_attempts_session_item_id",
        "spelling_attempts",
        "session_item_id",
    ),
    ("ix_spelling_session_items_word_id", "spelling_session_items", "word_id"),
)
NEW_INDEXES = (
    (
        "ix_spelling_dictation_progress_last_evaluated_session_id",
        "spelling_dictation_progress",
        "last_evaluated_session_id",
    ),
)


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    for index_name, table_name, column_name in RESTORED_INDEXES + NEW_INDEXES:
        if index_name not in _index_names(table_name):
            op.create_index(index_name, table_name, [column_name], unique=False)


def downgrade() -> None:
    # The restored indexes belong to migration 0003 and must survive this downgrade.
    for index_name, table_name, _ in reversed(NEW_INDEXES):
        if index_name in _index_names(table_name):
            op.drop_index(index_name, table_name=table_name)
