import os
import tempfile
from datetime import date, datetime, timedelta

db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["OPENAI_API_KEY"] = ""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError

from app.backend import models, readiness, repository, schemas
from app.backend.api import app, startup_seed
from app.backend.db import Base, SessionLocal, engine, get_db
from app.backend.spelling import audio, oxford


def _client() -> TestClient:
    return TestClient(app)


def _seed_core_words() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        repository.seed_defaults(db)
        terms = ["definitely", "magnificent", "accommodation", "knowledge"]
        for rank, term in enumerate(terms, start=1):
            word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == term))
            if word is None:
                word = repository.create_spelling_word(
                db,
                    schemas.SpellingWordCreate(term=term, level="core5k", source="oxford"),
                )
            word.known_skipped = False
            word.mastery_state = "new"
            word.diagnostic_status = "untested"
            word.priority_score = 0.0
            word.introduced_at = None
            repository.upsert_spelling_word_source(db, word.id, "oxford_3000", "core_3000", rank)
            review = db.scalar(select(models.SpellingReview).where(models.SpellingReview.word_id == word.id))
            if review:
                review.due_date = date.today()
                review.incorrect_count = 0
                review.lapse_count = 0
                review.current_stage = models.SpellingStage.learning
        db.commit()
    finally:
        db.close()


def test_spelling_only_public_app_and_dashboard() -> None:
    _seed_core_words()
    client = _client()

    assert client.get("/health").status_code == 200
    assert client.get("/profile").status_code == 200
    assert client.get("/settings").status_code == 200
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["profile"]["name"]
    assert "recent_activity" in dashboard.json()
    stats = dashboard.json()["stats"]
    expected_keys = {
        "oxford_target_words",
        "oxford_loaded_words",
        "oxford_explored_words",
        "practice_distinct_words",
        "dictation_distinct_words",
        "mastered_words",
        "learning_words",
        "trouble_words",
        "due_today_words",
        "forced_correction_words",
        "practice_queue_words",
        "dictation_ready_words",
        "diagnostic_ready_words",
        "diagnostic_tested_words",
        "diagnostic_missed_words",
        "diagnostic_accuracy",
        "first_try_accuracy",
        "exploration_accuracy",
        "practice_accuracy",
        "dictation_accuracy",
        "retention_accuracy_7d",
        "retention_accuracy_14d",
        "retention_accuracy_30d",
        "retention_accuracy_60d",
        "lapse_rate",
        "review_debt_words",
        "known_provisional_words",
        "stable_known_words",
        "due_audit_words",
        "llm_suggested_words",
        "llm_pending_suggestions",
        "content_generated_words",
        "audio_generated_words",
        "pattern_error_rates",
        "recent_mode_accuracy",
        "accuracy_trend",
    }
    assert expected_keys.issubset(stats.keys())
    assert stats["oxford_target_words"] == 5000
    assert stats["oxford_loaded_words"] == 4
    assert stats["practice_queue_words"] == 0
    assert stats["diagnostic_ready_words"] == 19
    assert stats["diagnostic_tested_words"] == 0
    assert stats["diagnostic_missed_words"] == 0
    assert stats["diagnostic_accuracy"] == 0.0
    assert stats["first_try_accuracy"] == 0.0
    assert stats["exploration_accuracy"] == 0.0
    assert stats["retention_accuracy_14d"] == 0.0
    assert stats["lapse_rate"] == 0.0
    assert len(stats["accuracy_trend"]) == 14
    assert all(point["total_attempts"] == 0 for point in stats["accuracy_trend"])
    assert dashboard.json()["daily_plan"]["recommended_mode"] == "diagnostic"
    assert dashboard.json()["daily_plan"]["new_words"] == 19

    for path in ["/categories", "/habits", "/logs", "/journal", "/summary", "/metrics"]:
        assert client.get(path).status_code == 404


