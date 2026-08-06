import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.backend import models, repository
from app.backend.api import app
from app.backend.db import Base, SessionLocal, engine
from app.backend.spelling import dictation_grading


ROOT = Path(__file__).resolve().parents[2]


def _seed() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        repository.seed_defaults(db)


def _create_session(client: TestClient, target_size: int = 1) -> dict:
    response = client.post(
        "/spelling/sessions",
        json={"session_type": "dictation", "target_size": target_size},
    )
    assert response.status_code == 200
    return response.json()


def _expected_text(item_id: int) -> tuple[str, list[str]]:
    with SessionLocal() as db:
        item = db.get(models.SpellingSessionItem, item_id)
        assert item is not None and item.dictation_text is not None
        return (
            item.dictation_text.content,
            [target.target_term for target in item.dictation_text.targets],
        )


def _submit(client: TestClient, session: dict, attempt_text: str, replay_count: int = 0):
    item = session["items"][0]
    return client.post(
        "/spelling/dictation/submissions",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "attempt_text": attempt_text,
            "replay_count": replay_count,
        },
    )


def test_layered_grading_separates_spelling_listening_case_and_punctuation() -> None:
    exact_words = dictation_grading.grade_dictation(
        "Careful learners write clearly, every day.",
        "careful learners write clearly every day",
        ["careful", "clearly"],
    )
    assert exact_words.word_accuracy == 1.0
    assert exact_words.target_accuracy == 1.0
    assert exact_words.capitalization_accuracy < 1.0
    assert exact_words.punctuation_accuracy == 0.0

    omission = dictation_grading.grade_dictation(
        "We keep clear notes.",
        "We keep notes.",
        ["clear"],
    )
    assert omission.omissions == 1
    assert omission.targets[0].error_type == "omission"
    assert omission.targets[0].feeds_practice is False

    substitution = dictation_grading.grade_dictation(
        "I will definitely check this.",
        "I will definately check this.",
        ["definitely"],
    )
    assert substitution.substitutions == 1
    assert substitution.targets[0].error_type == "substitution"
    assert substitution.targets[0].confidence >= 0.7
    assert substitution.targets[0].feeds_practice is True
    assert substitution.capitalization_accuracy == 1.0

    repeated_target = dictation_grading.grade_dictation(
        "The instrument was packed beside another instrument.",
        "The instrument was packed beside another instument.",
        ["instrument"],
    )
    assert repeated_target.targets[0].is_correct is False
    assert repeated_target.targets[0].error_type == "substitution"


def test_adaptive_session_hides_expected_text_until_submission() -> None:
    _seed()
    client = TestClient(app)
    session = _create_session(client)
    item = session["items"][0]

    assert session["dictation_level"] == "sentence"
    assert item["word_id"] is None
    assert item["term"] == "Dictation"
    assert item["prompt_text"] == "Listen to the complete text and type what you hear."
    assert item["segment_count"] == 1
    assert item["audio_url"].endswith(f"/{item['session_item_id']}/audio")
    assert "expected_text" not in item
    assert "targets" not in item

    library = client.get(
        "/spelling/dictation/texts",
        params={"source_type": "curated", "level": "sentence"},
    ).json()
    assert library["items"]
    assert all(text["content"] is None and text["targets"] == [] for text in library["items"])

    expected, targets = _expected_text(item["session_item_id"])
    response = _submit(client, session, expected, replay_count=2)
    assert response.status_code == 200
    result = response.json()
    assert result["expected_text"] == expected
    assert result["sentence_segments"] == [expected]
    assert result["replay_count"] == 2
    assert result["word_accuracy"] == 1.0
    assert result["target_accuracy"] == 1.0
    assert [target["target"] for target in result["targets"]] == targets

    duplicate = _submit(client, session, expected)
    assert duplicate.status_code == 409


