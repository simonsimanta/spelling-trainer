from __future__ import annotations

import json
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models


PROMPT_VERSION = "error-analysis-v1"
PATTERN_LABELS = {
    "letter_omission": "Letter omission",
    "letter_insertion": "Extra letter",
    "letter_substitution": "Letter substitution",
    "adjacent_transposition": "Adjacent letter transposition",
    "double_consonant": "Double consonant",
    "ie_ei_confusion": "Vowel order",
    "silent_letter": "Silent letter",
    "suffix_confusion": "Suffix confusion",
    "homophone_confusion": "Homophone confusion",
}
PATTERN_CODES = list(PATTERN_LABELS)
VOWELS = set("aeiou")
SUFFIXES = ("able", "ible", "ance", "ence", "ary", "ery", "tion", "sion", "cious", "tious", "ly")
HOMOPHONE_GROUPS = [
    {"their", "there", "theyre"},
    {"your", "youre"},
    {"to", "too", "two"},
    {"weather", "whether"},
    {"principal", "principle"},
    {"stationary", "stationery"},
    {"practice", "practise"},
]
SILENT_LETTER_WORDS = {
    "answer",
    "debt",
    "doubt",
    "island",
    "knowledge",
    "knight",
    "lamb",
    "receipt",
    "rhythm",
    "subtle",
    "wednesday",
    "write",
}
CURATED_TRANSFER_WORDS = {
    "double_consonant": ["necessary", "embarrass", "accommodation", "occurrence"],
    "ie_ei_confusion": ["believe", "receive", "piece", "ceiling"],
    "silent_letter": ["knowledge", "island", "debt", "write"],
    "suffix_confusion": ["definitely", "separately", "necessary", "accommodation"],
}


def word_pattern_codes(term: str) -> set[str]:
    """Return spelling patterns a correctly spelled word can exercise."""
    word = normalize_word(term)
    codes: set[str] = set()
    if "ie" in word or "ei" in word:
        codes.add("ie_ei_confusion")
    if any(left == right and left not in VOWELS for left, right in zip(word, word[1:])):
        codes.add("double_consonant")
    if word in SILENT_LETTER_WORDS or any(part in word for part in ("kn", "wr", "mb", "gh")):
        codes.add("silent_letter")
    if any(word.endswith(suffix) for suffix in SUFFIXES):
        codes.add("suffix_confusion")
    if any(word in group for group in HOMOPHONE_GROUPS):
        codes.add("homophone_confusion")
    return codes


def normalize_word(value: str) -> str:
    return "".join(char for char in value.lower().strip() if char.isalpha())


def _adjacent_transposition(correct: str, attempt: str) -> tuple[int, int] | None:
    if len(correct) != len(attempt):
        return None
    mismatches = [index for index, pair in enumerate(zip(correct, attempt)) if pair[0] != pair[1]]
    if len(mismatches) != 2 or mismatches[1] != mismatches[0] + 1:
        return None
    left, right = mismatches
    if correct[left] == attempt[right] and correct[right] == attempt[left]:
        return left, right
    return None


def edit_operations(correct_word: str, attempt_text: str) -> list[dict[str, Any]]:
    correct = normalize_word(correct_word)
    attempt = normalize_word(attempt_text)
    transposition = _adjacent_transposition(correct, attempt)
    if transposition:
        left, right = transposition
        return [
            {
                "type": "transpose",
                "expected": correct[left : right + 1],
                "actual": attempt[left : right + 1],
                "position_correct": left,
                "position_attempt": left,
            }
        ]

    operations: list[dict[str, Any]] = []
    matcher = SequenceMatcher(None, correct, attempt)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        operation_type = {"replace": "substitute", "delete": "omit", "insert": "insert"}[tag]
        operations.append(
            {
                "type": operation_type,
                "expected": correct[i1:i2],
                "actual": attempt[j1:j2],
                "position_correct": i1,
                "position_attempt": j1,
            }
        )
    return operations


def _is_homophone_pair(correct: str, attempt: str) -> bool:
    return any(correct in group and attempt in group for group in HOMOPHONE_GROUPS)


