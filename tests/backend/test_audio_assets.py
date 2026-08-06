from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.backend import models, repository, schemas
from app.backend.api import app
from app.backend.db import Base, SessionLocal, engine
from app.backend.spelling import audio


ROOT = Path(__file__).resolve().parents[2]


def _seed() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        repository.seed_defaults(db)


def _practice_asset(client: TestClient) -> tuple[dict, str]:
    session = client.post(
        "/spelling/sessions",
        json={"session_type": "diagnostic", "target_size": 1, "exercise_type": "mixed"},
    ).json()
    item = session["items"][0]
    return item, item["audio_url"]


class FakeStream:
    status_code = 200

    def __init__(self, chunks: list[bytes], started: threading.Event | None = None, delay: float = 0):
        self.chunks = chunks
        self.started = started
        self.delay = delay
        self.closed = False

    def iter_content(self, chunk_size: int):
        assert chunk_size == audio.STREAM_CHUNK_BYTES
        if self.started:
            self.started.set()
        if self.delay:
            time.sleep(self.delay)
        yield from self.chunks

    def close(self):
        self.closed = True


def test_audio_fingerprint_covers_every_pronunciation_input() -> None:
    base = {
        "asset_kind": "word",
        "mode": "word",
        "voice": "cedar",
        "model": "gpt-4o-mini-tts",
        "audio_format": "mp3",
        "locale": "en-GB",
        "instructions": "Use British English.",
        "pronunciation_version": "en-gb-v2",
    }
    fingerprint = audio.audio_fingerprint("Practice", **base)
    variants = [
        audio.audio_fingerprint("practice", **base),
        audio.audio_fingerprint("Practice", **{**base, "asset_kind": "dictation_complete"}),
        audio.audio_fingerprint("Practice", **{**base, "mode": "dictation"}),
        audio.audio_fingerprint("Practice", **{**base, "voice": "marin"}),
        audio.audio_fingerprint("Practice", **{**base, "model": "tts-1"}),
        audio.audio_fingerprint("Practice", **{**base, "audio_format": "wav"}),
        audio.audio_fingerprint("Practice", **{**base, "locale": "en-US"}),
        audio.audio_fingerprint("Practice", **{**base, "instructions": "Read slowly."}),
        audio.audio_fingerprint("Practice", **{**base, "pronunciation_version": "en-gb-v3"}),
    ]
    assert all(candidate != fingerprint for candidate in variants)
    assert len(set(variants)) == len(variants)