def test_dashboard_recent_accuracy_uses_first_try_attempts_from_last_14_days() -> None:
    _seed_core_words()
    db = SessionLocal()
    try:
        word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "accommodation"))
        assert word is not None
        db.add_all(
            [
                models.SpellingAttempt(
                    word_id=word.id,
                    attempt_date=date.today(),
                    attempt_text="accommodation",
                    is_correct=True,
                    mode=models.SpellingMode.practice,
                ),
                models.SpellingAttempt(
                    word_id=word.id,
                    attempt_date=date.today(),
                    attempt_text="acommodation",
                    is_correct=False,
                    mode=models.SpellingMode.practice,
                ),
                models.SpellingAttempt(
                    word_id=word.id,
                    attempt_date=date.today(),
                    attempt_text="accommodation",
                    is_correct=True,
                    mode=models.SpellingMode.dictation,
                ),
                models.SpellingAttempt(
                    word_id=word.id,
                    attempt_date=date.today(),
                    attempt_text="accommodation",
                    is_correct=True,
                    mode=models.SpellingMode.practice,
                    retry_index=1,
                ),
                models.SpellingAttempt(
                    word_id=word.id,
                    attempt_date=date.today() - timedelta(days=14),
                    attempt_text="accommodation",
                    is_correct=True,
                    mode=models.SpellingMode.practice,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    stats = _client().get("/dashboard").json()["stats"]
    modes = {row["mode"]: row for row in stats["recent_mode_accuracy"]}
    assert modes["practice"] == {
        "mode": "practice",
        "total_attempts": 2,
        "correct_attempts": 1,
        "accuracy": 0.5,
    }
    assert modes["dictation"] == {
        "mode": "dictation",
        "total_attempts": 1,
        "correct_attempts": 1,
        "accuracy": 1.0,
    }
    assert stats["accuracy_trend"][-1] == {
        "day": date.today().isoformat(),
        "total_attempts": 3,
        "correct_attempts": 2,
        "accuracy": 0.6667,
    }


def test_word_management_filters_counts_and_attempt_metadata() -> None:
    _seed_core_words()
    db = SessionLocal()
    try:
        personal = repository.create_spelling_word(
            db,
            schemas.SpellingWordCreate(term="meticulous", level="personal", source="manual"),
        )
        personal.short_meaning = "Very careful and precise."
        personal.cefr_level = "C1"
        review = db.scalar(
            select(models.SpellingReview).where(models.SpellingReview.word_id == personal.id)
        )
        assert review is not None
        review.current_stage = models.SpellingStage.trouble
        review.incorrect_count = 2
        personal.mastery_state = "lapse"
        db.add(
            models.SpellingAttempt(
                word_id=personal.id,
                attempt_date=date.today(),
                attempt_text="meticuluous",
                is_correct=False,
                mode=models.SpellingMode.practice,
            )
        )
        db.commit()
    finally:
        db.close()

    client = _client()
    response = client.get(
        "/spelling/word-management",
        params={"category": "trouble", "query": "precise", "sort": "last_attempt", "direction": "desc"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["counts"]["all"] == 20
    assert payload["counts"]["oxford"] == 4
    assert payload["counts"]["personal"] == 1
    assert payload["counts"]["trouble"] == 1
    assert payload["counts"]["seed"] == 15
    row = payload["items"][0]
    assert row["term"] == "meticulous"
    assert row["source_label"] == "Personal"
    assert row["cefr_level"] == "C1"
    assert row["review_stage"] == "trouble"
    assert row["last_attempt_at"]
    assert row["last_attempt_correct"] is False

    filtered = client.get(
        "/spelling/word-management",
        params={"mastery_state": "lapse", "diagnostic_status": "untested"},
    )
    assert filtered.status_code == 200
    assert [item["term"] for item in filtered.json()["items"]] == ["meticulous"]

    ranked_oxford = client.get(
        "/spelling/word-management",
        params={"category": "oxford", "sort": "frequency_rank", "limit": 1},
    )
    assert ranked_oxford.status_code == 200
    assert ranked_oxford.json()["items"][0]["frequency_rank"] == 1


def test_word_management_actions_editing_duplicates_and_targeted_practice() -> None:
    _seed_core_words()
    client = _client()

    created = client.post(
        "/spelling/words",
        json={"term": "perseverance", "level": "personal", "source": "manual"},
    )
    assert created.status_code == 200
    word_id = created.json()["id"]

    duplicate = client.post(
        "/spelling/words",
        json={"term": " Perseverance ", "level": "personal", "source": "manual"},
    )
    assert duplicate.status_code == 409
    assert "already exists in Personal" in duplicate.json()["detail"]

    updated = client.patch(
        f"/spelling/words/{word_id}",
        json={
            "term": "perseverance",
            "short_meaning": "Continuing despite difficulty.",
            "part_of_speech": "noun",
            "cefr_level": "B2",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["short_meaning"] == "Continuing despite difficulty."

    oxford = client.get(
        "/spelling/word-management",
        params={"category": "oxford", "limit": 1},
    ).json()["items"][0]
    forbidden_edit = client.patch(
        f"/spelling/words/{oxford['id']}",
        json={"short_meaning": "Not editable here."},
    )
    assert forbidden_edit.status_code == 403

    queued = client.post(
        f"/spelling/words/{word_id}/actions",
        json={"action": "practice"},
    )
    assert queued.status_code == 200
    session = client.post(
        "/spelling/sessions",
        json={
            "session_type": "practice",
            "target_size": 1,
            "exercise_type": "mixed",
            "word_ids": [word_id],
        },
    )
    assert session.status_code == 200
    assert session.json()["total_items"] == 1
    assert session.json()["items"][0]["word_id"] == word_id
    assert session.json()["items"][0]["source_reason"] == "selected from Word Lists"

    known = client.post(
        f"/spelling/words/{word_id}/actions",
        json={"action": "mark_known"},
    )
    assert known.status_code == 200
    stable_words = client.get(
        "/spelling/word-management",
        params={"category": "stable", "query": "perseverance"},
    ).json()
    assert stable_words["total"] == 1

    reset = client.post(
        f"/spelling/words/{word_id}/actions",
        json={"action": "reset"},
    )
    assert reset.status_code == 200
    reset_word = client.get(
        "/spelling/word-management",
        params={"category": "personal", "query": "perseverance"},
    ).json()["items"][0]
    assert reset_word["mastery_state"] == "new"
    assert reset_word["diagnostic_status"] == "untested"

    archived = client.post(
        f"/spelling/words/{word_id}/actions",
        json={"action": "archive"},
    )
    assert archived.status_code == 200
    archived_words = client.get(
        "/spelling/word-management",
        params={"category": "archived", "query": "perseverance"},
    ).json()
    assert archived_words["total"] == 1

    restored = client.post(
        f"/spelling/words/{word_id}/actions",
        json={"action": "restore"},
    )
    assert restored.status_code == 200
    assert client.get(
        "/spelling/word-management",
        params={"category": "personal", "query": "perseverance"},
    ).json()["total"] == 1


def test_readiness_reports_current_database_schema(tmp_path) -> None:
    ready_engine = create_engine(f"sqlite:///{tmp_path / 'ready.db'}")
    try:
        Base.metadata.create_all(bind=ready_engine)
        with ready_engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": readiness._expected_migration_head()},
            )

        report = readiness.build_readiness_report(ready_engine)
        checks = {check.key: check for check in report.checks}

        assert set(checks) == {"api", "database", "schema", "openai", "oxford", "audio_cache"}
        assert checks["api"].status == "ready"
        assert checks["database"].status == "ready"
        assert checks["schema"].status == "ready"
        assert report.database_backend == "sqlite"
        assert report.database_target == "Local SQLite"
        assert report.status in {"ready", "degraded"}
    finally:
        ready_engine.dispose()


def test_readiness_and_health_when_database_is_unavailable(tmp_path, monkeypatch) -> None:
    broken_engine = create_engine(f"sqlite:///{tmp_path / 'missing' / 'unavailable.db'}")
    monkeypatch.setattr(readiness, "engine", broken_engine)
    try:
        client = _client()
        health = client.get("/health")
        report = client.get("/readiness")

        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert report.status_code == 200
        payload = report.json()
        assert payload["status"] == "unavailable"
        checks = {check["key"]: check for check in payload["checks"]}
        assert checks["api"]["status"] == "ready"
        assert checks["database"]["status"] == "failed"
        assert checks["schema"]["status"] == "failed"
        assert checks["database"]["action"]
        assert str(tmp_path) not in checks["database"]["detail"]
    finally:
        broken_engine.dispose()


def test_startup_seed_defers_database_errors(monkeypatch) -> None:
    def unavailable_seed(_db) -> None:
        raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

    monkeypatch.setattr(repository, "seed_defaults", unavailable_seed)

    startup_seed()

    assert _client().get("/health").json() == {"status": "ok"}


def test_database_route_errors_return_sanitized_service_unavailable() -> None:
    def unavailable_db():
        raise OperationalError("SELECT 1", {}, Exception("password=do-not-expose"))
        yield

    app.dependency_overrides[get_db] = unavailable_db
    try:
        response = _client().get("/settings")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The database is unavailable. Open Settings for readiness details."
    }
    assert "do-not-expose" not in response.text


def test_unattempted_seed_and_due_learning_words_are_not_review_debt() -> None:
    _seed_core_words()
    client = _client()

    db = SessionLocal()
    try:
        word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "definitely"))
        assert word is not None
        review = repository._ensure_spelling_review(db, word)
        review.current_stage = models.SpellingStage.learning
        review.due_date = date.today() - timedelta(days=7)
        db.commit()
    finally:
        db.close()

    dashboard = client.get("/dashboard").json()
    assert dashboard["overview"]["due_today"] == 0
    assert dashboard["core5k"]["due_today_words"] == 0
    assert dashboard["stats"]["due_today_words"] == 0
    assert dashboard["stats"]["review_debt_words"] == 0
    assert dashboard["stats"]["practice_queue_words"] == 0

    practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 10, "exercise_type": "mixed"},
    )
    assert practice.status_code == 200
    assert practice.json()["items"] == []


def test_actionable_review_words_match_due_metrics_and_practice_queue() -> None:
    _seed_core_words()
    client = _client()

    db = SessionLocal()
    try:
        learning_word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "definitely"))
        review_word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "magnificent"))
        mastered_word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "accommodation"))
        future_mistake = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "knowledge"))
        assert learning_word is not None
        assert review_word is not None
        assert mastered_word is not None
        assert future_mistake is not None

        learning_review = repository._ensure_spelling_review(db, learning_word)
        learning_review.current_stage = models.SpellingStage.learning
        learning_review.due_date = date.today() - timedelta(days=7)

        review_word.mastery_state = "review"
        due_review = repository._ensure_spelling_review(db, review_word)
        due_review.current_stage = models.SpellingStage.review
        due_review.due_date = date.today()

        mastered_word.mastery_state = "stable_known"
        due_mastered = repository._ensure_spelling_review(db, mastered_word)
        due_mastered.current_stage = models.SpellingStage.mastered
        due_mastered.due_date = date.today() - timedelta(days=1)

        future_review = repository._ensure_spelling_review(db, future_mistake)
        future_review.current_stage = models.SpellingStage.learning
        future_review.incorrect_count = 1
        future_review.due_date = date.today() + timedelta(days=3)
        db.commit()

        expected_queue_ids = {review_word.id, mastered_word.id, future_mistake.id}
        excluded_learning_id = learning_word.id
    finally:
        db.close()

    dashboard = client.get("/dashboard").json()
    assert dashboard["overview"]["due_today"] == 2
    assert dashboard["core5k"]["due_today_words"] == 2
    assert dashboard["stats"]["due_today_words"] == 2
    assert dashboard["stats"]["review_debt_words"] == 1
    assert dashboard["stats"]["practice_queue_words"] == 3
    assert dashboard["stats"]["dictation_ready_words"] == 3

    practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 10, "exercise_type": "mixed"},
    )
    assert practice.status_code == 200
    practice_ids = {item["word_id"] for item in practice.json()["items"]}
    assert practice_ids == expected_queue_ids
    assert excluded_learning_id not in practice_ids