def _double_letter_error(correct: str, attempt: str, operations: list[dict[str, Any]]) -> bool:
    doubled = {index for index in range(1, len(correct)) if correct[index] == correct[index - 1]}
    for operation in operations:
        position = int(operation["position_correct"])
        if operation["type"] == "omit" and any(abs(position - index) <= 1 for index in doubled):
            return True
        if operation["type"] == "insert":
            inserted = str(operation.get("actual") or "")
            neighbours = correct[max(position - 1, 0) : min(position + 1, len(correct))]
            if inserted and any(char in neighbours for char in inserted):
                return True
    return False


def _vowel_order_error(correct: str, attempt: str) -> bool:
    if ("ie" in correct and "ei" in attempt) or ("ei" in correct and "ie" in attempt):
        return True
    transposition = _adjacent_transposition(correct, attempt)
    return bool(transposition and correct[transposition[0]] in VOWELS and correct[transposition[1]] in VOWELS)


def _silent_letter_error(correct: str, operations: list[dict[str, Any]]) -> bool:
    if correct not in SILENT_LETTER_WORDS and not any(part in correct for part in ("kn", "wr", "mb", "gh")):
        return False
    return any(operation["type"] == "omit" for operation in operations)


def _suffix_error(correct: str, operations: list[dict[str, Any]]) -> bool:
    suffix = next((value for value in SUFFIXES if correct.endswith(value)), None)
    if not suffix:
        return False
    suffix_start = len(correct) - len(suffix)
    return any(int(operation["position_correct"]) >= suffix_start for operation in operations)


def deterministic_analysis(correct_word: str, attempt_text: str) -> dict[str, Any]:
    correct = normalize_word(correct_word)
    attempt = normalize_word(attempt_text)
    operations = edit_operations(correct, attempt)
    patterns: list[str] = []

    if _is_homophone_pair(correct, attempt):
        patterns.append("homophone_confusion")
    if _vowel_order_error(correct, attempt):
        patterns.append("ie_ei_confusion")
    if _double_letter_error(correct, attempt, operations):
        patterns.append("double_consonant")
    if _silent_letter_error(correct, operations):
        patterns.append("silent_letter")
    if _suffix_error(correct, operations):
        patterns.append("suffix_confusion")
    if any(operation["type"] == "transpose" for operation in operations):
        patterns.append("adjacent_transposition")
    if any(operation["type"] == "omit" for operation in operations):
        patterns.append("letter_omission")
    if any(operation["type"] == "insert" for operation in operations):
        patterns.append("letter_insertion")
    if any(operation["type"] == "substitute" for operation in operations):
        patterns.append("letter_substitution")

    if not patterns:
        patterns.append("letter_substitution")
    primary = patterns[0]
    return {
        "primary_pattern": primary,
        "pattern_label": PATTERN_LABELS[primary],
        "secondary_patterns": patterns[1:],
        "edit_operations": operations,
        "confidence": 0.96 if primary in {"homophone_confusion", "ie_ei_confusion", "double_consonant", "adjacent_transposition"} else 0.85,
    }


def _memory_strategy(pattern: str, correct_word: str) -> str:
    strategies = {
        "double_consonant": "Mark the doubled letters, then spell the word once from memory.",
        "ie_ei_confusion": "Circle the vowel pair and say the two letters in order before writing.",
        "silent_letter": "Highlight the letter you cannot hear and include it in a visual chunk.",
        "suffix_confusion": "Separate the base word from its ending before spelling the whole word.",
        "homophone_confusion": "Link the spelling to the word's meaning in a short sentence.",
        "adjacent_transposition": "Slow down at the swapped pair and say those letters in order.",
        "letter_omission": "Compare the chunks and mark the letter that disappeared.",
        "letter_insertion": "Cross out the added letter and rebuild the word by chunks.",
        "letter_substitution": "Focus on the changed letter and connect it to a familiar word pattern.",
    }
    return strategies.get(pattern, f"Break {correct_word} into visible chunks and spell each chunk in order.")