def test_sessions_and_word_resolution_return_only_opaque_asset_urls() -> None:
    _seed()
    client = TestClient(app)
    item, path = _practice_asset(client)

    assert path == f"/spelling/audio/assets/{item['audio_asset_id']}"
    assert "text=" not in path
    resolved = client.post(
        "/spelling/audio/assets/resolve",
        json={"word_id": item["word_id"]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["url"].startswith("/spelling/audio/assets/")
    assert "text" not in resolved.json()

    raw_only = client.post(
        "/spelling/audio/assets/resolve",
        json={"text": "This must not be accepted."},
    )
    assert raw_only.status_code == 400

    with SessionLocal() as db:
        asset = db.get(models.SpellingAudioAsset, item["audio_asset_id"])
        assert asset is not None
        assert asset.text_hash == audio._sha256(item["term"])
        assert not hasattr(asset, "text")
        assert asset.locale == "en-GB"
        assert asset.pronunciation_version == audio.PRONUNCIATION_VERSION


def test_session_audio_metadata_is_loaded_in_one_batch() -> None:
    _seed()
    statements: list[str] = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        if "spelling_audio_assets" in statement and statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        response = TestClient(app).post(
            "/spelling/sessions",
            json={"session_type": "diagnostic", "target_size": 12, "exercise_type": "mixed"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 12
    assert len(statements) == 1


def test_audio_stream_is_atomic_cacheable_and_reused(monkeypatch, tmp_path) -> None:
    _seed()
    client = TestClient(app)
    item, path = _practice_asset(client)
    calls: list[audio.AudioSpec] = []

    def fake_stream(spec: audio.AudioSpec) -> FakeStream:
        calls.append(spec)
        return FakeStream([b"first-", b"second"])

    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(audio, "_open_tts_stream", fake_stream)

    first = client.get(path)
    second = client.get(path)

    assert first.status_code == 200
    assert first.content == b"first-second"
    assert first.headers["x-audio-cache"] == "miss"
    assert first.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert first.headers["accept-ranges"] == "bytes"
    assert first.headers["etag"]
    assert second.content == first.content
    assert second.headers["x-audio-cache"] == "hit"
    assert len(calls) == 1
    assert list(tmp_path.glob("*.mp3"))
    assert not list(tmp_path.glob(".*.tmp"))
    assert not list(tmp_path.glob("*.lock"))

    with SessionLocal() as db:
        asset = db.get(models.SpellingAudioAsset, item["audio_asset_id"])
        assert asset is not None
        assert asset.status == "ready"
        assert asset.byte_size == len(first.content)
        assert asset.access_count == 2


def test_concurrent_requests_share_one_generation(monkeypatch, tmp_path) -> None:
    _seed()
    client = TestClient(app)
    _item, path = _practice_asset(client)
    started = threading.Event()
    call_count = 0
    count_lock = threading.Lock()

    def fake_stream(_spec: audio.AudioSpec) -> FakeStream:
        nonlocal call_count
        with count_lock:
            call_count += 1
        return FakeStream([b"shared-audio"], started=started, delay=0.2)

    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(audio, "_open_tts_stream", fake_stream)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(client.get, path)
        assert started.wait(timeout=2)
        second = executor.submit(client.get, path)
        responses = [first.result(timeout=5), second.result(timeout=5)]

    assert [response.content for response in responses] == [b"shared-audio", b"shared-audio"]
    assert call_count == 1
    assert {response.headers["x-audio-cache"] for response in responses} == {"miss", "shared"}
    assert not list(tmp_path.glob(".*.tmp"))
    assert not list(tmp_path.glob("*.lock"))


def test_active_audio_batch_does_not_scan_the_oxford_list(monkeypatch, tmp_path) -> None:
    _seed()
    client = TestClient(app)
    _practice_asset(client)
    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        audio,
        "generate_tts_audio",
        lambda text, voice, model, instructions="": b"prepared-audio",
    )

    status = client.get("/spelling/audio/bulk-status").json()
    assert status["total_words"] == 1
    assert status["pending"] == 1

    result = client.post("/spelling/audio/bulk-generate", json={"limit": 10})
    assert result.status_code == 200
    assert result.json()["generated"] == 1
    assert result.json()["remaining"] == 0


def test_cleanup_retains_word_audio_and_expires_low_reuse_dictation(monkeypatch, tmp_path) -> None:
    _seed()
    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    now = datetime(2026, 8, 6, 12, 0, 0)
    with SessionLocal() as db:
        word = db.scalar(select(models.SpellingWord).order_by(models.SpellingWord.id))
        assert word is not None
        word_asset = audio.ensure_audio_asset(
            db,
            audio._word_spec(word, voice="cedar", model="gpt-4o-mini-tts"),
        )
        old_asset = audio.ensure_audio_asset(
            db,
            audio._spec(
                "An old passage.",
                asset_kind="dictation_complete",
                mode="dictation",
                voice="cedar",
                model="gpt-4o-mini-tts",
            ),
        )
        low_reuse_asset = audio.ensure_audio_asset(
            db,
            audio._spec(
                "A recent but low reuse passage.",
                asset_kind="dictation_complete",
                mode="dictation",
                voice="cedar",
                model="gpt-4o-mini-tts",
            ),
        )
        for asset, content, last_accessed in (
            (word_asset, b"word", now - timedelta(days=100)),
            (old_asset, b"expired", now - timedelta(days=31)),
            (low_reuse_asset, b"evicted", now - timedelta(days=1)),
        ):
            path = audio._asset_file(asset)
            path.write_bytes(content)
            asset.status = "ready"
            asset.file_path = path.name
            asset.byte_size = len(content)
            asset.generated_at = last_accessed
            asset.last_accessed_at = last_accessed
        db.commit()
        word_id, old_id, low_id = word_asset.id, old_asset.id, low_reuse_asset.id

        result = audio.cleanup_audio_cache(db, now=now, max_passage_bytes=3)
        assert result.expired == 1
        assert result.evicted == 1
        assert result.bytes_removed == len(b"expired") + len(b"evicted")
        assert result.retained_bytes == 0
        assert db.get(models.SpellingAudioAsset, word_id).status == "ready"
        assert db.get(models.SpellingAudioAsset, old_id).status == "expired"
        assert db.get(models.SpellingAudioAsset, low_id).status == "expired"
        assert audio._asset_file(db.get(models.SpellingAudioAsset, word_id)).exists()

    assert audio.PASSAGE_CACHE_MAX_BYTES == 512 * 1024 * 1024


def test_managed_audio_migration_round_trip(tmp_path) -> None:
    database_path = tmp_path / "managed-audio.db"
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
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260806_0015",
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(spelling_audio_assets)").fetchall()
        }
        assert {
            "fingerprint",
            "asset_kind",
            "text_hash",
            "instructions_hash",
            "pronunciation_version",
            "byte_size",
            "last_accessed_at",
        }.issubset(columns)
        settings = {
            row[1]: row[4]
            for row in connection.execute("PRAGMA table_info(app_settings)").fetchall()
        }
        assert settings["tts_voice"] == "'cedar'"

    run_alembic("downgrade", "20260806_0014")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260806_0014",
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "spelling_audio_assets" not in tables
        settings = {
            row[1]: row[4]
            for row in connection.execute("PRAGMA table_info(app_settings)").fetchall()
        }
        assert settings["tts_voice"] == "'alloy'"