def test_dashboard_stats_keep_llm_suggestions_separate_from_oxford_coverage() -> None:
    _seed_core_words()
    client = _client()
    db = SessionLocal()
    try:
        suggested = repository.create_spelling_word(
            db,
            schemas.SpellingWordCreate(term="conscientious", level="suggested", source="llm"),
        )
        db.add(models.SpellingSuggestion(word_id=suggested.id, term=suggested.term, reason="Similar difficult word", status="pending"))
        db.add(models.SpellingAudioManifest(word_id=suggested.id, term=suggested.term, status="generated"))
        db.commit()
    finally:
        db.close()

    first = client.get("/spelling/exploration/next").json()
    wrong = client.post(
        "/spelling/attempts",
        json={
            "word_id": first["word"]["id"],
            "attempt_text": "definately",
            "mode": "exploration",
        },
    )
    assert wrong.status_code == 200

    dashboard = client.get("/dashboard").json()
    stats = dashboard["stats"]
    assert stats["oxford_loaded_words"] == 4
    assert stats["oxford_target_words"] == 5000
    assert stats["llm_suggested_words"] >= 1
    assert stats["llm_pending_suggestions"] >= 1
    assert stats["practice_queue_words"] == 1
    assert stats["dictation_ready_words"] == 1
    assert dashboard["core5k"]["total_words"] == 4


def test_oxford_loader_status_and_batch_import(monkeypatch) -> None:
    _seed_core_words()
    client = _client()

    monkeypatch.setattr(
        oxford,
        "source_terms_by_word",
        lambda: (
            ["definitely", "zebrawood", "quizzical"],
            {
                "definitely": [oxford.OxfordSourceTerm("definitely", "oxford_3000", "core_3000", 1)],
                "zebrawood": [oxford.OxfordSourceTerm("zebrawood", "oxford_5000", "core_5000", 2)],
                "quizzical": [oxford.OxfordSourceTerm("quizzical", "oxford_5000", "core_5000", 3)],
            },
        ),
    )
    monkeypatch.setattr(oxford, "sources_available", lambda: True)

    status = client.get("/spelling/oxford/load-status")
    assert status.status_code == 200
    assert status.json()["target_words"] == 5000
    assert status.json()["loaded_words"] == 4
    assert status.json()["source_available"] is True

    loaded = client.post("/spelling/oxford/load-batch", json={"limit": 2})
    assert loaded.status_code == 200
    payload = loaded.json()
    assert payload["requested_limit"] == 2
    assert payload["created"] == 2
    assert payload["loaded_words"] == 6

    db = SessionLocal()
    try:
        assert db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "zebrawood")) is not None
        source_rows = db.scalars(
            select(models.SpellingWordSource).join(models.SpellingWord).where(models.SpellingWord.term == "zebrawood")
        ).all()
        assert {row.source_name for row in source_rows} == {"oxford_5000"}
    finally:
        db.close()

    content_status = client.get("/spelling/content/bulk-status").json()
    audio_status = client.get("/spelling/audio/bulk-status").json()
    assert content_status["total_words"] == 6
    assert audio_status["total_words"] == 6