def _fallback_analysis(correct_word: str, attempt_text: str, deterministic: dict[str, Any], reason: str) -> dict[str, Any]:
    pattern = deterministic["primary_pattern"]
    expected = correct_word.strip().lower()
    actual = attempt_text.strip().lower()
    suggestions = [
        {"term": term, "reason": f"Practises the {PATTERN_LABELS[pattern].lower()} pattern.", "confidence": 0.8}
        for term in CURATED_TRANSFER_WORDS.get(pattern, [])
        if term != expected
    ]
    return {
        **deterministic,
        "explanation": f"You wrote '{actual}' instead of '{expected}'. This is a {PATTERN_LABELS[pattern].lower()} error.",
        "memory_strategy": _memory_strategy(pattern, expected),
        "transfer_words": suggestions[:5],
        "analysis_source": "fallback",
        "fallback_reason": reason,
    }


def immediate_analysis(correct_word: str, attempt_text: str) -> dict[str, Any]:
    deterministic = deterministic_analysis(correct_word, attempt_text)
    return _fallback_analysis(
        correct_word,
        attempt_text,
        deterministic,
        "Detailed AI analysis is being prepared in the background.",
    )


def structured_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["primary_pattern", "explanation", "memory_strategy", "confidence", "transfer_words"],
        "properties": {
            "primary_pattern": {"type": "string", "enum": PATTERN_CODES},
            "explanation": {"type": "string", "minLength": 1, "maxLength": 320},
            "memory_strategy": {"type": "string", "minLength": 1, "maxLength": 240},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "transfer_words": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["term", "reason", "confidence"],
                    "properties": {
                        "term": {"type": "string", "minLength": 2, "maxLength": 40},
                        "reason": {"type": "string", "minLength": 1, "maxLength": 180},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        },
    }


def analyse_with_ai(
    correct_word: str,
    attempt_text: str,
    deterministic: dict[str, Any],
    *,
    model: str,
    locale: str,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return _fallback_analysis(correct_word, attempt_text, deterministic, "AI analysis is disabled in Settings.")
    import os

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _fallback_analysis(correct_word, attempt_text, deterministic, "The OpenAI API key is not configured.")

    prompt = (
        f"Target {'British' if locale == 'en-GB' else 'American'}-English spelling: {correct_word}\n"
        f"Learner attempt: {attempt_text}\n"
        f"Canonical pattern: {deterministic['primary_pattern']}\n"
        f"Edit operations: {json.dumps(deterministic['edit_operations'])}\n\n"
        "Explain the exact mistake in plain language. Keep the canonical pattern unchanged. "
        "Give one practical memory strategy and up to five British-English transfer words that "
        "genuinely practise the same pattern. Do not repeat the target word."
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "input": [
                    {"role": "system", "content": "You analyse English spelling errors accurately and concisely."},
                    {"role": "user", "content": prompt},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "spelling_error_analysis",
                        "strict": True,
                        "schema": structured_output_schema(),
                    }
                },
            },
            timeout=8,
        )
        if response.status_code >= 400:
            return _fallback_analysis(correct_word, attempt_text, deterministic, f"OpenAI returned HTTP {response.status_code}.")
        texts = [
            content["text"]
            for item in response.json().get("output", [])
            for content in item.get("content", [])
            if content.get("text")
        ]
        if not texts:
            return _fallback_analysis(correct_word, attempt_text, deterministic, "OpenAI returned no analysis.")
        result = json.loads("\n".join(texts))
        result["primary_pattern"] = deterministic["primary_pattern"]
        result["pattern_label"] = deterministic["pattern_label"]
        result["secondary_patterns"] = deterministic["secondary_patterns"]
        result["edit_operations"] = deterministic["edit_operations"]
        result["confidence"] = max(0.0, min(float(result.get("confidence", 0.0)), 1.0))
        result["analysis_source"] = "ai"
        result["fallback_reason"] = None
        return result
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        return _fallback_analysis(correct_word, attempt_text, deterministic, f"AI analysis failed: {type(exc).__name__}.")


