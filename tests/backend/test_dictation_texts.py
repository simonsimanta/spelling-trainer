import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.backend import models, repository
from app.backend.api import app
from app.backend.db import Base, SessionLocal, engine
from app.backend.spelling import dictation_texts


ROOT = Path(__file__).resolve().parents[2]


def _seed() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        repository.seed_defaults(db)
    finally:
        db.close()


def test_dictation_text_model_declares_selection_index() -> None:
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in models.SpellingDictationText.__table__.indexes
    }

    assert indexes["ix_spelling_dictation_texts_level_status_last_used"] == (
        "level",
        "status",
        "last_used_at",
    )


def test_curated_library_seeds_five_reviewed_texts_per_level() -> None:
    _seed()
    db = SessionLocal()
    try:
        texts = list(db.scalars(select(models.SpellingDictationText)).unique().all())
        assert len(texts) == 15
        for level, rules in dictation_texts.LEVEL_RULES.items():
            rows = [text for text in texts if text.level == level]
            assert len(rows) == 5
            for text in rows:
                assert text.source_type == "curated"
                assert text.status == "reviewed"
                assert text.locale == "en-GB"
                assert text.quality_warnings == []
                assert rules["words"][0] <= text.word_count <= rules["words"][1]
                assert rules["sentences"][0] <= text.sentence_count <= rules["sentences"][1]
                assert rules["targets"][0] <= len(text.targets) <= rules["targets"][1]
                assert all(target.word_id is not None for target in text.targets)
    finally:
        db.close()


def test_personal_text_can_be_listed_archived_restored_and_deleted() -> None:
    _seed()
    client = TestClient(app)
    created = client.post(
        "/spelling/dictation/texts",
        json={
            "title": "Concert preparation",
            "content": "The careful musician checked every instrument before tonight's important concert.",
            "level": "sentence",
            "target_terms": ["instrument"],
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["source_type"] == "personal"
    assert payload["status"] == "reviewed"
    assert payload["targets"] == [{"word_id": None, "term": "instrument", "order_index": 0}]

    listed = client.get(
        "/spelling/dictation/texts",
        params={"source_type": "personal", "status": "all"},
    ).json()
    assert listed["total"] == 1
    assert listed["counts"]["personal"] == 1

    archived = client.patch(
        f"/spelling/dictation/texts/{payload['id']}",
        json={"action": "archive"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    restored = client.patch(
        f"/spelling/dictation/texts/{payload['id']}",
        json={"action": "restore"},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "reviewed"

    deleted = client.delete(f"/spelling/dictation/texts/{payload['id']}")
    assert deleted.status_code == 204
    assert client.get(
        "/spelling/dictation/texts",
        params={"source_type": "personal", "status": "all"},
    ).json()["total"] == 0


def test_personal_text_needing_british_or_length_adaptation_is_retained() -> None:
    _seed()
    response = TestClient(app).post(
        "/spelling/dictation/texts",
        json={
            "title": "Poster note",
            "content": "My favorite color appears in the center of this poster.",
            "level": "sentence",
            "target_terms": ["favorite"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_adaptation"
    assert any("British spellings" in warning for warning in payload["quality_warnings"])


def test_curated_and_used_personal_texts_cannot_be_deleted() -> None:
    _seed()
    client = TestClient(app)
    curated = client.get(
        "/spelling/dictation/texts",
        params={"source_type": "curated", "level": "sentence"},
    ).json()["items"][0]
    assert client.delete(f"/spelling/dictation/texts/{curated['id']}").status_code == 409

    personal = client.post(
        "/spelling/dictation/texts",
        json={
            "title": "Concert preparation",
            "content": "The careful musician checked every instrument before tonight's important concert.",
            "level": "sentence",
            "target_terms": ["instrument"],
        },
    ).json()
    db = SessionLocal()
    try:
        stored = db.get(models.SpellingDictationText, personal["id"])
        assert stored is not None
        dictation_texts.mark_used(db, stored)
        db.commit()
    finally:
        db.close()
    blocked = client.delete(f"/spelling/dictation/texts/{personal['id']}")
    assert blocked.status_code == 409
    assert "unused personal texts" in blocked.json()["detail"]


def test_ai_adaptation_is_validated_and_cached(monkeypatch) -> None:
    _seed()
    client = TestClient(app)
    source = client.post(
        "/spelling/dictation/texts",
        json={
            "title": "Concert preparation",
            "content": "The careful musician checked every instrument before tonight's important concert.",
            "level": "sentence",
            "target_terms": ["instrument"],
        },
    ).json()
    calls = 0

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict:
            content = {
                "title": "Orchestra rehearsal",
                "content": "The musician checked every instrument before the concert began. After a brief rehearsal, the musician adjusted the instrument carefully and joined the orchestra on stage.",
                "target_terms": ["instrument", "musician"],
            }
            return {"output": [{"content": [{"text": json.dumps(content)}]}]}

    def fake_post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(dictation_texts.requests, "post", fake_post)
    request = {"level": "passage", "target_terms": ["instrument", "musician"]}

    first = client.post(f"/spelling/dictation/texts/{source['id']}/adapt", json=request)
    second = client.post(f"/spelling/dictation/texts/{source['id']}/adapt", json=request)

    assert first.status_code == 200
    assert first.json()["text"]["source_type"] == "ai_adapted"
    assert first.json()["text"]["status"] == "reviewed"
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["text"]["id"] == first.json()["text"]["id"]
    assert calls == 1


def test_ai_failure_returns_a_reviewed_curated_fallback(monkeypatch) -> None:
    _seed()
    client = TestClient(app)
    source = client.post(
        "/spelling/dictation/texts",
        json={
            "title": "Concert preparation",
            "content": "The careful musician checked every instrument before tonight's important concert.",
            "level": "sentence",
            "target_terms": ["instrument"],
        },
    ).json()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(
        f"/spelling/dictation/texts/{source['id']}/adapt",
        json={"level": "passage", "target_terms": ["instrument", "musician"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_fallback"] is True
    assert payload["fallback_reason"]
    assert payload["text"]["source_type"] == "curated"
    assert payload["text"]["level"] == "passage"
    assert payload["text"]["status"] == "reviewed"


def test_dictation_library_migration_round_trip(tmp_path) -> None:
    database_path = tmp_path / "dictation-library.db"
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

    run_alembic("upgrade", "20260806_0013")
    with sqlite3.connect(database_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version == ("20260806_0013",)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"spelling_dictation_texts", "spelling_dictation_text_targets"}.issubset(tables)

    run_alembic("downgrade", "20260806_0012")
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "spelling_dictation_texts" not in tables
        assert "spelling_dictation_text_targets" not in tables