def test_exploration_returns_oxford_words_in_order_and_respects_known_action() -> None:
    _seed_core_words()
    client = _client()

    first = client.get("/spelling/exploration/next")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["word"]["term"] == "definitely"
    assert first_payload["pool"] == "oxford"
    assert first_payload["content"]["meaning"]
    assert client.get("/dashboard").json()["stats"]["oxford_explored_words"] == 0

    action = client.post(
        "/spelling/exploration/action",
        json={"word_id": first_payload["word"]["id"], "action": "known"},
    )
    assert action.status_code == 200

    next_word = client.get("/spelling/exploration/next")
    assert next_word.status_code == 200
    assert next_word.json()["word"]["term"] == "magnificent"


def test_exploration_can_use_llm_suggested_word_pool() -> None:
    _seed_core_words()
    client = _client()
    db = SessionLocal()
    try:
        suggested = repository.create_spelling_word(
            db,
            schemas.SpellingWordCreate(term="conscientious", level="suggested", source="llm"),
        )
        db.add(models.SpellingSuggestion(word_id=suggested.id, term=suggested.term, reason="Similar difficult word", status="approved"))
        db.commit()
    finally:
        db.close()

    suggested_next = client.get("/spelling/exploration/next", params={"pool": "suggested"})
    assert suggested_next.status_code == 200
    suggested_payload = suggested_next.json()
    assert suggested_payload["pool"] == "suggested"
    assert suggested_payload["word"]["term"] == "conscientious"

    wrong = client.post(
        "/spelling/attempts",
        json={
            "word_id": suggested_payload["word"]["id"],
            "attempt_text": "consientious",
            "mode": "exploration",
        },
    )
    assert wrong.status_code == 200
    assert wrong.json()["forced_correction_required"] is True

    practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 4, "exercise_type": "mixed"},
    )
    assert practice.status_code == 200
    assert "conscientious" in {item["term"] for item in practice.json()["items"]}


def test_bulk_generation_preview_endpoints_return_safe_counts() -> None:
    _seed_core_words()
    client = _client()

    content_preview = client.get("/spelling/content/bulk-preview", params={"limit": 2})
    assert content_preview.status_code == 200
    content_payload = content_preview.json()
    assert content_payload["limit"] == 2
    assert content_payload["total_words"] == 4
    assert content_payload["will_process"] <= 2
    assert content_payload["will_process"] <= content_payload["pending"]
    assert content_payload["estimated_api_calls"] <= content_payload["will_process"]
    assert content_payload["model"]

    audio_preview = client.get(
        "/spelling/audio/bulk-preview",
        params={"limit": 3, "voice": "alloy", "model": "gpt-4o-mini-tts"},
    )
    assert audio_preview.status_code == 200
    audio_payload = audio_preview.json()
    assert audio_payload["limit"] == 3
    assert audio_payload["voice"] == "alloy"
    assert audio_payload["model"] == "gpt-4o-mini-tts"
    assert audio_payload["will_process"] <= 3
    assert audio_payload["will_process"] <= audio_payload["pending"]


def test_word_family_generation_sanitizes_bad_ly_forms() -> None:
    _seed_core_words()
    client = _client()
    db = SessionLocal()
    try:
        word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "necessary"))
        assert word is not None
        content = repository._ensure_word_content(db, word)
        content.word_family = [{"term": "necessary", "label": "base"}, {"term": "necessaryly", "label": "related"}]
        db.commit()
        word_id = word.id
    finally:
        db.close()

    response = client.get(f"/spelling/word-content/{word_id}")
    assert response.status_code == 200
    family_terms = {item["term"] for item in response.json()["word_family"]}
    assert "necessarily" in family_terms
    assert "necessaryly" not in family_terms


def test_bulk_generation_endpoints_return_result_shapes(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()

    content = client.post("/spelling/content/bulk-generate", json={"limit": 2})
    assert content.status_code == 200
    content_payload = content.json()
    assert {"requested_limit", "generated", "cached", "failed", "remaining"}.issubset(content_payload.keys())
    assert content_payload["requested_limit"] == 2

    def fake_audio(
        _: str,
        voice: str = "alloy",
        model: str = "gpt-4o-mini-tts",
        instructions: str = "",
    ) -> bytes:
        return b"fake-mp3"

    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(audio, "generate_tts_audio", fake_audio)
    audio_result = client.post(
        "/spelling/audio/bulk-generate",
        json={"limit": 2, "voice": "alloy", "model": "gpt-4o-mini-tts"},
    )
    assert audio_result.status_code == 200
    audio_payload = audio_result.json()
    assert {"requested_limit", "generated", "cached", "failed", "remaining"}.issubset(audio_payload.keys())
    assert audio_payload["requested_limit"] == 2
    assert audio_payload["voice"] == "alloy"
    assert audio_payload["model"] == "gpt-4o-mini-tts"


def test_practice_and_dictation_sessions_create_expected_items() -> None:
    _seed_core_words()
    client = _client()

    empty_practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 4, "exercise_type": "mixed"},
    )
    assert empty_practice.status_code == 200
    assert empty_practice.json()["items"] == []

    first = client.get("/spelling/exploration/next").json()
    wrong_exploration = client.post(
        "/spelling/attempts",
        json={
            "word_id": first["word"]["id"],
            "attempt_text": "definately",
            "mode": "exploration",
        },
    )
    assert wrong_exploration.status_code == 200
    assert wrong_exploration.json()["forced_correction_required"] is True

    practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 4, "exercise_type": "mixed"},
    )
    assert practice.status_code == 200
    practice_payload = practice.json()
    assert practice_payload["items"]
    assert {item["item_type"] for item in practice_payload["items"]} == {"review_word"}
    assert all(item["choices"] is None for item in practice_payload["items"])
    assert practice_payload["items"][0]["prompt_text"] == "Listen to the word and type its spelling."
    assert practice_payload["items"][0]["queue_reason"] in {"forced correction", "missed spelling"}
    assert practice_payload["items"][0]["short_meaning"]
    assert practice_payload["items"][0]["part_of_speech"]

    dictation = client.post(
        "/spelling/sessions",
        json={"session_type": "dictation", "target_size": 3},
    )
    assert dictation.status_code == 200
    dictation_payload = dictation.json()
    assert dictation_payload["items"][0]["mode"] == "dictation"
    assert dictation_payload["items"][0]["item_type"] == "sentence_dictation"
    assert dictation_payload["items"][0]["prompt_text"]