def cached_analysis(
    db: Session,
    word: models.SpellingWord,
    attempt_text: str,
    *,
    model: str,
    locale: str,
    enabled: bool,
) -> dict[str, Any]:
    normalized_attempt = normalize_word(attempt_text)
    deterministic = deterministic_analysis(word.term, attempt_text)
    existing = db.scalar(
        select(models.SpellingFeedbackCache).where(
            models.SpellingFeedbackCache.word_id == word.id,
            models.SpellingFeedbackCache.normalized_attempt == normalized_attempt,
            models.SpellingFeedbackCache.error_pattern == deterministic["primary_pattern"],
        )
    )
    if (
        existing
        and existing.analysis_json
        and existing.model == model
        and existing.prompt_version == PROMPT_VERSION
        and existing.locale == locale
    ):
        existing.hit_count += 1
        existing.updated_at = datetime.utcnow()
        return dict(existing.analysis_json)

    result = analyse_with_ai(
        word.term,
        attempt_text,
        deterministic,
        model=model,
        locale=locale,
        enabled=enabled,
    )
    feedback = f"{result['explanation']}\n{result['memory_strategy']}"
    estimated_input = max(1, round((len(word.term) + len(attempt_text) + 120) / 4))
    estimated_output = max(1, round((len(feedback) + sum(len(item["term"]) for item in result["transfer_words"])) / 4))
    if existing:
        existing.feedback_text = feedback
        existing.analysis_json = result
        existing.model = model
        existing.prompt_version = PROMPT_VERSION
        existing.locale = locale
        existing.estimated_input_tokens = estimated_input
        existing.estimated_output_tokens = estimated_output
        existing.updated_at = datetime.utcnow()
    else:
        db.add(
            models.SpellingFeedbackCache(
                word_id=word.id,
                normalized_attempt=normalized_attempt,
                error_pattern=deterministic["primary_pattern"],
                feedback_text=feedback,
                analysis_json=result,
                model=model,
                prompt_version=PROMPT_VERSION,
                locale=locale,
                estimated_input_tokens=estimated_input,
                estimated_output_tokens=estimated_output,
            )
        )
    return result


@lru_cache(maxsize=1)
def oxford_terms() -> frozenset[str]:
    try:
        from app.backend.spelling.oxford import source_terms_by_word

        terms, _ = source_terms_by_word()
        return frozenset(terms)
    except Exception:
        return frozenset()


def _candidate_matches_pattern(term: str, source_term: str, pattern: str) -> bool:
    if pattern == "double_consonant":
        return any(left == right for left, right in zip(term, term[1:]))
    if pattern == "ie_ei_confusion":
        return "ie" in term or "ei" in term
    if pattern == "silent_letter":
        return term in SILENT_LETTER_WORDS or any(part in term for part in ("kn", "wr", "mb", "gh"))
    if pattern == "suffix_confusion":
        return any(term.endswith(suffix) for suffix in SUFFIXES)
    if pattern == "homophone_confusion":
        return _is_homophone_pair(source_term, term)
    return SequenceMatcher(None, source_term, term).ratio() >= 0.3


