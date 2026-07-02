import os
import tempfile
from datetime import date, datetime, timedelta

db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.backend import models, repository, schemas
from app.backend.api import app
from app.backend.db import Base, SessionLocal, engine
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

    for path in ["/categories", "/habits", "/logs", "/journal", "/summary", "/metrics"]:
        assert client.get(path).status_code == 404


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


def test_bulk_generation_endpoints_return_result_shapes(monkeypatch) -> None:
    _seed_core_words()
    client = _client()

    content = client.post("/spelling/content/bulk-generate", json={"limit": 2})
    assert content.status_code == 200
    content_payload = content.json()
    assert {"requested_limit", "generated", "cached", "failed", "remaining"}.issubset(content_payload.keys())
    assert content_payload["requested_limit"] == 2

    def fake_audio(_: str, voice: str = "alloy", model: str = "gpt-4o-mini-tts") -> bytes:
        return b"fake-mp3"

    monkeypatch.setattr(audio, "generate_tts_audio", fake_audio)
    audio_result = client.post(
        "/spelling/audio/bulk-generate",
        json={"limit": 2, "voice": "alloy", "model": "gpt-4o-mini-tts"},
    )
    assert audio_result.status_code == 200
    audio_payload = audio_result.json()
    assert {"requested_limit", "generated", "cached", "failed", "remaining"}.issubset(audio_payload.keys())
    assert audio_payload["requested_limit"] == 2


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
    assert wrong_payload["forced_correction_required"] is True
    assert wrong_payload["sentence_diff_json"]["target_correct"] is False

    correction = client.post(
        f"/spelling/attempts/{wrong_payload['attempt_id']}/correct",
        json={"correction_text": item["term"]},
    )
    assert correction.status_code == 200
    assert correction.json()["allow_next"] is True

    target_correct = client.post(
        "/spelling/attempts",
        json={
            "session_id": session["session_id"],
            "session_item_id": item["session_item_id"],
            "word_id": item["word_id"],
            "attempt_text": item["prompt_text"],
            "mode": "dictation",
        },
    )
    assert target_correct.status_code == 200
    assert target_correct.json()["is_correct"] is True
    assert target_correct.json()["sentence_diff_json"]["target_correct"] is True


def test_content_and_audio_bulk_generation(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()

    content = client.post("/spelling/content/bulk-generate", json={"limit": 2})
    assert content.status_code == 200
    assert content.json()["generated"] >= 1
    assert client.get("/spelling/content/bulk-status").json()["generated"] >= 1

    monkeypatch.setattr(audio, "audio_cache_path", lambda text: tmp_path / f"{text}.mp3")
    monkeypatch.setattr(audio, "generate_tts_audio", lambda text, voice="alloy", model="gpt-4o-mini-tts": b"bulk-mp3")
    result = client.post("/spelling/audio/bulk-generate", json={"limit": 2})
    assert result.status_code == 200
    assert result.json()["generated"] >= 1
    assert client.get("/spelling/audio/bulk-status").json()["generated"] >= 1


def test_cached_audio_endpoint(monkeypatch, tmp_path) -> None:
    _seed_core_words()
    client = _client()
    cache_file = tmp_path / "cached.mp3"
    cache_file.write_bytes(b"fake-mp3")
    monkeypatch.setattr(audio, "audio_cache_path", lambda text: cache_file)

    audio_response = client.get("/spelling/audio", params={"text": "definitely"})
    assert audio_response.status_code == 200
    assert audio_response.content == b"fake-mp3"