def test_diagnostic_session_creates_personal_practice_priority() -> None:
    _seed_core_words()
    client = _client()

    diagnostic = client.post(
        "/spelling/sessions",
        json={"session_type": "diagnostic", "target_size": 5, "exercise_type": "mixed"},
    )
    assert diagnostic.status_code == 200
    session = diagnostic.json()
    assert session["items"]
    item = session["items"][0]
    assert item["item_type"] == "review_word"
    assert item["choices"] is None
    assert item["queue_reason"] in {
        "AI suggested diagnostic",
        "Oxford diagnostic",
        "common difficult spelling",
        "diagnostic sample",
        "Oxford B2 diagnostic",
        "Oxford C1 diagnostic",
        "Oxford C2 diagnostic",
    }

    wrong = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": "wrong",
            "mode": "diagnostic",
        },
    )
    assert wrong.status_code == 200
    wrong_payload = wrong.json()
    assert wrong_payload["is_correct"] is False
    assert wrong_payload["allow_next"] is True
    assert wrong_payload["forced_correction_required"] is False

    db = SessionLocal()
    try:
        word = db.get(models.SpellingWord, item["word_id"])
        assert word is not None
        assert word.diagnostic_status == "missed"
        assert word.priority_score >= 1.0
    finally:
        db.close()

    practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 4, "exercise_type": "mixed"},
    )
    assert practice.status_code == 200
    practice_items = practice.json()["items"]
    assert practice_items
    assert practice_items[0]["word_id"] == item["word_id"]
    assert practice_items[0]["queue_reason"] == "diagnostic miss"

    dashboard = client.get("/dashboard").json()["stats"]
    assert dashboard["diagnostic_tested_words"] == 1
    assert dashboard["diagnostic_missed_words"] == 1
    assert dashboard["diagnostic_ready_words"] == 18
    assert dashboard["diagnostic_accuracy"] == 0.0


def test_explainable_priority_score_ranks_high_risk_word() -> None:
    _seed_core_words()
    client = _client()

    db = SessionLocal()
    try:
        high_risk = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "receive"))
        low_risk = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "magnificent"))
        assert high_risk is not None
        assert low_risk is not None

        high_risk.mastery_state = "lapse"
        high_risk.priority_score = 2.0
        high_risk.introduced_at = datetime.utcnow() - timedelta(days=30)
        high_review = repository._ensure_spelling_review(db, high_risk)
        high_review.current_stage = models.SpellingStage.trouble
        high_review.forced_correction_required = True
        high_review.incorrect_count = 3
        high_review.lapse_count = 2
        high_review.due_date = date.today() - timedelta(days=1)
        high_review.average_response_ms = 7000
        high_review.last_attempt_at = datetime.utcnow() - timedelta(days=1)

        low_risk.mastery_state = "learning"
        low_risk.introduced_at = datetime.utcnow()
        low_review = repository._ensure_spelling_review(db, low_risk)
        low_review.current_stage = models.SpellingStage.learning
        low_review.incorrect_count = 1
        low_review.due_date = date.today() + timedelta(days=3)
        low_review.last_attempt_at = datetime.utcnow()

        pattern = db.scalar(
            select(models.SpellingPattern).where(models.SpellingPattern.code == "ie_ei_confusion")
        )
        assert pattern is not None
        pattern_stat = db.scalar(
            select(models.SpellingUserPatternStat).where(
                models.SpellingUserPatternStat.pattern_id == pattern.id
            )
        )
        if pattern_stat is None:
            pattern_stat = models.SpellingUserPatternStat(pattern_id=pattern.id)
            db.add(pattern_stat)
        pattern_stat.total_attempts = 10
        pattern_stat.incorrect_attempts = 8
        pattern_stat.recent_error_rate = 0.8

        for attempt_text in ["recieve", "receve"]:
            db.add(
                models.SpellingAttempt(
                    word_id=high_risk.id,
                    attempt_date=date.today(),
                    attempt_text=attempt_text,
                    is_correct=False,
                    mode=models.SpellingMode.exploration,
                )
            )
        db.commit()
        high_risk_id = high_risk.id
        low_risk_id = low_risk.id
    finally:
        db.close()

    session = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 2, "exercise_type": "mixed"},
    )
    assert session.status_code == 200
    items = session.json()["items"]
    assert [item["word_id"] for item in items] == [high_risk_id, low_risk_id]
    assert items[0]["queue_reason"] == "forced correction"
    assert items[0]["selection_score"] > items[1]["selection_score"]
    assert {
        "forced_correction",
        "diagnostic_miss",
        "due_audit",
        "lapses",
        "recent_misses",
        "pattern_weakness",
        "spacing_delay",
        "usefulness",
        "recency",
    }.issubset(items[0]["score_breakdown"])
    assert items[0]["score_breakdown"]["forced_correction"] == 12.0
    assert items[0]["score_breakdown"]["recent_misses"] > 0
    assert items[0]["score_breakdown"]["pattern_weakness"] > 0
    assert items[0]["score_breakdown"]["response_effort"] > 0

    plan = client.get("/spelling/daily-plan")
    assert plan.status_code == 200
    plan_payload = plan.json()
    assert plan_payload["recommended_mode"] == "practice"
    assert plan_payload["mode_scores"]["practice"] > plan_payload["mode_scores"]["diagnostic"]
    assert plan_payload["recommended_reason"]


def test_stale_due_review_does_not_starve_diagnostic_coverage() -> None:
    _seed_core_words()
    client = _client()

    db = SessionLocal()
    try:
        stale_due = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == "magnificent"))
        assert stale_due is not None
        stale_due.mastery_state = "review"
        stale_due.diagnostic_status = "passed"
        stale_due.introduced_at = datetime.utcnow() - timedelta(days=180)
        stale_review = repository._ensure_spelling_review(db, stale_due)
        stale_review.current_stage = models.SpellingStage.review
        stale_review.due_date = date.today() - timedelta(days=180)
        stale_review.last_attempt_at = datetime.utcnow() - timedelta(days=180)
        db.add(
            models.SpellingAttempt(
                word_id=stale_due.id,
                attempt_date=date.today() - timedelta(days=180),
                attempt_text=stale_due.term,
                is_correct=True,
                mode=models.SpellingMode.diagnostic,
            )
        )
        db.commit()
        stale_due_id = stale_due.id
    finally:
        db.close()

    plan = client.get("/spelling/daily-plan")
    assert plan.status_code == 200
    plan_payload = plan.json()
    assert plan_payload["recommended_mode"] == "diagnostic"
    assert plan_payload["mode_scores"]["diagnostic"] > plan_payload["mode_scores"]["review_due"]

    diagnostic = client.post(
        "/spelling/sessions",
        json={"session_type": "diagnostic", "target_size": 5, "exercise_type": "mixed"},
    )
    assert diagnostic.status_code == 200
    items = diagnostic.json()["items"]
    assert len(items) == 5
    assert stale_due_id not in {item["word_id"] for item in items}
    assert all(item["score_breakdown"]["diagnostic_coverage"] == 4.0 for item in items)
    assert all(item["score_breakdown"]["spacing_delay"] == 0.0 for item in items)
    assert all(item["selection_score"] > 0 for item in items)


