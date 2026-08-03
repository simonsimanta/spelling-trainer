import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "20260801_0010_supabase_hardening.py"
spec = importlib.util.spec_from_file_location("supabase_hardening_migration", MIGRATION_PATH)
assert spec and spec.loader
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class FakeBind:
    def __init__(self, dialect_name: str):
        self.dialect = SimpleNamespace(name=dialect_name)


def _capture_migration(monkeypatch, dialect_name: str):
    statements: list[str] = []
    created_indexes: list[tuple[str, str, tuple[str, ...]]] = []
    dropped_indexes: list[tuple[str, str]] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: FakeBind(dialect_name))
    monkeypatch.setattr(migration.op, "execute", lambda statement: statements.append(str(statement)))
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, unique=False: created_indexes.append((name, table, tuple(columns))),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda name, table_name=None: dropped_indexes.append((name, table_name)),
    )
    return statements, created_indexes, dropped_indexes


def test_postgres_upgrade_enables_rls_denies_data_api_and_adds_indexes(monkeypatch) -> None:
    statements, created_indexes, _ = _capture_migration(monkeypatch, "postgresql")

    migration.upgrade()

    sql = "\n".join(statements)
    for table_name in migration.PUBLIC_TABLES:
        assert f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'CREATE POLICY "{migration.DENY_POLICY}" ON public."{table_name}"' in sql
    assert "REVOKE ALL PRIVILEGES ON SCHEMA public" in sql
    assert "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public" in sql
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE postgres" in sql
    assert '"anon", "authenticated", "service_role"' in sql
    assert set(created_indexes) == {
        (name, table, tuple(columns))
        for name, table, columns in migration.FOREIGN_KEY_INDEXES
    }


def test_postgres_downgrade_restores_previous_access_and_removes_indexes(monkeypatch) -> None:
    statements, _, dropped_indexes = _capture_migration(monkeypatch, "postgresql")

    migration.downgrade()

    sql = "\n".join(statements)
    for table_name in migration.PUBLIC_TABLES:
        assert f'DROP POLICY "{migration.DENY_POLICY}" ON public."{table_name}"' in sql
        assert f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY' in sql
    assert "GRANT USAGE ON SCHEMA public" in sql
    assert "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public" in sql
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE postgres" in sql
    assert dropped_indexes == [
        (name, table)
        for name, table, _ in reversed(migration.FOREIGN_KEY_INDEXES)
    ]


def test_sqlite_upgrade_and_downgrade_skip_supabase_statements(monkeypatch) -> None:
    statements, created_indexes, dropped_indexes = _capture_migration(monkeypatch, "sqlite")

    migration.upgrade()
    migration.downgrade()

    assert statements == []
    assert len(created_indexes) == len(migration.FOREIGN_KEY_INDEXES)
    assert len(dropped_indexes) == len(migration.FOREIGN_KEY_INDEXES)


def test_alembic_round_trip_on_sqlite(tmp_path) -> None:
    database_path = tmp_path / "migration-round-trip.db"
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

    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version == (migration.revision,)
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list('spelling_attempts')").fetchall()
        }
        assert "ix_spelling_attempts_word_id" in indexes

    run_alembic("downgrade", migration.down_revision)
    with sqlite3.connect(database_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version == (migration.down_revision,)
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list('spelling_attempts')").fetchall()
        }
        assert "ix_spelling_attempts_word_id" not in indexes

    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version == (migration.revision,)
