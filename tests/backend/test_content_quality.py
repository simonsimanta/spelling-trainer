import pytest

from app.backend import models, repository
from app.backend.spelling import audio
from app.backend.spelling.content_quality import (
    contains_target,
    validate_generated_content,
)


def _valid_payload(target: str) -> dict:
    return {
        "meaning": "A clear learner-friendly meaning.",
        "ipa": "/test/ or /tɛst/",
        "part_of_speech": "adj",
        "examples": [
            f"{target.capitalize()} appears at the start.",
            f"We practiced {target} today.",
        ],
        "word_family": [{"term": target, "label": "adjective"}],
        "chunked_form": target.replace("-", "--"),
        "mnemonic": "Use the chunks to remember every letter.",
    }


def test_quality_validation_accepts_capitalization_hyphens_and_multiple_pronunciations() -> None:
    result = validate_generated_content("well-being", _valid_payload("well-being"))

    assert result["part_of_speech"] == "adjective"
    assert result["ipa"] == "/test/ or /tɛst/"
    assert result["chunked_form"] == "well--being"


def test_quality_validation_rejects_homophone_in_place_of_target() -> None:
    payload = _valid_payload("there")
    payload["examples"][1] = "Their books are on the desk."

    with pytest.raises(ValueError, match="target word"):
        validate_generated_content("there", payload)

    assert contains_target("There is enough time.", "there")
    assert not contains_target("Their answer was correct.", "there")


def test_quality_validation_removes_unrelated_word_family_entries() -> None:
    payload = _valid_payload("definitely")
    payload["word_family"] = [
        {"term": "banana", "label": "noun"},
        {"term": "definite", "label": "adjective"},
    ]

    result = validate_generated_content("definitely", payload)

    assert {item["term"] for item in result["word_family"]} == {"definitely", "definite"}


def test_malformed_ai_response_uses_visible_fallback(monkeypatch) -> None:
    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"output": [{"content": [{"text": "not-json"}]}]}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(repository.requests, "post", lambda *args, **kwargs: Response())
    word = models.SpellingWord(term="careful", level="personal", source="manual")

    result = repository._generate_content_with_ai(word)

    assert result.source == "fallback"
    assert result.fallback_reason
    assert all(contains_target(example, "careful") for example in result.data["examples"])


def test_tts_instructions_and_cache_include_pronunciation_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audio, "audio_cache_dir", lambda: tmp_path)
    word = models.SpellingWord(
        term="read",
        level="personal",
        source="manual",
        ipa="/riːd/ or /rɛd/",
        phonetic_hint="Use the present-tense pronunciation",
    )
    instructions = audio.pronunciation_instructions("read", word)
    dictation = audio.pronunciation_instructions("I read every day.", word, "dictation")

    assert "present-tense" in instructions
    assert "/riːd/ or /rɛd/" in instructions
    assert "measured learner pace" in dictation
    assert audio.audio_cache_path("read", instructions=instructions) != audio.audio_cache_path(
        "read",
        instructions=audio.pronunciation_instructions("read"),
    )