def test_correct_diagnostic_attempt_is_provisional_not_practice() -> None:
    _seed_core_words()
    client = _client()

    diagnostic = client.post(
        "/spelling/sessions",
        json={"session_type": "diagnostic", "target_size": 1, "exercise_type": "mixed"},
    ).json()
    item = diagnostic["items"][0]

    correct = client.post(
        "/spelling/attempts",
        json={
            "session_id": diagnostic["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": item["term"],
            "mode": "diagnostic",
        },
    )
    assert correct.status_code == 200
    payload = correct.json()
    assert payload["is_correct"] is True
    assert payload["mastery_state"] == "known_provisional"

    practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 4, "exercise_type": "mixed"},
    )
    assert practice.status_code == 200
    assert all(item["word_id"] != payload["word_id"] for item in practice.json()["items"])


def test_exploration_correct_does_not_add_word_to_practice_queue() -> None:
    _seed_core_words()
    client = _client()
    first = client.get("/spelling/exploration/next").json()

    correct = client.post(
        "/spelling/attempts",
        json={
            "word_id": first["word"]["id"],
            "attempt_text": first["word"]["term"],
            "mode": "exploration",
        },
    )
    assert correct.status_code == 200
    assert correct.json()["is_correct"] is True
    assert correct.json()["mastery_state"] == "known_provisional"

    db = SessionLocal()
    try:
        word = db.get(models.SpellingWord, first["word"]["id"])
        assert word is not None
        review = repository._ensure_spelling_review(db, word)
        assert word.mastery_state == "known_provisional"
        assert review.current_stage == models.SpellingStage.review
        assert review.due_date == date.today() + timedelta(days=14)
    finally:
        db.close()

    practice = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 4, "exercise_type": "mixed"},
    )
    assert practice.status_code == 200
    assert practice.json()["items"] == []

    dashboard = client.get("/dashboard").json()["stats"]
    assert dashboard["known_provisional_words"] == 1
    assert dashboard["stable_known_words"] == 0
    assert dashboard["exploration_accuracy"] == 1.0


def test_due_provisional_word_enters_practice_as_delayed_audit_and_can_stabilize() -> None:
    _seed_core_words()
    client = _client()
    first = client.get("/spelling/exploration/next").json()

    client.post(
        "/spelling/attempts",
        json={
            "word_id": first["word"]["id"],
            "attempt_text": first["word"]["term"],
            "mode": "exploration",
        },
    )

    db = SessionLocal()
    try:
        word = db.get(models.SpellingWord, first["word"]["id"])
        assert word is not None
        word.introduced_at = datetime.utcnow() - timedelta(days=15)
        review = repository._ensure_spelling_review(db, word)
        review.due_date = date.today()
        db.commit()
    finally:
        db.close()

    session_response = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 4, "exercise_type": "mixed"},
    )
    assert session_response.status_code == 200
    session = session_response.json()
    assert session["items"]
    item = session["items"][0]
    assert item["word_id"] == first["word"]["id"]
    assert item["queue_reason"] == "delayed audit"

    audit = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": first["word"]["term"],
            "mode": "practice",
        },
    )
    assert audit.status_code == 200
    assert audit.json()["is_correct"] is True
    assert audit.json()["mastery_state"] == "stable_known"

    dashboard = client.get("/dashboard").json()["stats"]
    assert dashboard["stable_known_words"] == 1
    assert dashboard["mastered_words"] == 1
    assert dashboard["retention_accuracy_14d"] == 1.0


def test_wrong_delayed_audit_or_stable_word_becomes_lapse() -> None:
    _seed_core_words()
    client = _client()
    first = client.get("/spelling/exploration/next").json()

    db = SessionLocal()
    try:
        word = db.get(models.SpellingWord, first["word"]["id"])
        assert word is not None
        word.mastery_state = "stable_known"
        word.introduced_at = datetime.utcnow() - timedelta(days=31)
        review = repository._ensure_spelling_review(db, word)
        review.current_stage = models.SpellingStage.mastered
        review.mastery_score = word.mastery_threshold
        review.due_date = date.today()
        review.interval_days = 30
        db.commit()
    finally:
        db.close()

    missed = client.post(
        "/spelling/attempts",
        json={
            "word_id": first["word"]["id"],
            "attempt_text": "definately",
            "mode": "practice",
        },
    )
    assert missed.status_code == 200
    payload = missed.json()
    assert payload["is_correct"] is False
    assert payload["mastery_state_before"] == "stable_known"
    assert payload["mastery_state_after"] == "lapse"
    assert payload["forced_correction_required"] is True

    dashboard = client.get("/dashboard").json()["stats"]
    assert dashboard["lapse_rate"] == 1.0
    assert dashboard["practice_queue_words"] >= 1


def test_attempts_update_points_feedback_srs_activity_and_correction() -> None:
    _seed_core_words()
    client = _client()
    first = client.get("/spelling/exploration/next").json()
    client.post(
        "/spelling/attempts",
        json={
            "word_id": first["word"]["id"],
            "attempt_text": "definately",
            "mode": "exploration",
        },
    )
    session = client.post(
        "/spelling/sessions",
        json={"session_type": "practice", "target_size": 3, "exercise_type": "mixed"},
    ).json()
    item = session["items"][0]

    wrong = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": "wrong",
            "mode": "practice",
        },
    )
    assert wrong.status_code == 200
    wrong_payload = wrong.json()
    assert wrong_payload["is_correct"] is False
    assert wrong_payload["forced_correction_required"] is True
    assert wrong_payload["diff_json"]["operations"]
    assert wrong_payload["llm_feedback"]

    suggestions = client.get("/spelling/suggestions", params={"status": "auto_added"})
    assert suggestions.status_code == 200
    assert suggestions.json()

    correction = client.post(
        f"/spelling/attempts/{wrong_payload['attempt_id']}/correct",
        json={"correction_text": wrong_payload["term"]},
    )
    assert correction.status_code == 200
    assert correction.json()["allow_next"] is True

    correction_word = wrong_payload["term"]
    correct = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": correction_word,
            "mode": "practice",
        },
    )
    assert correct.status_code == 200
    assert correct.json()["points_awarded"] == 3

    dashboard = client.get("/dashboard").json()
    assert dashboard["profile"]["points"] >= 4
    assert dashboard["recent_activity"]