def test_only_high_confidence_target_substitutions_feed_spelling_practice() -> None:
    _seed()
    with SessionLocal() as db:
        progress = repository._ensure_dictation_progress(db)
        progress.current_level = "paragraph"
        db.commit()

    client = TestClient(app)
    session = _create_session(client)
    item_id = session["items"][0]["session_item_id"]
    expected, targets = _expected_text(item_id)
    assert len(targets) >= 4

    misspelled = targets[0][:-2] + targets[0][-1]
    attempt = re.sub(rf"\b{re.escape(targets[0])}\b", misspelled, expected, count=1)
    attempt = re.sub(rf"\b{re.escape(targets[1])}\b\s*", "", attempt, count=1)
    response = _submit(client, session, attempt)
    assert response.status_code == 200
    result = response.json()
    by_target = {target["target"]: target for target in result["targets"]}
    assert by_target[targets[0]]["error_type"] == "substitution"
    assert by_target[targets[0]]["feeds_practice"] is True
    assert by_target[targets[1]]["error_type"] == "omission"
    assert by_target[targets[1]]["feeds_practice"] is False

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(models.SpellingDictationTargetResult).where(
                    models.SpellingDictationTargetResult.submission_id == result["submission_id"]
                )
            ).all()
        )
        stored = {row.target_term: row for row in rows}
        assert stored[targets[0]].attempt_id is not None
        assert stored[targets[0]].feeds_practice is True
        assert stored[targets[1]].attempt_id is None
        assert stored[targets[1]].feeds_practice is False


def test_progress_promotes_after_three_strong_sessions_and_steps_down_after_two_low_sessions() -> None:
    _seed()
    client = TestClient(app)
    for expected_level in ("sentence", "sentence", "sentence"):
        session = _create_session(client)
        assert session["dictation_level"] == expected_level
        expected, _ = _expected_text(session["items"][0]["session_item_id"])
        response = _submit(client, session, expected)
        assert response.status_code == 200
    assert response.json()["level_changed"] is True
    assert response.json()["current_level"] == "passage"

    for _ in range(2):
        session = _create_session(client)
        assert session["dictation_level"] == "passage"
        response = _submit(client, session, "I could not hear the passage.")
        assert response.status_code == 200
    assert response.json()["level_changed"] is True
    assert response.json()["current_level"] == "sentence"

    session = _create_session(client)
    expected, _ = _expected_text(session["items"][0]["session_item_id"])
    response = _submit(client, session, expected)
    assert response.json()["level_changed"] is False
    assert response.json()["current_level"] == "sentence"


def test_paragraph_audio_supports_complete_text_and_sentence_segments(monkeypatch) -> None:
    _seed()
    with SessionLocal() as db:
        progress = repository._ensure_dictation_progress(db)
        progress.current_level = "paragraph"
        db.commit()
    client = TestClient(app)
    session = _create_session(client)
    item = session["items"][0]
    expected, _ = _expected_text(item["session_item_id"])
    segments = dictation_grading.split_sentence_segments(expected)
    spoken: list[str] = []

    def fake_audio(text: str, **_kwargs) -> Response:
        spoken.append(text)
        return Response(content=b"audio", media_type="audio/mpeg")

    monkeypatch.setattr("app.backend.api.audio.get_audio_response", fake_audio)
    complete = client.get(item["audio_url"])
    first_segment = client.get(item["audio_url"], params={"segment": 0})
    missing_segment = client.get(item["audio_url"], params={"segment": len(segments)})

    assert complete.status_code == 200
    assert first_segment.status_code == 200
    assert missing_segment.status_code == 404
    assert spoken == [expected, segments[0]]
    assert item["segment_count"] == len(segments)


def test_adaptive_dictation_migration_round_trip(tmp_path) -> None:
    database_path = tmp_path / "adaptive-dictation.db"
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

    run_alembic("upgrade", "20260806_0014")
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
        assert {
            "spelling_dictation_progress",
            "spelling_dictation_submissions",
            "spelling_dictation_target_results",
        }.issubset(tables)
        progress_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(spelling_dictation_progress)"
            ).fetchall()
        }
        assert "level_started_at" in progress_columns
        session_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(spelling_sessions)").fetchall()
        }
        assert {"dictation_level", "dictation_target_accuracy", "dictation_word_accuracy"}.issubset(
            session_columns
        )

    run_alembic("downgrade", "20260806_0013")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260806_0013",
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "spelling_dictation_submissions" not in tables