def validate_transfer_candidates(
    db: Session,
    source_word: models.SpellingWord,
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    source_term = normalize_word(source_word.term)
    pattern = analysis["primary_pattern"]
    candidate_terms = {
        normalize_word(str(candidate.get("term", "")))
        for candidate in analysis.get("transfer_words", [])[:5]
    }
    candidate_terms.discard("")
    existing_terms = set(
        db.scalars(
            select(models.SpellingWord.term).where(
                models.SpellingWord.is_active.is_(True),
                models.SpellingWord.term.in_(candidate_terms),
            )
        ).all()
    )
    missing_terms = candidate_terms - existing_terms
    trusted = existing_terms | (missing_terms & set(oxford_terms()) if missing_terms else set())
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in analysis.get("transfer_words", []):
        term = normalize_word(str(candidate.get("term", "")))
        confidence = max(0.0, min(float(candidate.get("confidence", 0.0)), 1.0))
        if (
            len(term) < 2
            or term == source_term
            or term in seen
            or term not in trusted
            or confidence < 0.6
            or not _candidate_matches_pattern(term, source_term, pattern)
        ):
            continue
        validated.append(
            {
                "term": term,
                "reason": str(candidate.get("reason") or f"Practises {PATTERN_LABELS[pattern].lower()}.")[:180],
                "confidence": confidence,
                "pool_status": "validated",
            }
        )
        seen.add(term)
    return validated[:5]


def persist_analysis(
    db: Session,
    attempt: models.SpellingAttempt,
    source_word: models.SpellingWord,
    analysis: dict[str, Any],
    *,
    model: str,
    locale: str,
) -> dict[str, Any]:
    validated = validate_transfer_candidates(db, source_word, analysis)
    public_analysis = {**analysis, "transfer_words": validated, "prompt_version": PROMPT_VERSION}
    stored_analysis = db.scalar(
        select(models.SpellingErrorAnalysis).where(
            models.SpellingErrorAnalysis.attempt_id == attempt.id
        )
    )
    values = {
        "primary_pattern": analysis["primary_pattern"],
        "secondary_patterns": analysis.get("secondary_patterns", []),
        "edit_operations": analysis.get("edit_operations", []),
        "explanation": analysis["explanation"],
        "memory_strategy": analysis["memory_strategy"],
        "confidence": float(analysis.get("confidence", 0.0)),
        "analysis_source": analysis.get("analysis_source", "fallback"),
        "model": model if analysis.get("analysis_source") == "ai" else "",
        "prompt_version": PROMPT_VERSION,
        "locale": locale,
    }
    if stored_analysis is None:
        stored_analysis = models.SpellingErrorAnalysis(
            attempt_id=attempt.id,
            **values,
        )
        db.add(stored_analysis)
    else:
        for field, value in values.items():
            setattr(stored_analysis, field, value)

    for candidate in validated:
        related_word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == candidate["term"]))
        if not related_word:
            related_word = models.SpellingWord(
                term=candidate["term"],
                level="suggested",
                source="llm_suggestion",
                mastery_state="new",
                diagnostic_status="untested",
            )
            db.add(related_word)
            db.flush()
        suggestion = db.scalar(
            select(models.SpellingSuggestion).where(models.SpellingSuggestion.term == candidate["term"])
        )
        if not suggestion:
            suggestion = models.SpellingSuggestion(
                word_id=related_word.id,
                term=candidate["term"],
                reason=candidate["reason"],
                status="validated",
                pattern_code=analysis["primary_pattern"],
                confidence=candidate["confidence"],
                evidence_count=0,
                validation_status="validated",
            )
            db.add(suggestion)
            db.flush()
        if suggestion.status not in {"rejected", "ignored"}:
            suggestion.status = "validated"
        suggestion.word_id = related_word.id
        suggestion.reason = candidate["reason"]
        suggestion.pattern_code = analysis["primary_pattern"]
        suggestion.confidence = max(suggestion.confidence, candidate["confidence"])
        suggestion.validation_status = "validated"
        suggestion.last_suggested_at = datetime.utcnow()
        evidence = db.scalar(
            select(models.SpellingSuggestionEvidence).where(
                models.SpellingSuggestionEvidence.suggestion_id == suggestion.id,
                models.SpellingSuggestionEvidence.attempt_id == attempt.id,
            )
        )
        if not evidence:
            db.add(
                models.SpellingSuggestionEvidence(
                    suggestion_id=suggestion.id,
                    attempt_id=attempt.id,
                    source_word_id=source_word.id,
                    pattern_code=analysis["primary_pattern"],
                    reason=candidate["reason"],
                    confidence=candidate["confidence"],
                )
            )
            suggestion.evidence_count += 1
    return public_analysis


def enrich_attempt_analysis(db: Session, attempt_id: int) -> bool:
    attempt = db.get(models.SpellingAttempt, attempt_id)
    if attempt is None or attempt.is_correct or attempt.mode == models.SpellingMode.dictation:
        return False
    word = db.get(models.SpellingWord, attempt.word_id)
    settings = db.get(models.AppSettings, 1)
    if word is None or settings is None or not settings.ai_generation_enabled:
        return False
    analysis = cached_analysis(
        db,
        word,
        attempt.attempt_text,
        model=settings.ai_model,
        locale=settings.english_variant,
        enabled=True,
    )
    public_analysis = persist_analysis(
        db,
        attempt,
        word,
        analysis,
        model=settings.ai_model,
        locale=settings.english_variant,
    )
    attempt.error_pattern = public_analysis["primary_pattern"]
    attempt.llm_feedback = feedback_text(public_analysis)
    db.commit()
    return public_analysis.get("analysis_source") == "ai"


def feedback_text(analysis: dict[str, Any]) -> str:
    return f"{analysis['explanation']}\n{analysis['memory_strategy']}"