def test_dictation_grades_target_word_and_returns_sentence_diff() -> None:
    _seed_core_words()
    client = _client()
    first = client.get("/spelling/exploration/next").json()
    client.post(
        "/spelling/attempts",
        json={
            "word_id": first["word"]["id"],
            "attempt_text": "definately",
            "mode": "exploration",
        },
    )
    session = client.post(
        "/spelling/sessions",
        json={"session_type": "dictation", "target_size": 1},
    ).json()
    item = session["items"][0]

    target_wrong = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": item["prompt_text"].replace(item["term"], "definately"),
            "mode": "dictation",
        },
    )
    assert target_wrong.status_code == 200
    wrong_payload = target_wrong.json()
    assert wrong_payload["is_correct"] is False
    assert wrong_payload["target_spelling_correct"] is False
    assert wrong_payload["sentence_complete"] is False
    assert wrong_payload["sentence_similarity"] < 1.0
    assert wrong_payload["forced_correction_required"] is True
    assert wrong_payload["sentence_diff_json"]["target_correct"] is False
    assert wrong_payload["sentence_diff_json"]["target_spelling_correct"] is False

    correction = client.post(
        f"/spelling/attempts/{wrong_payload['attempt_id']}/correct",
        json={"correction_text": item["term"]},
    )
    assert correction.status_code == 200
    assert correction.json()["allow_next"] is True

    partial_sentence = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": item["term"],
            "mode": "dictation",
        },
    )
    assert partial_sentence.status_code == 200
    partial_payload = partial_sentence.json()
    assert partial_payload["is_correct"] is True
    assert partial_payload["target_spelling_correct"] is True
    assert partial_payload["sentence_complete"] is False
    assert partial_payload["sentence_similarity"] < 1.0
    assert partial_payload["allow_next"] is True
    assert partial_payload["forced_correction_required"] is False

    full_sentence = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": item["prompt_text"].upper().rstrip("."),
            "mode": "dictation",
        },
    )
    assert full_sentence.status_code == 200
    full_payload = full_sentence.json()
    assert full_payload["is_correct"] is True
    assert full_payload["target_spelling_correct"] is True
    assert full_payload["sentence_complete"] is True
    assert full_payload["sentence_similarity"] == 1.0
    assert full_payload["sentence_diff_json"]["operations"] == []


def test_dictation_assessment_handles_sentence_and_compound_word_cases() -> None:
    cases = [
        (
            "I definitely finished the task.",
            "I definitely finished the task",
            "definitely",
            True,
            True,
        ),
        (
            "I definitely finished the task.",
            "Definitely finished",
            "definitely",
            True,
            False,
        ),
        (
            "I definitely finished the task.",
            "I definitely finished the task very quickly.",
            "definitely",
            True,
            False,
        ),
        (
            "I definitely finished the task.",
            "This is definitely the wrong sentence.",
            "definitely",
            True,
            False,
        ),
        (
            "I can't attend today.",
            "I can't attend today",
            "can't",
            True,
            True,
        ),
        (
            "I can't attend today.",
            "I cant attend today",
            "can't",
            False,
            False,
        ),
        (
            "It is a well-known fact.",
            "It is a well-known fact",
            "well-known",
            True,
            True,
        ),
        (
            "It is a well-known fact.",
            "It is a well known fact",
            "well-known",
            False,
            False,
        ),
    ]

    for expected, attempt, target, target_correct, sentence_complete in cases:
        result = repository._assess_dictation(expected, attempt, target)
        assert result.target_spelling_correct is target_correct
        assert result.sentence_complete is sentence_complete
        assert 0.0 <= result.sentence_similarity <= 1.0


def test_content_and_audio_bulk_generation(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()

    content = client.post("/spelling/content/bulk-generate", json={"limit": 2})
    assert content.status_code == 200
    assert content.json()["generated"] + content.json()["fallback"] >= 1
    content_status = client.get("/spelling/content/bulk-status").json()
    assert content_status["generated"] + content_status["fallback"] >= 1

    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        audio,
        "generate_tts_audio",
        lambda text, voice="alloy", model="gpt-4o-mini-tts", instructions="": b"bulk-mp3",
    )
    result = client.post("/spelling/audio/bulk-generate", json={"limit": 2})
    assert result.status_code == 200
    assert result.json()["generated"] >= 1


