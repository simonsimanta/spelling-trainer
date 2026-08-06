import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from app.backend import models


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_INDEXES = {
    "ix_spelling_attempts_session_id": (
        models.SpellingAttempt,
        ("session_id",),
    ),
    "ix_spelling_attempts_session_item_id": (
        models.SpellingAttempt,
        ("session_item_id",),
    ),
    "ix_spelling_dictation_progress_last_evaluated_session_id": (
        models.SpellingDictationProgress,
        ("last_evaluated_session_id",),
    ),
    "ix_spelling_session_items_word_id": (
        models.SpellingSessionItem,
        ("word_id",),
    ),
}


def _index_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row[1]
        for row in connection.execute(f"PRAGMA index_list('{table_name}')").fetchall()
    }


def test_models_declare_covering_foreign_key_indexes() -> None:
    for index_name, (model, columns) in EXPECTED_INDEXES.items():
        indexes = {
            index.name: tuple(column.name for column in index.columns)
            for index in model.__table__.indexes
        }
        assert indexes[index_name] == columns


def test_covering_index_migration_repairs_drift_and_round_trips(tmp_path) -> None:
    database_path = tmp_path / "covering-indexes.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"

    def run_alembic(*arguments: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    run_alembic("upgrade", "20260806_0015")
    with sqlite3.connect(database_path) as connection:
        for index_name in (
            "ix_spelling_attempts_session_id",
            "ix_spelling_attempts_session_item_id",
            "ix_spelling_session_items_word_id",
        ):
            connection.execute(f'DROP INDEX "{index_name}"')

    run_alembic("upgrade", "20260806_0016")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260806_0016",
        )
        for index_name, (model, _) in EXPECTED_INDEXES.items():
            assert index_name in _index_names(connection, model.__tablename__)

    run_alembic("downgrade", "20260806_0015")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260806_0015",
        )
        for index_name in (
            "ix_spelling_attempts_session_id",
            "ix_spelling_attempts_session_item_id",
            "ix_spelling_session_items_word_id",
        ):
            table_name = EXPECTED_INDEXES[index_name][0].__tablename__
            assert index_name in _index_names(connection, table_name)
        assert "ix_spelling_dictation_progress_last_evaluated_session_id" not in _index_names(
            connection, "spelling_dictation_progress"
        )

    run_alembic("upgrade", "20260806_0016")
