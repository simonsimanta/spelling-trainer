from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from app.backend import models, schemas  # noqa: F401
from app.backend.db import Base, engine
from app.backend.spelling import audio, oxford
from app.shared.config import get_settings


def _check(
    key: str,
    label: str,
    status: str,
    detail: str,
    *,
    required: bool,
    action: str | None = None,
) -> schemas.ReadinessCheck:
    return schemas.ReadinessCheck(
        key=key,
        label=label,
        status=status,
        detail=detail,
        required=required,
        action=action,
    )


def _database_identity(candidate_engine: Engine) -> tuple[str, str]:
    backend = candidate_engine.url.get_backend_name()
    if backend == "sqlite":
        return backend, "Local SQLite"

    host = (candidate_engine.url.host or "").lower()
    if backend == "postgresql" and ("supabase.co" in host or "supabase.com" in host):
        return backend, "Supabase PostgreSQL"
    if backend == "postgresql":
        return backend, "PostgreSQL"
    return backend, backend.title()


def _database_failure(error: Exception, target: str) -> tuple[str, str]:
    message = str(error).lower()
    if "tenant/user" in message or "enotfound" in message:
        detail = f"{target} rejected the configured project reference or pooler user."
        action = "Copy a fresh Session pooler connection string from Supabase Connect into DATABASE_URL, then restart the backend."
    elif "password authentication failed" in message or "authentication failed" in message:
        detail = f"{target} rejected the configured credentials."
        action = "Copy a fresh connection string into DATABASE_URL, then restart the backend."
    elif any(
        marker in message
        for marker in (
            "could not translate host name",
            "name or service not known",
            "nodename nor servname provided",
            "temporary failure in name resolution",
        )
    ):
        detail = f"The {target} host could not be resolved."
        action = "Confirm the database project is active and refresh DATABASE_URL, then restart the backend."
    elif any(marker in message for marker in ("connection refused", "timeout", "timed out", "could not connect")):
        detail = f"{target} could not be reached."
        action = "Confirm the database is running and the DATABASE_URL host, port, and SSL settings are correct."
    elif target == "Local SQLite":
        detail = "The local SQLite database could not be opened."
        action = "Confirm the data directory exists and is writable, then restart the backend."
    else:
        detail = f"{target} connection failed."
        action = "Check DATABASE_URL and database availability, then restart the backend."
    return detail, action


@lru_cache(maxsize=1)
def _expected_migration_head() -> str:
    project_root = Path(__file__).resolve().parents[2]
    config = Config()
    config.set_main_option("script_location", str(project_root / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def _schema_check(connection: Connection) -> schemas.ReadinessCheck:
    tables = set(inspect(connection).get_table_names())
    expected_tables = set(Base.metadata.tables)
    missing_tables = sorted(expected_tables - tables)
    if missing_tables:
        return _check(
            "schema",
            "Database schema",
            "failed",
            f"{len(missing_tables)} required database table(s) are missing.",
            required=True,
            action="Run python -m alembic upgrade head, then refresh this check.",
        )

    if "alembic_version" not in tables:
        return _check(
            "schema",
            "Database schema",
            "warning",
            "Required tables exist, but the migration version is not recorded.",
            required=True,
            action="Verify the database migration history before applying or stamping migrations.",
        )

    current_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    expected_revision = _expected_migration_head()
    if current_revision != expected_revision:
        return _check(
            "schema",
            "Database schema",
            "failed",
            "The database schema is not at the migration version required by this app.",
            required=True,
            action="Run python -m alembic upgrade head, then refresh this check.",
        )

    return _check(
        "schema",
        "Database schema",
        "ready",
        f"Schema and migration {expected_revision} are current.",
        required=True,
    )


def _database_checks(candidate_engine: Engine) -> tuple[schemas.ReadinessCheck, schemas.ReadinessCheck]:
    _, target = _database_identity(candidate_engine)
    try:
        connection = candidate_engine.connect()
    except Exception as error:
        detail, action = _database_failure(error, target)
        return (
            _check("database", "Database connection", "failed", detail, required=True, action=action),
            _check(
                "schema",
                "Database schema",
                "failed",
                "The schema cannot be inspected until the database connection works.",
                required=True,
                action="Restore the database connection first, then refresh this check.",
            ),
        )

    with connection:
        try:
            connection.execute(text("SELECT 1"))
        except Exception as error:
            detail, action = _database_failure(error, target)
            return (
                _check("database", "Database connection", "failed", detail, required=True, action=action),
                _check(
                    "schema",
                    "Database schema",
                    "failed",
                    "The schema cannot be inspected until the database connection works.",
                    required=True,
                    action="Restore the database connection first, then refresh this check.",
                ),
            )

        database_check = _check(
            "database",
            "Database connection",
            "ready",
            f"{target} accepted a test query.",
            required=True,
        )
        try:
            schema_check = _schema_check(connection)
        except Exception:
            schema_check = _check(
                "schema",
                "Database schema",
                "failed",
                "The database responded, but its schema could not be inspected.",
                required=True,
                action="Run python -m alembic upgrade head and check the backend log.",
            )
        return database_check, schema_check


def _openai_check() -> schemas.ReadinessCheck:
    if get_settings().openai_api_key.strip():
        return _check(
            "openai",
            "OpenAI",
            "ready",
            "An OpenAI API key is configured for TTS and generated content.",
            required=False,
        )
    return _check(
        "openai",
        "OpenAI",
        "warning",
        "No OpenAI API key is configured. Cached content remains available, but new TTS and AI content will fail.",
        required=False,
        action="Set OPENAI_API_KEY in .env, then restart the backend.",
    )


def _oxford_check() -> schemas.ReadinessCheck:
    paths = oxford.source_paths()
    available = sum(path.exists() for path in paths.values())
    if oxford.sources_available():
        return _check(
            "oxford",
            "Oxford source PDFs",
            "ready",
            f"All {len(paths)} Oxford source PDFs are available.",
            required=False,
        )
    return _check(
        "oxford",
        "Oxford source PDFs",
        "warning",
        f"{available} of {len(paths)} Oxford source PDFs are available.",
        required=False,
        action="Add The_Oxford_3000.pdf and The_Oxford_5000.pdf to the data directory.",
    )


def _audio_cache_check() -> schemas.ReadinessCheck:
    try:
        cache_dir = audio.audio_cache_dir()
        with NamedTemporaryFile(prefix=".readiness-", dir=cache_dir) as handle:
            handle.write(b"ok")
            handle.flush()
    except OSError:
        return _check(
            "audio_cache",
            "Audio cache",
            "failed",
            "The backend cannot write to the audio cache.",
            required=False,
            action="Make the data/spelling_audio directory writable, then refresh this check.",
        )
    return _check(
        "audio_cache",
        "Audio cache",
        "ready",
        "The audio cache is writable.",
        required=False,
    )


def build_readiness_report(candidate_engine: Engine | None = None) -> schemas.ReadinessReport:
    candidate_engine = candidate_engine or engine
    backend, target = _database_identity(candidate_engine)
    database_check, schema_check = _database_checks(candidate_engine)
    checks = [
        _check("api", "Backend API", "ready", "The API is responding.", required=True),
        database_check,
        schema_check,
        _openai_check(),
        _oxford_check(),
        _audio_cache_check(),
    ]

    required_failure = any(check.required and check.status == "failed" for check in checks)
    has_attention = any(check.status != "ready" for check in checks)
    status = "unavailable" if required_failure else "degraded" if has_attention else "ready"
    return schemas.ReadinessReport(
        status=status,
        database_backend=backend,
        database_target=target,
        checks=checks,
    )