def test_disabled_ai_fallback_and_manual_content_review(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()
    settings = client.patch("/settings", json={"ai_generation_enabled": False})
    assert settings.status_code == 200
    word_id = client.get("/spelling/words").json()[0]["id"]

    content_response = client.get(f"/spelling/word-content/{word_id}")
    assert content_response.status_code == 200
    content = content_response.json()
    assert content["status"] == "fallback"
    assert content["generation_source"] == "fallback"
    assert "disabled" in content["fallback_reason"].lower()

    preview = client.get("/spelling/content/bulk-preview", params={"limit": 10}).json()
    assert preview["estimated_api_calls"] == 0
    assert preview["ai_generation_enabled"] is False
    bulk = client.post("/spelling/content/bulk-generate", json={"limit": 1}).json()
    assert bulk["fallback"] == 1
    assert bulk["generated"] + bulk["fallback"] + bulk["cached"] + bulk["failed"] == 1

    term = content["term"]
    reviewed = client.patch(
        f"/spelling/word-content/{word_id}",
        json={
            "meaning": "A reviewed meaning.",
            "ipa": "/reviewed/ or /alternate/",
            "part_of_speech": "noun",
            "examples": [f"{term.capitalize()} begins this example."],
            "word_family": [{"term": term, "label": "noun"}],
            "chunked_form": "-".join(term),
            "phonetic_hint": "Stress the first syllable",
            "review_notes": "Checked against a learner dictionary.",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"
    assert reviewed.json()["generation_source"] == "manual"

    invalid = client.patch(
        f"/spelling/word-content/{word_id}",
        json={"examples": ["This sentence omits the requested spelling term."]},
    )
    assert invalid.status_code == 400

    generated = []

    def fake_audio(text: str, voice: str, model: str, instructions: str = "") -> bytes:
        generated.append((text, instructions))
        return b"reviewed-audio"

    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(audio, "generate_tts_audio", fake_audio)
    playback = client.get(
        "/spelling/audio",
        params={"text": term, "word_id": word_id, "force": True},
    )
    assert playback.status_code == 200
    assert "Stress the first syllable" in generated[0][1]
    status = client.get("/spelling/audio/bulk-status").json()
    assert status["generated"] >= 1
    assert status["voice"] == "alloy"
    assert status["model"] == "gpt-4o-mini-tts"


def test_cached_audio_endpoint(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()
    cache_file = tmp_path / "cached.mp3"
    cache_file.write_bytes(b"fake-mp3")
    monkeypatch.setattr(
        audio,
        "audio_cache_path",
        lambda text, voice, model, instructions="": cache_file,
    )

    audio_response = client.get("/spelling/audio", params={"text": "definitely"})
    assert audio_response.status_code == 200
    assert audio_response.content == b"fake-mp3"
    assert audio_response.headers["x-audio-cache"] == "hit"


def test_audio_cache_and_on_demand_generation_are_variant_aware(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()
    generated_variants = []

    def fake_audio(text: str, voice: str, model: str, instructions: str = "") -> bytes:
        generated_variants.append((text, voice, model))
        return f"{voice}:{model}".encode()

    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(audio, "generate_tts_audio", fake_audio)
    settings = client.patch(
        "/settings",
        json={"tts_voice": "coral", "tts_model": "gpt-4o-mini-tts"},
    )
    assert settings.status_code == 200

    saved_variant = client.get("/spelling/audio", params={"text": "Definitely"})
    explicit_variant = client.get(
        "/spelling/audio",
        params={"text": "Definitely", "voice": "alloy", "model": "tts-1"},
    )
    saved_variant_again = client.get("/spelling/audio", params={"text": "Definitely"})

    assert saved_variant.content == b"coral:gpt-4o-mini-tts"
    assert explicit_variant.content == b"alloy:tts-1"
    assert saved_variant.headers["x-audio-cache"] == "miss"
    assert explicit_variant.headers["x-audio-cache"] == "miss"
    assert saved_variant_again.headers["x-audio-cache"] == "hit"
    assert generated_variants == [
        ("Definitely", "coral", "gpt-4o-mini-tts"),
        ("Definitely", "alloy", "tts-1"),
    ]
    assert len(list(tmp_path.glob("*.mp3"))) == 2
    assert audio.audio_cache_path("Definitely", "coral", "gpt-4o-mini-tts") != audio.audio_cache_path(
        "Definitely",
        "alloy",
        "tts-1",
    )


def test_bulk_audio_status_and_legacy_manifests_are_variant_specific(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()
    legacy_path = tmp_path / "legacy-text-only.mp3"
    legacy_path.write_bytes(b"stale-voice")

    db = SessionLocal()
    try:
        word = db.scalar(
            select(models.SpellingWord)
            .join(models.SpellingWordSource)
            .where(models.SpellingWordSource.source_name == "oxford_3000")
            .order_by(models.SpellingWordSource.list_rank)
        )
        assert word is not None
        db.add(
            models.SpellingAudioManifest(
                word_id=word.id,
                term=word.term,
                voice="coral",
                model="gpt-4o-mini-tts",
                status="generated",
                file_path=str(legacy_path),
            )
        )
        db.commit()
    finally:
        db.close()

    generated_variants = []

    def fake_audio(text: str, voice: str, model: str, instructions: str = "") -> bytes:
        generated_variants.append((text, voice, model))
        return b"fresh-variant"

    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(audio, "generate_tts_audio", fake_audio)

    coral_result = client.post(
        "/spelling/audio/bulk-generate",
        json={"limit": 1, "voice": "coral", "model": "gpt-4o-mini-tts"},
    )
    assert coral_result.status_code == 200
    assert coral_result.json()["generated"] == 1
    assert generated_variants[0][1:] == ("coral", "gpt-4o-mini-tts")

    coral_status = client.get(
        "/spelling/audio/bulk-status",
        params={"voice": "coral", "model": "gpt-4o-mini-tts"},
    ).json()
    alloy_status = client.get(
        "/spelling/audio/bulk-status",
        params={"voice": "alloy", "model": "gpt-4o-mini-tts"},
    ).json()
    assert coral_status["generated"] == 1
    assert coral_status["voice"] == "coral"
    assert alloy_status["generated"] == 0
    assert alloy_status["pending"] == alloy_status["total_words"]
    assert legacy_path.read_bytes() == b"stale-voice"


def test_audio_generation_errors_are_actionable(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()
    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    missing_key = client.get("/spelling/audio", params={"text": "missing key"})
    assert missing_key.status_code == 503
    assert "not configured" in missing_key.json()["detail"]

    class QuotaResponse:
        status_code = 429
        content = b""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(audio.requests, "post", lambda *args, **kwargs: QuotaResponse())
    quota = client.get("/spelling/audio", params={"text": "quota error"})
    assert quota.status_code == 429
    assert "quota or rate limit" in quota.json()["detail"]

    def network_error(*args, **kwargs):
        raise audio.requests.ConnectionError()

    monkeypatch.setattr(audio.requests, "post", network_error)
    network = client.get("/spelling/audio", params={"text": "network error"})
    assert network.status_code == 502
    assert "could not reach OpenAI" in network.json()["detail"]


def test_tts_request_uses_selected_variant_and_mp3_response_format(monkeypatch) -> None:
    captured = {}

    class SuccessResponse:
        status_code = 200
        content = b"generated-audio"

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SuccessResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(audio.requests, "post", fake_post)

    result = audio.generate_tts_audio(
        "Spell clearly.",
        voice="Coral",
        model="gpt-4o-mini-tts",
        instructions="Read this once at a measured learner pace.",
    )

    assert result == b"generated-audio"
    assert captured["json"]["voice"] == "coral"
    assert captured["json"]["model"] == "gpt-4o-mini-tts"
    assert captured["json"]["response_format"] == "mp3"
    assert captured["json"]["instructions"] == "Read this once at a measured learner pace."
    assert "format" not in captured["json"]
