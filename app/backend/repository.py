from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from sqlalchemy import Integer, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.backend import models, schemas


DEFAULT_SPELLING_WORDS = [
    ("definitely", "confusion"),
    ("separate", "confusion"),
    ("receive", "confusion"),
    ("necessary", "confusion"),
    ("embarrass", "confusion"),
    ("environment", "confusion"),
    ("schedule", "daily"),
    ("language", "daily"),
    ("journal", "daily"),
    ("discipline", "daily"),
    ("progress", "daily"),
    ("focused", "daily"),
    ("consistency", "daily"),
    ("practice", "daily"),
    ("habit", "daily"),
    ("magnificent", "daily"),
    ("accommodation", "daily"),
    ("knowledge", "daily"),
    ("beautiful", "daily"),
]

OXFORD_SOURCE_NAMES = {"oxford_3000", "oxford_5000"}
SRS_STEPS_HARD = [0, 1, 2, 4, 7, 14, 30]
SRS_STEPS_NORMAL = [0, 1, 3, 7, 14, 30, 60]
FORCED_CORRECTION_SKIP_AFTER = 2
PROVISIONAL_AUDIT_DAYS = 14
STABLE_AUDIT_DAYS = 30
STABLE_MASTERY_STATES = {"stable_known", "mastered"}
DIAGNOSTIC_PRIORITY_BOOST = 1.0
RECENT_MISS_WINDOW_DAYS = 14

COMMON_CONFUSION_WORDS = [
    "definitely",
    "separate",
    "receive",
    "necessary",
    "embarrass",
    "environment",
    "accommodate",
    "occasionally",
    "recommend",
    "independent",
    "beautiful",
    "knowledge",
    "accommodation",
    "magnificent",
]


@dataclass(frozen=True)
class SelectionScore:
    total: float
    reason: str
    breakdown: Dict[str, float]


@dataclass(frozen=True)
class RankedWord:
    word: models.SpellingWord
    score: SelectionScore


@dataclass(frozen=True)
class DictationAssessment:
    target_spelling_correct: bool
    sentence_complete: bool
    sentence_similarity: float


CONFUSION_GROUPS = [
    ["definitely", "separate", "necessary", "embarrass", "accommodate", "occasionally"],
    ["receive", "believe", "piece", "friend"],
    ["environment", "independent", "recommend"],
    ["beautiful", "knowledge", "accommodation", "magnificent"],
]

DEFAULT_PATTERNS = [
    {
        "code": "double_consonant",
        "label": "Double consonants",
        "description": "Confusion with repeated consonants such as ss, rr, mm.",
        "examples": ["necessary", "embarrass", "accommodate"],
    },
    {
        "code": "ie_ei_confusion",
        "label": "ie/ei confusion",
        "description": "Vowel-order confusion in words like receive, believe, piece.",
        "examples": ["receive", "believe", "piece"],
    },
    {
        "code": "silent_letter",
        "label": "Silent letters",
        "description": "Letters that are present in spelling but often omitted in recall.",
        "examples": ["environment", "debt", "island"],
    },
    {
        "code": "homophone_confusion",
        "label": "Homophone confusion",
        "description": "Words that sound alike but differ in spelling and meaning.",
        "examples": ["their", "there", "they're"],
    },
]

DEFAULT_ACHIEVEMENTS = [
    ("explorer_10", "Word Explorer", "Explore 10 words.", "exploration", 10),
    ("practice_25", "Practice Builder", "Complete 25 practice attempts.", "practice", 25),
    ("dictation_10", "Sharp Listener", "Complete 10 dictation attempts.", "dictation", 10),
    ("accuracy_90", "Careful Speller", "Reach 90% first-try accuracy.", "accuracy", 90),
    ("streak_7", "Seven Day Streak", "Practice for 7 days in a row.", "streak", 7),
]


def seed_defaults(db: Session) -> None:
    ensure_app_defaults(db)
    seed_spelling_defaults(db)


def ensure_app_defaults(db: Session) -> None:
    if not db.get(models.LearnerProfile, 1):
        db.add(models.LearnerProfile(id=1))
    if not db.get(models.AppSettings, 1):
        db.add(models.AppSettings(id=1))

    existing_codes = set(db.scalars(select(models.Achievement.code)).all())
    for code, title, description, category, target in DEFAULT_ACHIEVEMENTS:
        if code in existing_codes:
            continue
        db.add(
            models.Achievement(
                code=code,
                title=title,
                description=description,
                category=category,
                target=target,
            )
        )
    db.commit()


def seed_spelling_defaults(db: Session) -> None:
    existing_count = db.scalar(select(func.count(models.SpellingWord.id))) or 0
    if existing_count == 0:
        for rank, (term, level) in enumerate(DEFAULT_SPELLING_WORDS, start=1):
            word = models.SpellingWord(
                term=term,
                level=level,
                source="seed",
                chunked_form=_chunk_hint(term),
                example_sentence=_example_sentence(term),
                frequency_rank=rank,
            )
            db.add(word)
            db.flush()
            db.add(
                models.SpellingReview(
                    word_id=word.id,
                    due_date=date.today(),
                    interval_days=0,
                    consecutive_correct=0,
                    incorrect_count=0,
                )
            )
    seed_spelling_taxonomy(db)
    db.commit()


def seed_spelling_taxonomy(db: Session) -> None:
    existing_patterns = set(db.scalars(select(models.SpellingPattern.code)).all())
    for pattern in DEFAULT_PATTERNS:
        if pattern["code"] in existing_patterns:
            continue
        db.add(
            models.SpellingPattern(
                code=pattern["code"],
                label=pattern["label"],
                description=pattern["description"],
                examples=pattern["examples"],
            )
        )
    db.flush()

    existing_groups = set(db.scalars(select(models.SpellingConfusionGroup.name)).all())
    for idx, words in enumerate(CONFUSION_GROUPS):
        name = f"group_{idx + 1}"
        if name in existing_groups:
            continue
        group = models.SpellingConfusionGroup(
            name=name,
            description=", ".join(words),
            difficulty_score=0.7,
        )
        db.add(group)
        db.flush()
        for position, term in enumerate(words):
            word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == term))
            if word:
                word.is_confusable = True
                db.add(models.SpellingConfusionGroupWord(group_id=group.id, word_id=word.id, position=position))


def get_profile(db: Session) -> models.LearnerProfile:
    ensure_app_defaults(db)
    profile = db.get(models.LearnerProfile, 1)
    assert profile is not None
    return profile


def update_profile(db: Session, payload: schemas.ProfileUpdate) -> models.LearnerProfile:
    profile = get_profile(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    profile.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return profile


def get_settings(db: Session) -> models.AppSettings:
    ensure_app_defaults(db)
    settings = db.get(models.AppSettings, 1)
    assert settings is not None
    return settings


def update_settings(db: Session, payload: schemas.SettingsUpdate) -> models.AppSettings:
    settings = get_settings(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)
    return settings


def _normalize_text(value: str) -> str:
    return "".join(ch for ch in value.lower().strip() if ch.isalpha())


def _chunk_hint(word: str) -> str:
    if len(word) <= 4:
        return word
    pieces: List[str] = []
    idx = 0
    while idx < len(word):
        step = 2 if idx == 0 else 3
        pieces.append(word[idx : idx + step])
        idx += step
    return "-".join(pieces)


def _example_sentence(word: str) -> str:
    templates = {
        "definitely": "I will definitely finish my practice today.",
        "separate": "Keep this page separate from your notes.",
        "receive": "I receive feedback after every attempt.",
        "necessary": "Daily review is necessary for long-term memory.",
        "embarrass": "Small mistakes help you improve.",
        "magnificent": "The view from the mountain top was magnificent.",
        "accommodation": "The hotel arranged accommodation for the visitors.",
        "knowledge": "Reading builds knowledge over time.",
        "beautiful": "The garden looked beautiful after the rain.",
    }
    return templates.get(word, f"I practiced the word '{word}' in my spelling session.")


def _meaning_for_word(word: str) -> str:
    meanings = {
        "definitely": "Without doubt; clearly and certainly.",
        "separate": "To keep apart, divide, or treat as different.",
        "receive": "To get, accept, or be given something.",
        "necessary": "Needed for a purpose or situation.",
        "embarrass": "To make someone feel awkward or self-conscious.",
        "environment": "The surroundings or conditions where something lives or happens.",
        "magnificent": "Extremely beautiful, impressive, or grand.",
        "accommodation": "A place to stay or an arrangement that helps someone.",
        "knowledge": "Facts, information, and understanding gained through learning.",
        "beautiful": "Pleasing to look at, hear, or experience.",
    }
    return meanings.get(word, f"A useful English word to understand, pronounce, and spell accurately.")


def _word_family_for(word: str) -> List[Dict[str, str]]:
    families = {
        "necessary": [
            {"term": "necessary", "label": "adjective"},
            {"term": "necessarily", "label": "adverb"},
            {"term": "necessity", "label": "noun"},
        ],
        "magnificent": [
            {"term": "magnify", "label": "verb"},
            {"term": "magnification", "label": "noun"},
            {"term": "magnificently", "label": "adverb"},
        ],
        "beautiful": [
            {"term": "beauty", "label": "noun"},
            {"term": "beautifully", "label": "adverb"},
            {"term": "beautify", "label": "verb"},
        ],
        "knowledge": [
            {"term": "know", "label": "verb"},
            {"term": "known", "label": "adjective"},
            {"term": "knowledgeable", "label": "adjective"},
        ],
    }
    return _sanitize_word_family(
        word,
        families.get(word)
        or [
            {"term": word, "label": "base"},
            *_derived_family_terms(word),
        ],
    )


def _derived_family_terms(word: str) -> List[Dict[str, str]]:
    derived: List[Dict[str, str]] = []
    adverb = _safe_adverb_form(word)
    if adverb and adverb != word:
        derived.append({"term": adverb, "label": "adverb"})
    return derived


def _safe_adverb_form(word: str) -> Optional[str]:
    if len(word) > 2 and word.endswith("y") and word[-2].lower() not in {"a", "e", "i", "o", "u"}:
        return f"{word[:-1]}ily"
    if word.endswith("al"):
        return f"{word}ly"
    return None


def _normalize_family_term(base_word: str, term: str) -> str:
    normalized = term.strip().lower()
    if base_word.endswith("y") and normalized == f"{base_word}ly":
        return _safe_adverb_form(base_word) or normalized
    return normalized


def _sanitize_word_family(base_word: str, family: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    base = base_word.strip().lower()
    cleaned: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in family or []:
        raw_term = str(item.get("term") or "").strip()
        if not raw_term:
            continue
        term = _normalize_family_term(base, raw_term)
        if not term.replace("-", "").isalpha() or term in seen:
            continue
        label = str(item.get("label") or "related").strip().lower()
        cleaned.append({"term": term, "label": label})
        seen.add(term)
    if base not in seen:
        cleaned.insert(0, {"term": base, "label": "base"})
        seen.add(base)
    if len(cleaned) == 1:
        for item in _derived_family_terms(base):
            if item["term"] not in seen:
                cleaned.append(item)
                seen.add(item["term"])
    return cleaned[:6]


def _phonetic_feedback(word: models.SpellingWord) -> Optional[Dict[str, Any]]:
    if not word.ipa and not word.phonetic_hint:
        return None
    return {
        "ipa": word.ipa,
        "chunked": word.chunked_form,
        "sound_hint": word.phonetic_hint,
    }


def _mnemonic_for_word(word: str) -> str:
    hints = {
        "definitely": "Think: de-fi-nite-ly.",
        "separate": "Remember: there is 'a rat' in sep-a-rat-e.",
        "necessary": "One collar, two sleeves: neCeSSary.",
        "receive": "i before e, except after c.",
        "embarrass": "Two r and two s: emba-rra-ss.",
        "accommodation": "Two c and two m: a-ccommo-dation.",
    }
    return hints.get(word, f"Say it in chunks: {_chunk_hint(word)}")


def _error_pattern(correct_word: str, attempt_text: str) -> str:
    correct = _normalize_text(correct_word)
    attempt = _normalize_text(attempt_text)
    if attempt == correct:
        return "none"
    if len(attempt) < len(correct):
        return "missing_letter"
    if len(attempt) > len(correct):
        return "extra_letter"
    ratio = SequenceMatcher(None, correct, attempt).ratio()
    if ratio > 0.75:
        return "close_spelling"
    return "pattern_confusion"


def _build_diff_json(correct_word: str, attempt_text: str) -> Dict[str, Any]:
    correct = _normalize_text(correct_word)
    attempt = _normalize_text(attempt_text)
    matcher = SequenceMatcher(None, correct, attempt)
    operations: List[Dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            operations.append(
                {
                    "type": "replace",
                    "expected": correct[i1:i2],
                    "actual": attempt[j1:j2],
                    "position_correct": i1,
                    "position_attempt": j1,
                }
            )
        elif tag == "delete":
            operations.append({"type": "missing", "expected": correct[i1:i2], "position_correct": i1})
        elif tag == "insert":
            operations.append({"type": "extra", "actual": attempt[j1:j2], "position_attempt": j1})
    return {
        "correct": correct_word,
        "attempt": attempt_text,
        "operations": operations,
        "summary": "none" if not operations else _error_pattern(correct_word, attempt_text),
    }


def _word_tokens(value: str) -> List[str]:
    tokens: List[str] = []
    current: List[str] = []
    normalized = value.lower().replace("\u2019", "'").replace("\u2010", "-").replace("\u2011", "-")
    for index, char in enumerate(normalized):
        if char.isalpha():
            current.append(char)
        elif (
            char in {"'", "-"}
            and current
            and index + 1 < len(normalized)
            and normalized[index + 1].isalpha()
        ):
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _dictation_target_correct(target_word: str, attempt_text: str) -> bool:
    target_tokens = _word_tokens(target_word)
    attempt_tokens = _word_tokens(attempt_text)
    if not target_tokens:
        return False
    width = len(target_tokens)
    return any(
        attempt_tokens[index : index + width] == target_tokens
        for index in range(len(attempt_tokens) - width + 1)
    )


def _assess_dictation(expected_text: str, attempt_text: str, target_word: str) -> DictationAssessment:
    expected_tokens = _word_tokens(expected_text)
    attempt_tokens = _word_tokens(attempt_text)
    similarity = SequenceMatcher(None, expected_tokens, attempt_tokens).ratio() if expected_tokens else 0.0
    return DictationAssessment(
        target_spelling_correct=_dictation_target_correct(target_word, attempt_text),
        sentence_complete=bool(expected_tokens) and expected_tokens == attempt_tokens,
        sentence_similarity=round(similarity, 4),
    )


def _closest_target_attempt(target_word: str, attempt_text: str) -> str:
    tokens = _word_tokens(attempt_text)
    if not tokens:
        return attempt_text
    target = _normalize_text(target_word)
    return max(tokens, key=lambda token: SequenceMatcher(None, target, token).ratio())


def _build_sentence_diff_json(
    expected_text: str,
    attempt_text: str,
    target_word: str,
    assessment: Optional[DictationAssessment] = None,
) -> Dict[str, Any]:
    expected = _word_tokens(expected_text)
    attempt = _word_tokens(attempt_text)
    result = assessment or _assess_dictation(expected_text, attempt_text, target_word)
    matcher = SequenceMatcher(None, expected, attempt)
    operations: List[Dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        operations.append(
            {
                "type": tag,
                "expected": " ".join(expected[i1:i2]),
                "actual": " ".join(attempt[j1:j2]),
                "position_expected": i1,
                "position_attempt": j1,
            }
        )
    return {
        "expected": expected_text,
        "attempt": attempt_text,
        "target_word": target_word,
        "target_correct": result.target_spelling_correct,
        "target_spelling_correct": result.target_spelling_correct,
        "sentence_complete": result.sentence_complete,
        "sentence_similarity": result.sentence_similarity,
        "operations": operations,
    }


def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def _llm_feedback(correct_word: str, attempt_text: str, error_pattern: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        if error_pattern == "none":
            return "Correct. Say the word once and spell it again later from memory."
        if error_pattern == "missing_letter":
            return "Almost there. You missed one or more letters."
        if error_pattern == "extra_letter":
            return "You added an extra letter. Type slowly and check each chunk."
        if error_pattern == "close_spelling":
            return "Very close. Check the middle letters and common confusion pattern."
        return "Break the word into chunks, then type it once more from memory."

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt = (
        "Return 3 short spelling feedback lines: what happened, a chunk hint, and a mnemonic. "
        f"Correct word: {correct_word}. Attempt: {attempt_text}. Error type: {error_pattern}."
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": prompt},
            timeout=15,
        )
        if response.status_code >= 400:
            return "AI feedback is unavailable right now. Use chunking and try once more."
        data = response.json()
        texts: List[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    texts.append(text)
        return "\n".join(texts).strip()[:500] or "Try again with chunking and repetition."
    except Exception:
        return "Try chunking the word and type it once more."


def _cached_llm_feedback(
    db: Session,
    word: models.SpellingWord,
    attempt_text: str,
    error_pattern: str,
) -> str:
    normalized_attempt = _normalize_text(attempt_text)
    existing = db.scalar(
        select(models.SpellingFeedbackCache).where(
            models.SpellingFeedbackCache.word_id == word.id,
            models.SpellingFeedbackCache.normalized_attempt == normalized_attempt,
            models.SpellingFeedbackCache.error_pattern == error_pattern,
        )
    )
    if existing:
        existing.hit_count += 1
        existing.updated_at = datetime.utcnow()
        return existing.feedback_text

    feedback = _llm_feedback(word.term, attempt_text, error_pattern)
    db.add(
        models.SpellingFeedbackCache(
            word_id=word.id,
            normalized_attempt=normalized_attempt,
            error_pattern=error_pattern,
            feedback_text=feedback,
            hit_count=0,
            estimated_input_tokens=_estimate_tokens(f"{word.term} {attempt_text} {error_pattern}"),
            estimated_output_tokens=_estimate_tokens(feedback),
        )
    )
    return feedback


def _ensure_spelling_review(db: Session, word: models.SpellingWord) -> models.SpellingReview:
    review = db.scalar(select(models.SpellingReview).where(models.SpellingReview.word_id == word.id))
    if review:
        return review
    review = models.SpellingReview(
        word_id=word.id,
        due_date=date.today(),
        interval_days=0,
        consecutive_correct=0,
        incorrect_count=0,
    )
    db.add(review)
    db.flush()
    return review


def _active_learning_word_filter() -> Tuple[Any, Any]:
    return (
        models.SpellingWord.is_active.is_(True),
        models.SpellingWord.known_skipped.is_(False),
    )


def _actionable_review_filter(as_of: date) -> Any:
    return or_(
        models.SpellingReview.forced_correction_required.is_(True),
        models.SpellingWord.diagnostic_status == "missed",
        models.SpellingReview.incorrect_count > 0,
        models.SpellingReview.lapse_count > 0,
        models.SpellingReview.current_stage == models.SpellingStage.trouble,
        (
            (models.SpellingWord.mastery_state == "known_provisional")
            & (models.SpellingReview.due_date <= as_of)
        ),
        (
            models.SpellingReview.current_stage.in_(
                [models.SpellingStage.review, models.SpellingStage.mastered]
            )
            & (models.SpellingReview.due_date <= as_of)
        ),
    )


def _is_actionable_review(
    word: models.SpellingWord,
    review: models.SpellingReview,
    as_of: date,
) -> bool:
    return bool(
        review.forced_correction_required
        or word.diagnostic_status == "missed"
        or review.incorrect_count > 0
        or review.lapse_count > 0
        or review.current_stage == models.SpellingStage.trouble
        or (
            word.mastery_state == "known_provisional"
            and review.due_date <= as_of
        )
        or (
            review.current_stage in {
                models.SpellingStage.review,
                models.SpellingStage.mastered,
            }
            and review.due_date <= as_of
        )
    )


def _state_for_word(word: models.SpellingWord, review: Optional[models.SpellingReview] = None) -> str:
    if word.mastery_state:
        return word.mastery_state
    if review:
        return review.current_stage.value
    return "new"


def _is_stable_state(state: Optional[str]) -> bool:
    return bool(state in STABLE_MASTERY_STATES)


def _is_due_provisional_audit(word: models.SpellingWord, review: models.SpellingReview) -> bool:
    return word.mastery_state == "known_provisional" and review.due_date <= date.today()


def _word_usefulness_score(word: models.SpellingWord) -> float:
    score = float(word.difficulty_score or 0.0)
    cefr = (word.cefr_level or "").upper()
    if cefr in {"B2", "C1", "C2"}:
        score += 0.35
    elif cefr in {"B1"}:
        score += 0.15
    if word.term in COMMON_CONFUSION_WORDS:
        score += 0.3
    if word.source in {"llm", "llm_suggestion"} or word.level == "suggested":
        score += 0.25
    if word.frequency_rank:
        score += max(0.0, 0.2 - min(word.frequency_rank, 5000) / 25000)
    return round(score, 4)


def _inferred_pattern_codes(word: models.SpellingWord) -> set[str]:
    codes: set[str] = set()
    term = word.term.lower()
    if "ie" in term or "ei" in term:
        codes.add("ie_ei_confusion")
    if any(left == right for left, right in zip(term, term[1:])):
        codes.add("double_consonant")
    return codes


def _selection_signal_maps(
    db: Session,
    words: List[models.SpellingWord],
    as_of: date,
) -> Tuple[Dict[int, models.SpellingReview], Dict[int, int], Dict[int, float]]:
    word_ids = [word.id for word in words]
    if not word_ids:
        return {}, {}, {}

    reviews = {
        review.word_id: review
        for review in db.scalars(
            select(models.SpellingReview).where(models.SpellingReview.word_id.in_(word_ids))
        ).all()
    }
    recent_miss_rows = db.execute(
        select(models.SpellingAttempt.word_id, func.count(models.SpellingAttempt.id))
        .where(
            models.SpellingAttempt.word_id.in_(word_ids),
            models.SpellingAttempt.attempt_date >= as_of - timedelta(days=RECENT_MISS_WINDOW_DAYS),
            models.SpellingAttempt.is_correct.is_(False),
            models.SpellingAttempt.retry_index == 0,
        )
        .group_by(models.SpellingAttempt.word_id)
    ).all()
    recent_misses = {word_id: int(count or 0) for word_id, count in recent_miss_rows}

    pattern_rates = {
        code: float(error_rate or 0.0)
        for code, error_rate in db.execute(
            select(models.SpellingPattern.code, models.SpellingUserPatternStat.recent_error_rate)
            .join(
                models.SpellingUserPatternStat,
                models.SpellingUserPatternStat.pattern_id == models.SpellingPattern.id,
            )
        ).all()
    }
    linked_patterns: Dict[int, List[Tuple[str, float]]] = {}
    for word_id, code, strength in db.execute(
        select(
            models.SpellingWordPattern.word_id,
            models.SpellingPattern.code,
            models.SpellingWordPattern.strength,
        )
        .join(
            models.SpellingPattern,
            models.SpellingPattern.id == models.SpellingWordPattern.pattern_id,
        )
        .where(models.SpellingWordPattern.word_id.in_(word_ids))
    ).all():
        linked_patterns.setdefault(word_id, []).append((code, float(strength or 1.0)))

    pattern_weakness: Dict[int, float] = {}
    for word in words:
        candidates = [
            pattern_rates.get(code, 0.0)
            for code in _inferred_pattern_codes(word)
        ]
        candidates.extend(
            pattern_rates.get(code, 0.0) * strength
            for code, strength in linked_patterns.get(word.id, [])
        )
        pattern_weakness[word.id] = round(max(candidates, default=0.0), 4)
    return reviews, recent_misses, pattern_weakness


def _selection_recency_score(
    word: models.SpellingWord,
    review: Optional[models.SpellingReview],
    now: datetime,
) -> float:
    last_seen = review.last_attempt_at if review and review.last_attempt_at else word.last_seen_at
    if last_seen is None:
        return 1.5
    days_since = max((now - last_seen).days, 0)
    if days_since <= 1:
        return -0.75
    if days_since <= 3:
        return -0.25
    if days_since >= 30:
        return 1.25
    if days_since >= 14:
        return 0.8
    if days_since >= 7:
        return 0.4
    return 0.0


def _selection_reason(
    word: models.SpellingWord,
    review: Optional[models.SpellingReview],
    mode: models.SpellingSessionType,
    breakdown: Dict[str, float],
    as_of: date,
) -> str:
    if mode == models.SpellingSessionType.diagnostic:
        return _diagnostic_reason(word)
    if review and review.forced_correction_required:
        return "forced correction"
    if word.diagnostic_status == "missed":
        return "diagnostic miss"
    if word.mastery_state == "lapse" or (review and review.lapse_count > 0):
        return "lapse repair"
    if (
        review
        and word.mastery_state == "known_provisional"
        and review.due_date <= as_of
    ):
        return "delayed audit"
    if breakdown["recent_misses"] > 0 or (review and review.incorrect_count > 0):
        return "missed spelling"
    if breakdown["pattern_weakness"] >= 1.0:
        return "weak spelling pattern"
    if review and review.due_date <= as_of:
        return "due review"
    return "review"


def _selection_score(
    word: models.SpellingWord,
    review: Optional[models.SpellingReview],
    mode: models.SpellingSessionType,
    recent_misses: int,
    pattern_weakness: float,
    as_of: date,
    now: datetime,
) -> SelectionScore:
    breakdown = {
        "forced_correction": 12.0 if review and review.forced_correction_required else 0.0,
        "diagnostic_miss": 6.0 if word.diagnostic_status == "missed" else 0.0,
        "due_audit": 0.0,
        "lapses": 0.0,
        "miss_history": min(float(review.incorrect_count) * 0.75, 3.0) if review else 0.0,
        "recent_misses": min(float(recent_misses) * 1.5, 4.5),
        "pattern_weakness": round(pattern_weakness * 3.0, 4),
        "spacing_delay": 0.0,
        "usefulness": _word_usefulness_score(word),
        "stored_priority": min(max(float(word.priority_score or 0.0), 0.0), 3.0),
        "response_effort": 0.0,
        "recency": _selection_recency_score(word, review, now),
        "diagnostic_coverage": (
            4.0
            if mode == models.SpellingSessionType.diagnostic and word.diagnostic_status == "untested"
            else 0.0
        ),
    }
    if review:
        lapse_count = max(review.lapse_count, 1 if word.mastery_state == "lapse" else 0)
        breakdown["lapses"] = min(float(lapse_count) * 2.0, 6.0)
        if review.due_date <= as_of and _is_actionable_review(word, review, as_of):
            overdue_days = max((as_of - review.due_date).days, 0)
            breakdown["spacing_delay"] = round(min(3.0, 0.75 + (overdue_days / 14)), 4)
            if word.mastery_state == "known_provisional":
                breakdown["due_audit"] = 4.0
            elif review.current_stage == models.SpellingStage.mastered:
                breakdown["due_audit"] = 2.5
            elif review.current_stage == models.SpellingStage.review:
                breakdown["due_audit"] = 1.5
        if review.average_response_ms and review.average_response_ms > 3000:
            breakdown["response_effort"] = round(
                min((review.average_response_ms - 3000) / 4000, 1.5),
                4,
            )
    breakdown = {key: round(value, 4) for key, value in breakdown.items()}
    reason = _selection_reason(word, review, mode, breakdown, as_of)
    return SelectionScore(
        total=round(sum(breakdown.values()), 4),
        reason=reason,
        breakdown=breakdown,
    )


def _rank_words(
    db: Session,
    words: List[models.SpellingWord],
    mode: models.SpellingSessionType,
    as_of: Optional[date] = None,
) -> List[RankedWord]:
    scoring_date = as_of or date.today()
    now = datetime.utcnow()
    reviews, recent_misses, pattern_weakness = _selection_signal_maps(
        db,
        words,
        scoring_date,
    )
    ranked = [
        RankedWord(
            word=word,
            score=_selection_score(
                word,
                reviews.get(word.id),
                mode,
                recent_misses.get(word.id, 0),
                pattern_weakness.get(word.id, 0.0),
                scoring_date,
                now,
            ),
        )
        for word in words
    ]
    return sorted(
        ranked,
        key=lambda item: (
            -item.score.total,
            item.word.frequency_rank or 999999,
            item.word.term,
        ),
    )


def _diagnostic_reason(word: models.SpellingWord) -> str:
    cefr = (word.cefr_level or "").upper()
    if word.source in {"llm", "llm_suggestion"} or word.level == "suggested":
        return "AI suggested diagnostic"
    if cefr in {"B2", "C1", "C2"}:
        return f"Oxford {cefr} diagnostic"
    if word.term in COMMON_CONFUSION_WORDS or word.level == "confusion":
        return "common difficult spelling"
    if word.source == "oxford" or word.level == "core5k" or any(
        source.source_name in OXFORD_SOURCE_NAMES for source in word.sources
    ):
        return "Oxford diagnostic"
    return "diagnostic sample"


def _diagnostic_candidate_words(db: Session, target_size: int, level: str = "all") -> List[RankedWord]:
    seed_spelling_defaults(db)
    today = date.today()
    attempted_ids = set(
        db.scalars(
            select(models.SpellingAttempt.word_id)
            .where(models.SpellingAttempt.mode == models.SpellingMode.diagnostic)
            .distinct()
        ).all()
    )
    actionable_review_ids = set(
        db.scalars(
            select(models.SpellingReview.word_id)
            .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
            .where(*_active_learning_word_filter())
            .where(_actionable_review_filter(today))
        ).all()
    )
    stmt = (
        select(models.SpellingWord)
        .where(models.SpellingWord.is_active.is_(True))
        .where(models.SpellingWord.known_skipped.is_(False))
    )
    if level != "all":
        normalized_level = level.upper()
        if normalized_level in {"A1", "A2", "B1", "B2", "C1", "C2"}:
            stmt = stmt.where(models.SpellingWord.cefr_level == normalized_level)
        else:
            stmt = stmt.where(models.SpellingWord.level == level)
    words = [
        word
        for word in db.scalars(stmt).all()
        if word.id not in attempted_ids and word.id not in actionable_review_ids
    ]
    return _rank_words(db, words, models.SpellingSessionType.diagnostic, today)[:target_size]


def _word_has_oxford_source() -> Any:
    return (
        select(models.SpellingWordSource.id)
        .where(
            models.SpellingWordSource.word_id == models.SpellingWord.id,
            models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)),
        )
        .exists()
    )


def list_spelling_words(db: Session, level: Optional[str] = None) -> List[models.SpellingWord]:
    stmt = select(models.SpellingWord).where(models.SpellingWord.is_active.is_(True)).order_by(models.SpellingWord.term)
    if level:
        if level == "trouble":
            stmt = (
                stmt.join(models.SpellingReview, models.SpellingReview.word_id == models.SpellingWord.id)
                .where(models.SpellingReview.current_stage == models.SpellingStage.trouble)
            )
        elif level == "mastered":
            stmt = (
                stmt.join(models.SpellingReview, models.SpellingReview.word_id == models.SpellingWord.id)
                .where(models.SpellingReview.current_stage == models.SpellingStage.mastered)
            )
        elif level == "core5k":
            stmt = stmt.where(_word_has_oxford_source())
        else:
            stmt = stmt.where(models.SpellingWord.level == level)
    return list(db.scalars(stmt.limit(500)).all())


def create_spelling_word(db: Session, payload: schemas.SpellingWordCreate) -> models.SpellingWord:
    normalized = payload.term.strip().lower()
    existing = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == normalized))
    if existing:
        return existing
    word = models.SpellingWord(
        term=normalized,
        level=payload.level,
        source=payload.source,
        chunked_form=_chunk_hint(normalized),
        example_sentence=_example_sentence(normalized),
        mastery_state="learning" if payload.source == "manual" else "new",
        introduced_at=datetime.utcnow() if payload.source == "manual" else None,
    )
    db.add(word)
    db.flush()
    db.add(models.SpellingReview(word_id=word.id, due_date=date.today(), interval_days=0))
    _ensure_word_content(db, word)
    db.commit()
    db.refresh(word)
    return word


def upsert_spelling_word_source(
    db: Session,
    word_id: int,
    source_name: str,
    source_level: Optional[str] = None,
    list_rank: Optional[int] = None,
) -> models.SpellingWordSource:
    if db.bind and db.bind.dialect.name == "sqlite":
        row = db.scalar(
            select(models.SpellingWordSource).where(
                models.SpellingWordSource.word_id == word_id,
                models.SpellingWordSource.source_name == source_name,
            )
        )
        if row:
            row.source_level = source_level
            row.list_rank = list_rank
            db.flush()
            return row
        row = models.SpellingWordSource(
            word_id=word_id,
            source_name=source_name,
            source_level=source_level,
            list_rank=list_rank,
        )
        db.add(row)
        db.flush()
        return row

    stmt = (
        pg_insert(models.SpellingWordSource)
        .values(
            word_id=word_id,
            source_name=source_name,
            source_level=source_level,
            list_rank=list_rank,
            added_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            constraint="uq_spelling_word_source",
            set_={"source_level": source_level, "list_rank": list_rank},
        )
        .returning(models.SpellingWordSource)
    )
    result = db.execute(stmt)
    db.flush()
    row = result.scalars().first()
    if row is None:
        row = db.scalar(
            select(models.SpellingWordSource).where(
                models.SpellingWordSource.word_id == word_id,
                models.SpellingWordSource.source_name == source_name,
            )
        )
    return row  # type: ignore[return-value]


def enrich_spelling_word_metadata(
    db: Session,
    word: models.SpellingWord,
    short_meaning: Optional[str] = None,
    example_sentence: Optional[str] = None,
    ipa: Optional[str] = None,
    part_of_speech: Optional[str] = None,
) -> models.SpellingWord:
    if short_meaning:
        word.short_meaning = short_meaning.strip()
    if example_sentence:
        word.example_sentence = example_sentence.strip()
    if ipa:
        word.ipa = ipa.strip()
    if part_of_speech:
        word.part_of_speech = part_of_speech.strip()
    db.flush()
    return word


def _fallback_content(word: models.SpellingWord) -> Dict[str, Any]:
    return {
        "meaning": word.short_meaning or _meaning_for_word(word.term),
        "ipa": word.ipa,
        "part_of_speech": word.part_of_speech or "word",
        "examples": [word.example_sentence or _example_sentence(word.term)],
        "word_family": _word_family_for(word.term),
    }


def _generate_content_with_ai(word: models.SpellingWord, model: Optional[str] = None) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _fallback_content(word)

    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt = (
        "Return JSON with keys meaning, ipa, part_of_speech, examples, word_family. "
        "examples must be a list of two short sentences. word_family must be a list of "
        f"objects with term and label. Word: {word.term}."
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": prompt},
            timeout=20,
        )
        if response.status_code >= 400:
            return _fallback_content(word)
        texts: List[str] = []
        for item in response.json().get("output", []):
            for content in item.get("content", []):
                if content.get("text"):
                    texts.append(content["text"])
        parsed = json.loads("\n".join(texts).strip())
        return {
            "meaning": str(parsed.get("meaning") or _meaning_for_word(word.term)),
            "ipa": parsed.get("ipa") or word.ipa,
            "part_of_speech": parsed.get("part_of_speech") or word.part_of_speech or "word",
            "examples": list(parsed.get("examples") or [word.example_sentence or _example_sentence(word.term)])[:3],
            "word_family": _sanitize_word_family(word.term, list(parsed.get("word_family") or _word_family_for(word.term))),
        }
    except Exception:
        return _fallback_content(word)


def _ensure_word_content(db: Session, word: models.SpellingWord, force: bool = False) -> models.SpellingWordContent:
    content = db.scalar(select(models.SpellingWordContent).where(models.SpellingWordContent.word_id == word.id))
    if content and not force:
        sanitized_family = _sanitize_word_family(word.term, content.word_family or [])
        if sanitized_family != (content.word_family or []):
            content.word_family = sanitized_family
            content.updated_at = datetime.utcnow()
            db.flush()
        return content
    settings = db.get(models.AppSettings, 1)
    generated = _generate_content_with_ai(word, model=settings.ai_model if settings else None)
    if not content:
        content = models.SpellingWordContent(word_id=word.id)
        db.add(content)
    content.meaning = generated["meaning"]
    content.ipa = generated.get("ipa")
    content.part_of_speech = generated.get("part_of_speech")
    content.examples = generated.get("examples") or []
    content.word_family = generated.get("word_family") or []
    content.status = "generated"
    content.error = None
    content.generated_at = datetime.utcnow()
    content.updated_at = datetime.utcnow()
    word.short_meaning = word.short_meaning or content.meaning
    word.ipa = word.ipa or content.ipa
    word.part_of_speech = word.part_of_speech or content.part_of_speech
    if not word.example_sentence and content.examples:
        word.example_sentence = content.examples[0]
    db.flush()
    return content


def _content_to_schema(word: models.SpellingWord, content: models.SpellingWordContent) -> schemas.SpellingWordContentRead:
    return schemas.SpellingWordContentRead(
        word_id=word.id,
        term=word.term,
        meaning=content.meaning or _meaning_for_word(word.term),
        ipa=content.ipa,
        part_of_speech=content.part_of_speech,
        examples=list(content.examples or []),
        word_family=list(content.word_family or []),
        status=content.status,
    )


def get_word_content(db: Session, word_id: int) -> schemas.SpellingWordContentRead:
    word = db.get(models.SpellingWord, word_id)
    if not word:
        raise ValueError("Word not found")
    content = _ensure_word_content(db, word)
    db.commit()
    return _content_to_schema(word, content)


def _target_oxford_words(db: Session, limit: Optional[int] = None) -> List[models.SpellingWord]:
    stmt = (
        select(models.SpellingWord)
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWord.id)
        .where(models.SpellingWord.is_active.is_(True))
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .group_by(models.SpellingWord.id)
        .order_by(func.coalesce(func.min(models.SpellingWordSource.list_rank), 999999).asc(), models.SpellingWord.term.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def _target_suggested_words(db: Session, limit: Optional[int] = None) -> List[models.SpellingWord]:
    suggested_ids = (
        select(models.SpellingSuggestion.word_id)
        .where(models.SpellingSuggestion.word_id.is_not(None))
        .where(models.SpellingSuggestion.status.in_(["pending", "auto_added", "approved"]))
    )
    stmt = (
        select(models.SpellingWord)
        .where(models.SpellingWord.is_active.is_(True))
        .where(
            or_(
                models.SpellingWord.source.in_(["llm", "llm_suggestion"]),
                models.SpellingWord.level == "suggested",
                models.SpellingWord.id.in_(suggested_ids),
            )
        )
        .order_by(models.SpellingWord.created_at.asc(), models.SpellingWord.term.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def _target_exploration_words(db: Session, pool: str = "oxford") -> List[models.SpellingWord]:
    normalized_pool = pool if pool in {"oxford", "suggested", "mixed"} else "oxford"
    attempted_ids = set(
        db.scalars(
            select(models.SpellingAttempt.word_id)
            .where(models.SpellingAttempt.mode == models.SpellingMode.exploration)
            .distinct()
        ).all()
    )

    def available(rows: Iterable[models.SpellingWord]) -> List[models.SpellingWord]:
        return [
            word
            for word in rows
            if word.id not in attempted_ids and not word.known_skipped and word.mastery_state != "mastered"
        ]

    if normalized_pool == "suggested":
        return available(_target_suggested_words(db))
    if normalized_pool == "mixed":
        combined: List[models.SpellingWord] = []
        used: set[int] = set()
        for word in [*_target_suggested_words(db), *_target_oxford_words(db)]:
            if word.id not in used:
                used.add(word.id)
                combined.append(word)
        return available(combined)
    return available(_target_oxford_words(db))


def content_bulk_status(db: Session) -> schemas.ContentBulkStatus:
    total_words = len(_target_oxford_words(db))
    generated = db.scalar(
        select(func.count(func.distinct(models.SpellingWordContent.word_id)))
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWordContent.word_id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .where(models.SpellingWordContent.status == "generated")
    ) or 0
    failed = db.scalar(
        select(func.count(func.distinct(models.SpellingWordContent.word_id)))
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWordContent.word_id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .where(models.SpellingWordContent.status == "failed")
    ) or 0
    return schemas.ContentBulkStatus(
        total_words=total_words,
        generated=generated,
        pending=max(total_words - int(generated) - int(failed), 0),
        failed=failed,
    )


def content_bulk_preview(db: Session, limit: int) -> schemas.BulkGeneratePreview:
    settings = get_settings(db)
    status = content_bulk_status(db)
    will_process = min(limit, status.pending)
    return schemas.BulkGeneratePreview(
        limit=limit,
        total_words=status.total_words,
        generated=status.generated,
        pending=status.pending,
        failed=status.failed,
        will_process=will_process,
        estimated_api_calls=will_process if os.getenv("OPENAI_API_KEY", "").strip() else 0,
        model=settings.ai_model,
    )


def content_bulk_generate(db: Session, payload: schemas.ContentBulkGenerateRequest) -> schemas.ContentBulkGenerateResult:
    generated = 0
    cached = 0
    failed = 0
    words = _target_oxford_words(db)
    for word in words:
        if generated + cached + failed >= payload.limit:
            break
        existing = db.scalar(select(models.SpellingWordContent).where(models.SpellingWordContent.word_id == word.id))
        if existing and existing.status == "generated" and not payload.force:
            continue
        try:
            _ensure_word_content(db, word, force=payload.force)
            generated += 1
        except Exception as err:
            failed += 1
            content = existing or models.SpellingWordContent(word_id=word.id)
            content.status = "failed"
            content.error = str(err)
            db.add(content)
    db.commit()
    status = content_bulk_status(db)
    return schemas.ContentBulkGenerateResult(
        requested_limit=payload.limit,
        generated=generated,
        cached=cached,
        failed=failed,
        remaining=status.pending,
    )


def _activity(
    db: Session,
    event_type: str,
    title: str,
    detail: Optional[str] = None,
    word_id: Optional[int] = None,
    points: int = 0,
    accuracy: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    db.add(
        models.ActivityEvent(
            event_type=event_type,
            title=title,
            detail=detail,
            word_id=word_id,
            points=points,
            accuracy=accuracy,
            event_metadata=metadata or {},
        )
    )


def _update_profile_after_attempt(db: Session, points: int, response_ms: Optional[int]) -> None:
    profile = get_profile(db)
    today = date.today()
    if profile.last_practice_date != today:
        if profile.last_practice_date == today - timedelta(days=1):
            profile.current_streak += 1
        else:
            profile.current_streak = 1
        profile.best_streak = max(profile.best_streak, profile.current_streak)
        profile.last_practice_date = today
    profile.points += points
    if response_ms:
        profile.practice_time_seconds += max(round(response_ms / 1000), 1)
    profile.updated_at = datetime.utcnow()


def _update_achievements(db: Session) -> None:
    ensure_app_defaults(db)
    explored = db.scalar(select(func.count(models.ActivityEvent.id)).where(models.ActivityEvent.event_type == "exploration")) or 0
    practice = db.scalar(select(func.count(models.SpellingAttempt.id)).where(models.SpellingAttempt.mode == models.SpellingMode.practice)) or 0
    dictation = db.scalar(select(func.count(models.SpellingAttempt.id)).where(models.SpellingAttempt.mode == models.SpellingMode.dictation)) or 0
    total = db.scalar(select(func.count(models.SpellingAttempt.id)).where(models.SpellingAttempt.retry_index == 0)) or 0
    correct = db.scalar(
        select(func.count(models.SpellingAttempt.id)).where(
            models.SpellingAttempt.retry_index == 0,
            models.SpellingAttempt.is_correct.is_(True),
        )
    ) or 0
    accuracy = round((correct / total) * 100) if total else 0
    profile = get_profile(db)
    progress_by_code = {
        "explorer_10": int(explored),
        "practice_25": int(practice),
        "dictation_10": int(dictation),
        "accuracy_90": int(accuracy),
        "streak_7": int(profile.current_streak),
    }
    for achievement in db.scalars(select(models.Achievement)).all():
        achievement.progress = min(progress_by_code.get(achievement.code, achievement.progress), achievement.target)
        if achievement.progress >= achievement.target and not achievement.unlocked_at:
            achievement.unlocked_at = datetime.utcnow()
            _activity(db, "achievement", f"Achievement unlocked: {achievement.title}", achievement.description)
        achievement.updated_at = datetime.utcnow()


def get_achievements(db: Session) -> List[models.Achievement]:
    ensure_app_defaults(db)
    _update_achievements(db)
    db.commit()
    return list(db.scalars(select(models.Achievement).order_by(models.Achievement.category, models.Achievement.id)).all())


def _review_priority_words(db: Session, target_size: int, mode: models.SpellingSessionType) -> List[RankedWord]:
    due_today = date.today()
    review_candidate = _actionable_review_filter(due_today)
    stmt = (
        select(models.SpellingWord)
        .join(models.SpellingReview, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(review_candidate)
    )
    if mode == models.SpellingSessionType.review_due:
        stmt = stmt.where(
            or_(
                models.SpellingReview.forced_correction_required.is_(True),
                models.SpellingReview.due_date <= due_today,
            )
        )
    return _rank_words(db, list(db.scalars(stmt).all()), mode)[:target_size]


def _scramble(word: str) -> str:
    if len(word) <= 3:
        return word[::-1]
    return word[1::2] + word[0::2]


def _choice_variants(word: str) -> List[str]:
    variants: List[str] = []
    candidates = [word]
    if len(word) > 5:
        candidates.append(word.replace("mm", "m").replace("cc", "c"))
        candidates.append(word + word[-1])
        candidates.append(word[:-1])
    for candidate in candidates:
        if candidate and candidate not in variants:
            variants.append(candidate)
    for candidate in COMMON_CONFUSION_WORDS:
        if len(variants) >= 4:
            break
        if candidate != word and candidate not in variants:
            variants.append(candidate)
    return variants[:4]


def _exercise_type_for(index: int, requested: str, session_type: models.SpellingSessionType) -> models.SpellingSessionItemType:
    if session_type == models.SpellingSessionType.dictation:
        return models.SpellingSessionItemType.sentence_dictation
    if session_type in {
        models.SpellingSessionType.diagnostic,
        models.SpellingSessionType.practice,
        models.SpellingSessionType.fix_mistakes,
        models.SpellingSessionType.review_due,
    }:
        return models.SpellingSessionItemType.review_word
    if requested != "mixed":
        return models.SpellingSessionItemType(requested)
    cycle = [
        models.SpellingSessionItemType.spelling_quiz,
        models.SpellingSessionItemType.fill_blank,
        models.SpellingSessionItemType.word_scramble,
        models.SpellingSessionItemType.choose_correct,
    ]
    return cycle[index % len(cycle)]


def _prompt_for(word: models.SpellingWord, item_type: models.SpellingSessionItemType) -> str:
    if item_type == models.SpellingSessionItemType.sentence_dictation:
        return word.example_sentence or _example_sentence(word.term)
    if item_type == models.SpellingSessionItemType.review_word:
        return "Listen to the word and type its spelling."
    if item_type == models.SpellingSessionItemType.fill_blank:
        example = word.example_sentence or _example_sentence(word.term)
        blank = f"{word.term[:1]}{'_' * max(len(word.term) - 2, 2)}{word.term[-1:]}"
        return f"{example} Target spelling: {blank}"
    if item_type == models.SpellingSessionItemType.word_scramble:
        return _scramble(word.term)
    return "Choose or type the correct spelling of the word."


def _session_item_to_schema(item: models.SpellingSessionItem) -> schemas.SpellingSessionItemOut:
    term = item.word.term if item.word else item.prompt_text
    mode = item.session.session_type.value if item.session else models.SpellingMode.practice.value
    content = item.word.content_cache if item.word else None
    return schemas.SpellingSessionItemOut(
        session_item_id=item.id,
        word_id=item.word_id,
        term=term,
        item_type=item.item_type.value,
        mode=mode,
        prompt_text=item.prompt_text,
        source_reason=item.source_reason,
        queue_reason=item.source_reason,
        selection_score=item.selection_score,
        score_breakdown=dict(item.score_breakdown or {}),
        status=item.status.value,
        audio_ready=True,
        choices=item.choices,
        short_meaning=(
            (item.word.short_meaning if item.word else None)
            or (content.meaning if content else None)
            or (_meaning_for_word(item.word.term) if item.word else None)
        ),
        part_of_speech=(
            (item.word.part_of_speech if item.word else None)
            or (content.part_of_speech if content else None)
            or ("word" if item.word else None)
        ),
        chunked_form=item.word.chunked_form if item.word else None,
        phonetic_hint=item.word.phonetic_hint if item.word else None,
        difficulty_score=item.word.difficulty_score if item.word else None,
    )


def create_spelling_session(db: Session, payload: schemas.SpellingSessionCreate) -> schemas.SpellingSessionOut:
    session_type = models.SpellingSessionType(payload.session_type)
    session = models.SpellingSession(session_type=session_type)
    db.add(session)
    db.flush()

    if session_type == models.SpellingSessionType.diagnostic:
        ranked_words = _diagnostic_candidate_words(db, payload.target_size, payload.level)
    elif session_type in {models.SpellingSessionType.learn_new, models.SpellingSessionType.exploration, models.SpellingSessionType.core_5k}:
        words = _target_oxford_words(db, limit=payload.target_size)
        words = [word for word in words if not word.known_skipped][: payload.target_size]
        ranked_words = [
            RankedWord(
                word=word,
                score=SelectionScore(total=0.0, reason=session_type.value, breakdown={}),
            )
            for word in words
        ]
    else:
        ranked_words = _review_priority_words(db, payload.target_size, session_type)

    words = [ranked.word for ranked in ranked_words]
    for idx, ranked in enumerate(ranked_words):
        word = ranked.word
        item_type = _exercise_type_for(idx, payload.exercise_type, session_type)
        if session_type in {models.SpellingSessionType.learn_new, models.SpellingSessionType.exploration, models.SpellingSessionType.core_5k}:
            item_type = models.SpellingSessionItemType.core_word
        _ensure_spelling_review(db, word)
        item = models.SpellingSessionItem(
            session_id=session.id,
            word_id=word.id,
            prompt_text=_prompt_for(word, item_type),
            item_type=item_type,
            source_reason=ranked.score.reason,
            selection_score=ranked.score.total,
            score_breakdown=ranked.score.breakdown,
            order_index=idx,
            choices=_choice_variants(word.term) if item_type in {models.SpellingSessionItemType.spelling_quiz, models.SpellingSessionItemType.choose_correct} else None,
        )
        word.introduced_at = word.introduced_at or datetime.utcnow()
        word.last_seen_at = datetime.utcnow()
        if word.mastery_state == "new" and session_type != models.SpellingSessionType.diagnostic:
            word.mastery_state = "learning"
        db.add(item)

    session.total_items = len(words)
    session.new_items = len([word for word in words if word.mastery_state in {"new", "learning"}])
    session.review_items = len(words) - session.new_items
    session.sentence_items = len([word for word in words if session_type == models.SpellingSessionType.dictation])
    db.commit()
    return get_spelling_session(db, session.id)  # type: ignore[return-value]


def get_spelling_session(db: Session, session_id: int) -> Optional[schemas.SpellingSessionOut]:
    session = db.get(models.SpellingSession, session_id)
    if not session:
        return None
    items = db.scalars(
        select(models.SpellingSessionItem)
        .where(models.SpellingSessionItem.session_id == session.id)
        .order_by(models.SpellingSessionItem.order_index.asc())
    ).all()
    session.completed_items = len(
        [item for item in items if item.status in {models.SpellingSessionItemStatus.completed, models.SpellingSessionItemStatus.skipped}]
    )
    session.is_completed = session.completed_items >= session.total_items if session.total_items else False
    db.commit()
    return schemas.SpellingSessionOut(
        session_id=session.id,
        session_type=session.session_type.value,
        total_items=session.total_items,
        completed_items=session.completed_items,
        items=[_session_item_to_schema(item) for item in items],
    )


def get_exploration_next(
    db: Session, word_id: Optional[int] = None, direction: str = "next", pool: str = "oxford"
) -> schemas.ExplorationNextOut:
    normalized_pool = pool if pool in {"oxford", "suggested", "mixed"} else "oxford"
    words = _target_exploration_words(db, normalized_pool)
    if not words:
        seed_spelling_defaults(db)
        words = _target_exploration_words(db, normalized_pool)
    if not words:
        raise ValueError("No words available")

    index = 0
    if word_id:
        ids = [word.id for word in words]
        if word_id in ids:
            current = ids.index(word_id)
            if direction == "previous":
                index = max(current - 1, 0)
            elif direction == "change":
                index = (current + 1) % len(words)
            else:
                index = min(current + 1, len(words) - 1)
    word = words[index]
    content = _ensure_word_content(db, word)
    word.last_seen_at = datetime.utcnow()
    db.commit()
    return schemas.ExplorationNextOut(
        word=schemas.SpellingWordRead.model_validate(word),
        content=_content_to_schema(word, content),
        pool=normalized_pool,
        previous_word_id=words[index - 1].id if index > 0 else None,
        next_word_id=words[index + 1].id if index < len(words) - 1 else None,
        progress_index=index + 1,
        total_words=len(words),
    )


def submit_exploration_action(db: Session, payload: schemas.ExplorationAction) -> schemas.ExplorationActionResult:
    points = 0
    if payload.action == "viewed":
        word = db.get(models.SpellingWord, payload.word_id)
        if not word:
            raise ValueError("Word not found")
        _activity(db, "exploration", f"Explored: {word.term}", word.short_meaning, word_id=word.id)
    else:
        placement = submit_spelling_placement(
            db,
            schemas.SpellingPlacementAttempt(word_id=payload.word_id, action=payload.action),
            commit=False,
        )
        points = 1 if payload.action == "practice" else 0
        _activity(db, "exploration", f"{payload.action.title()}: {placement.term}", word_id=payload.word_id, points=points)
    _update_achievements(db)
    db.commit()
    next_word = get_exploration_next(db, word_id=payload.word_id, direction="next")
    return schemas.ExplorationActionResult(
        word_id=payload.word_id,
        action=payload.action,
        next_word_id=next_word.word.id,
        points_awarded=points,
    )


def _points_for_attempt(is_correct: bool, used_hint: bool, used_reveal: bool, retry_index: int = 0) -> int:
    if not is_correct:
        return 0
    if retry_index > 0 or used_reveal:
        return 1
    if used_hint:
        return 2
    return 3


def _srs_steps_for_review(review: models.SpellingReview) -> List[int]:
    if review.incorrect_count >= 3 or review.lapse_count >= 2:
        return SRS_STEPS_HARD
    return SRS_STEPS_NORMAL


def _adaptive_interval(review: models.SpellingReview, first_try_correct: bool, forced_correction: bool) -> int:
    if forced_correction or not first_try_correct:
        return 0
    steps = _srs_steps_for_review(review)
    current = review.interval_days
    if current not in steps:
        return steps[1] if len(steps) > 1 else steps[0]
    idx = steps.index(current)
    return steps[min(idx + 1, len(steps) - 1)]


def _pattern_from_error(word: models.SpellingWord, error_pattern: str) -> str:
    if error_pattern == "close_spelling":
        if "ie" in word.term or "ei" in word.term:
            return "ie_ei_confusion"
        if any(pair in word.term for pair in ["ss", "rr", "mm", "cc"]):
            return "double_consonant"
    if error_pattern == "missing_letter":
        return "silent_letter"
    return "homophone_confusion"


def _upsert_pattern_stats(db: Session, pattern_code: Optional[str], is_correct: bool) -> None:
    if not pattern_code:
        return
    pattern = db.scalar(select(models.SpellingPattern).where(models.SpellingPattern.code == pattern_code))
    if not pattern:
        return
    stat = db.scalar(select(models.SpellingUserPatternStat).where(models.SpellingUserPatternStat.pattern_id == pattern.id))
    if not stat:
        stat = models.SpellingUserPatternStat(pattern_id=pattern.id)
        db.add(stat)
        db.flush()
    stat.total_attempts += 1
    if not is_correct:
        stat.incorrect_attempts += 1
    stat.recent_error_rate = round(stat.incorrect_attempts / stat.total_attempts, 4) if stat.total_attempts else 0.0
    stat.mastery_score = max(0.0, 1.0 - stat.recent_error_rate)
    stat.updated_at = datetime.utcnow()


def submit_spelling_attempt(db: Session, payload: schemas.SpellingAttemptCreate) -> schemas.SpellingAttemptResult:
    word = db.get(models.SpellingWord, payload.word_id)
    if not word:
        raise ValueError("Word not found")
    review = _ensure_spelling_review(db, word)
    session_item = db.get(models.SpellingSessionItem, payload.session_item_id) if payload.session_item_id else None

    dictation_assessment: Optional[DictationAssessment] = None
    if payload.mode == models.SpellingMode.dictation.value:
        expected_text = (
            session_item.prompt_text
            if session_item
            else word.example_sentence or _example_sentence(word.term)
        )
        dictation_assessment = _assess_dictation(expected_text, payload.attempt_text, word.term)
        # Dictation advances spelling mastery from the target spelling only.
        # Sentence completeness is a separate feedback signal.
        correct = dictation_assessment.target_spelling_correct
    else:
        correct = _normalize_text(payload.attempt_text) == _normalize_text(word.term)
    if payload.mode == models.SpellingMode.dictation.value:
        feedback_attempt_text = word.term if correct else _closest_target_attempt(word.term, payload.attempt_text)
    else:
        feedback_attempt_text = payload.attempt_text
    was_forced_correction = review.forced_correction_required
    retry_index = review.consecutive_forced_corrections if was_forced_correction else 0
    mastery_state_before = _state_for_word(word, review)
    due_provisional_audit = _is_due_provisional_audit(word, review)
    was_stable_before = _is_stable_state(mastery_state_before) or review.current_stage == models.SpellingStage.mastered
    is_diagnostic = payload.mode == models.SpellingMode.diagnostic.value
    is_exploration_first_try = (
        payload.mode == models.SpellingMode.exploration.value and retry_index == 0 and not was_forced_correction
    )
    pattern = "none" if correct else _error_pattern(word.term, feedback_attempt_text)
    points = _points_for_attempt(correct, payload.used_hint, payload.used_reveal, retry_index)
    feedback = _cached_llm_feedback(db, word, feedback_attempt_text, pattern)
    diff_json = None
    sentence_diff_json = None
    now = datetime.utcnow()
    if dictation_assessment is not None:
        sentence_diff_json = _build_sentence_diff_json(
            expected_text,
            payload.attempt_text,
            word.term,
            dictation_assessment,
        )

    word.known_skipped = False
    word.introduced_at = word.introduced_at or now
    word.last_seen_at = now

    mastery_state_after: Optional[str] = None
    if correct:
        if is_diagnostic:
            word.diagnostic_status = "passed"
            word.priority_score = max(0.0, round(_word_usefulness_score(word) * 0.1, 4))
            review.consecutive_correct = max(review.consecutive_correct, 1)
            review.mastery_score = max(review.mastery_score, 1.0)
            review.ease_factor = min(3.0, review.ease_factor + 0.05)
            review.interval_days = PROVISIONAL_AUDIT_DAYS
            review.due_date = date.today() + timedelta(days=PROVISIONAL_AUDIT_DAYS)
            review.forced_correction_required = False
            review.consecutive_forced_corrections = 0
            review.current_stage = models.SpellingStage.review
            mastery_state_after = "known_provisional"
        elif was_forced_correction:
            review.mastery_score += 0.25
            review.interval_days = 0
            review.due_date = date.today()
            review.forced_correction_required = False
            review.consecutive_forced_corrections = 0
            mastery_state_after = "lapse" if mastery_state_before == "lapse" else None
        elif is_exploration_first_try:
            review.consecutive_correct = max(review.consecutive_correct, 1)
            review.mastery_score = max(review.mastery_score, 1.0)
            review.ease_factor = min(3.0, review.ease_factor + 0.05)
            review.interval_days = PROVISIONAL_AUDIT_DAYS
            review.due_date = date.today() + timedelta(days=PROVISIONAL_AUDIT_DAYS)
            review.forced_correction_required = False
            review.consecutive_forced_corrections = 0
            review.current_stage = models.SpellingStage.review
            mastery_state_after = "known_provisional"
        elif due_provisional_audit:
            review.consecutive_correct = max(review.consecutive_correct + 1, 2)
            review.mastery_score = max(review.mastery_score + 1.0, float(word.mastery_threshold))
            review.ease_factor = min(3.0, review.ease_factor + 0.05)
            review.interval_days = STABLE_AUDIT_DAYS
            review.due_date = date.today() + timedelta(days=STABLE_AUDIT_DAYS)
            review.forced_correction_required = False
            review.consecutive_forced_corrections = 0
            review.current_stage = models.SpellingStage.mastered
            mastery_state_after = "stable_known"
        else:
            review.consecutive_correct += 1
            review.mastery_score += 1.0
            review.ease_factor = min(3.0, review.ease_factor + 0.05)
            interval = _adaptive_interval(review, first_try_correct=True, forced_correction=False)
            review.interval_days = interval
            review.due_date = date.today() + timedelta(days=interval)
            if was_stable_before:
                review.current_stage = models.SpellingStage.mastered
                mastery_state_after = "stable_known"
    else:
        review.consecutive_correct = 0
        review.incorrect_count += 1
        if was_stable_before or due_provisional_audit:
            review.lapse_count += 1
        review.mastery_score = max(0.0, review.mastery_score - 0.5)
        review.ease_factor = max(1.5, review.ease_factor - 0.15)
        review.interval_days = 0
        review.due_date = date.today()
        review.forced_correction_required = False if is_diagnostic else True
        review.consecutive_forced_corrections = 0 if not was_forced_correction else review.consecutive_forced_corrections + 1
        diff_json = _build_diff_json(word.term, feedback_attempt_text)
        _create_suggestion_from_error(db, word, pattern)
        if is_diagnostic:
            word.diagnostic_status = "missed"
            word.priority_score = round(DIAGNOSTIC_PRIORITY_BOOST + _word_usefulness_score(word), 4)
            mastery_state_after = "learning"
        else:
            mastery_state_after = "lapse" if (was_stable_before or due_provisional_audit) else None

    review.updated_at = now
    review.last_attempt_at = now
    if payload.response_ms is not None:
        review.average_response_ms = (
            float(payload.response_ms)
            if review.average_response_ms is None
            else (review.average_response_ms * 0.8) + (payload.response_ms * 0.2)
        )

    if mastery_state_after == "stable_known":
        review.current_stage = models.SpellingStage.mastered
    elif mastery_state_after == "known_provisional":
        review.current_stage = models.SpellingStage.review
    elif mastery_state_after == "lapse":
        review.current_stage = models.SpellingStage.trouble
    elif is_diagnostic and not correct:
        review.current_stage = models.SpellingStage.trouble
    elif review.mastery_score >= word.mastery_threshold and review.interval_days >= PROVISIONAL_AUDIT_DAYS:
        review.current_stage = models.SpellingStage.mastered
        mastery_state_after = "stable_known"
    elif review.incorrect_count >= 3:
        review.current_stage = models.SpellingStage.trouble
    elif review.consecutive_correct >= 2:
        review.current_stage = models.SpellingStage.review
    else:
        review.current_stage = models.SpellingStage.learning
    if mastery_state_after is None:
        mastery_state_after = "review" if review.current_stage == models.SpellingStage.mastered else review.current_stage.value
    word.mastery_state = mastery_state_after

    skip_available = review.forced_correction_required and review.consecutive_forced_corrections >= FORCED_CORRECTION_SKIP_AFTER
    allow_next = correct or skip_available or is_diagnostic

    attempt = models.SpellingAttempt(
        word_id=word.id,
        attempt_date=date.today(),
        attempt_text=payload.attempt_text.strip(),
        is_correct=correct,
        points_awarded=points,
        error_pattern=None if correct else pattern,
        llm_feedback=feedback,
        response_ms=payload.response_ms,
        mode=models.SpellingMode(payload.mode),
        input_method=payload.input_method,
        diff_json=diff_json,
        chunk_feedback=word.chunked_form or _chunk_hint(word.term),
        phonetic_feedback=_phonetic_feedback(word),
        retry_index=retry_index,
        was_forced_correction=was_forced_correction,
        mastery_state_before=mastery_state_before,
        mastery_state_after=mastery_state_after,
        confidence_score=payload.confidence_score,
        session_id=payload.session_id,
        session_item_id=payload.session_item_id,
    )
    db.add(attempt)

    if payload.session_item_id:
        item = session_item
        if item:
            if correct or is_diagnostic:
                item.status = models.SpellingSessionItemStatus.completed
                item.forced_correction_done = was_forced_correction
            elif skip_available:
                item.status = models.SpellingSessionItemStatus.skipped

    if payload.session_id:
        session = db.get(models.SpellingSession, payload.session_id)
        if session:
            if correct and retry_index == 0:
                session.correct_first_try += 1
            if was_forced_correction and correct:
                session.forced_corrections += 1
            session.completed_items = db.scalar(
                select(func.count(models.SpellingSessionItem.id)).where(
                    models.SpellingSessionItem.session_id == session.id,
                    models.SpellingSessionItem.status.in_(
                        [models.SpellingSessionItemStatus.completed, models.SpellingSessionItemStatus.skipped]
                    ),
                )
            ) or 0
            session.is_completed = session.completed_items >= session.total_items if session.total_items else False

    _upsert_pattern_stats(db, _pattern_from_error(word, pattern) if not correct else None, correct)
    _update_profile_after_attempt(db, points, payload.response_ms)
    _activity(
        db,
        payload.mode,
        f"{'Correct' if correct else 'Missed'}: {word.term}",
        feedback,
        word_id=word.id,
        points=points,
        accuracy=1.0 if correct else 0.0,
    )
    _update_achievements(db)
    db.commit()
    db.refresh(attempt)

    return schemas.SpellingAttemptResult(
        attempt_id=attempt.id,
        word_id=word.id,
        term=word.term,
        attempt_text=payload.attempt_text,
        is_correct=correct,
        points_awarded=points,
        error_pattern=None if correct else pattern,
        next_due_date=review.due_date,
        llm_feedback=feedback,
        chunk_hint=word.chunked_form or _chunk_hint(word.term),
        mnemonic=_mnemonic_for_word(word.term),
        example_sentence=word.example_sentence or _example_sentence(word.term),
        diff_json=diff_json,
        sentence_diff_json=sentence_diff_json,
        target_spelling_correct=(
            dictation_assessment.target_spelling_correct if dictation_assessment is not None else None
        ),
        sentence_complete=dictation_assessment.sentence_complete if dictation_assessment is not None else None,
        sentence_similarity=(
            dictation_assessment.sentence_similarity if dictation_assessment is not None else None
        ),
        chunk_feedback=word.chunked_form or _chunk_hint(word.term),
        phonetic_feedback=_phonetic_feedback(word),
        forced_correction_required=review.forced_correction_required,
        allow_next=allow_next,
        mastery_state=word.mastery_state,
        mastery_state_before=mastery_state_before,
        mastery_state_after=mastery_state_after,
        retry_prompt=None if allow_next else "Type the correct spelling once before moving on.",
        retry_index=retry_index,
        skip_available=skip_available,
        skip_after_retries=FORCED_CORRECTION_SKIP_AFTER,
    )


def submit_spelling_correction(
    db: Session, attempt_id: int, payload: schemas.SpellingCorrectionSubmit
) -> schemas.SpellingCorrectionResult:
    attempt = db.get(models.SpellingAttempt, attempt_id)
    if not attempt:
        raise ValueError("Attempt not found")
    word = db.get(models.SpellingWord, attempt.word_id)
    if not word:
        raise ValueError("Word not found")
    review = _ensure_spelling_review(db, word)
    mastery_state_before = _state_for_word(word, review)

    accepted = _normalize_text(payload.correction_text) == _normalize_text(word.term)
    if not accepted:
        review.consecutive_forced_corrections += 1
        skip_available = review.consecutive_forced_corrections >= FORCED_CORRECTION_SKIP_AFTER
        if skip_available:
            review.forced_correction_required = False
            if attempt.session_item_id:
                item = db.get(models.SpellingSessionItem, attempt.session_item_id)
                if item:
                    item.status = models.SpellingSessionItemStatus.skipped
        review.updated_at = datetime.utcnow()
        db.commit()
        return schemas.SpellingCorrectionResult(
            accepted=False,
            allow_next=skip_available,
            review_stage=review.current_stage.value,
            due_date=review.due_date,
            retries_remaining=max(FORCED_CORRECTION_SKIP_AFTER - review.consecutive_forced_corrections, 0),
            skip_available=skip_available,
        )

    correction_attempt = models.SpellingAttempt(
        word_id=word.id,
        attempt_date=date.today(),
        attempt_text=payload.correction_text,
        is_correct=True,
        points_awarded=1,
        mode=attempt.mode,
        input_method="typed",
        retry_index=max(attempt.retry_index + 1, 1),
        was_forced_correction=True,
        mastery_state_before=mastery_state_before,
        mastery_state_after=word.mastery_state,
        session_id=attempt.session_id,
        session_item_id=attempt.session_item_id,
        chunk_feedback=word.chunked_form,
        phonetic_feedback=_phonetic_feedback(word),
    )
    db.add(correction_attempt)
    review.forced_correction_required = False
    review.consecutive_forced_corrections = 0
    review.interval_days = 0
    review.due_date = date.today()
    review.mastery_score += 0.25
    review.updated_at = datetime.utcnow()
    if attempt.session_item_id:
        item = db.get(models.SpellingSessionItem, attempt.session_item_id)
        if item:
            item.status = models.SpellingSessionItemStatus.completed
            item.forced_correction_done = True
    _update_profile_after_attempt(db, 1, None)
    _activity(db, "correction", f"Correction accepted: {word.term}", word_id=word.id, points=1, accuracy=1.0)
    _update_achievements(db)
    db.commit()
    return schemas.SpellingCorrectionResult(
        accepted=True,
        allow_next=True,
        review_stage=review.current_stage.value,
        due_date=review.due_date,
        retries_remaining=0,
        skip_available=False,
    )


def _create_suggestion_from_error(db: Session, word: models.SpellingWord, pattern: str) -> None:
    candidates: List[str] = []
    for group in CONFUSION_GROUPS:
        if word.term in group:
            candidates.extend([candidate for candidate in group if candidate != word.term])
            break
    for candidate in COMMON_CONFUSION_WORDS:
        if candidate == word.term:
            continue
        similarity = SequenceMatcher(None, word.term, candidate).ratio()
        if pattern == "close_spelling" and similarity >= 0.45:
            candidates.append(candidate)
        elif pattern != "close_spelling" and similarity >= 0.35:
            candidates.append(candidate)
    if not candidates:
        candidates = [candidate for candidate in COMMON_CONFUSION_WORDS if candidate != word.term]

    deduped: List[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    for candidate in deduped[:3]:
        term = candidate.strip().lower()
        if len(term) < 3 or term == word.term:
            continue
        related_word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == term))
        if not related_word:
            related_word = models.SpellingWord(
                term=term,
                level="personal",
                source="llm_suggestion",
                chunked_form=_chunk_hint(term),
                example_sentence=_example_sentence(term),
                difficulty_score=0.7,
                mastery_state="learning",
                introduced_at=datetime.utcnow(),
            )
            db.add(related_word)
            db.flush()
            db.add(models.SpellingReview(word_id=related_word.id, due_date=date.today(), interval_days=0))
        reason = f"Auto-added due to {pattern} while practicing '{word.term}'"
        suggestion = db.scalar(select(models.SpellingSuggestion).where(models.SpellingSuggestion.term == term))
        if suggestion:
            suggestion.word_id = related_word.id
            suggestion.reason = reason
            suggestion.status = "auto_added"
        else:
            db.add(models.SpellingSuggestion(word_id=related_word.id, term=term, reason=reason, status="auto_added"))


def list_spelling_suggestions(db: Session, status: str = "pending") -> List[models.SpellingSuggestion]:
    stmt = select(models.SpellingSuggestion).order_by(models.SpellingSuggestion.created_at.desc())
    if status:
        stmt = stmt.where(models.SpellingSuggestion.status == status)
    return list(db.scalars(stmt).all())


def update_spelling_suggestion(
    db: Session, suggestion_id: int, payload: schemas.SpellingSuggestionAction
) -> Optional[models.SpellingSuggestion]:
    suggestion = db.get(models.SpellingSuggestion, suggestion_id)
    if not suggestion:
        return None
    suggestion.status = payload.status
    db.commit()
    db.refresh(suggestion)
    return suggestion


def submit_spelling_placement(
    db: Session, payload: schemas.SpellingPlacementAttempt, commit: bool = True
) -> schemas.SpellingPlacementResult:
    word = db.get(models.SpellingWord, payload.word_id)
    if not word:
        raise ValueError("Word not found")
    review = _ensure_spelling_review(db, word)
    now = datetime.utcnow()
    word.is_active = True
    word.introduced_at = word.introduced_at or now
    word.last_seen_at = now
    if payload.action == "known":
        word.known_skipped = True
        word.mastery_state = "known"
        review.current_stage = models.SpellingStage.mastered
        review.mastery_score = max(review.mastery_score, float(word.mastery_threshold))
        review.interval_days = 3650
        review.due_date = date.today() + timedelta(days=3650)
        review.forced_correction_required = False
        review.consecutive_forced_corrections = 0
        review.consecutive_correct = max(review.consecutive_correct, word.mastery_threshold)
        if payload.session_item_id:
            item = db.get(models.SpellingSessionItem, payload.session_item_id)
            if item:
                item.status = models.SpellingSessionItemStatus.skipped
    else:
        word.known_skipped = False
        word.mastery_state = "learning"
        review.current_stage = models.SpellingStage.learning
        review.due_date = date.today()
        review.interval_days = 0
    review.updated_at = now
    if commit:
        db.commit()
    return schemas.SpellingPlacementResult(
        word_id=word.id,
        term=word.term,
        mastery_state=word.mastery_state,
        known_skipped=word.known_skipped,
        due_date=review.due_date,
    )


def get_spelling_overview(db: Session, as_of: date) -> schemas.SpellingOverview:
    due_today = db.scalar(
        select(func.count(models.SpellingReview.id))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(_actionable_review_filter(as_of))
        .where(models.SpellingReview.due_date <= as_of)
    ) or 0
    hard_words = db.scalar(
        select(func.count(models.SpellingReview.id))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(models.SpellingReview.incorrect_count >= 2)
    ) or 0
    attempts_today = db.scalar(
        select(func.count(models.SpellingAttempt.id)).where(models.SpellingAttempt.attempt_date == as_of)
    ) or 0
    points_today = db.scalar(
        select(func.coalesce(func.sum(models.SpellingAttempt.points_awarded), 0)).where(
            models.SpellingAttempt.attempt_date == as_of
        )
    ) or 0
    return schemas.SpellingOverview(
        due_today=due_today,
        hard_words=hard_words,
        attempts_today=attempts_today,
        points_today=points_today,
    )


def get_spelling_analytics(db: Session) -> schemas.SpellingAnalyticsOut:
    mastered_words = db.scalar(
        select(func.count(models.SpellingReview.id))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(models.SpellingReview.current_stage == models.SpellingStage.mastered)
    ) or 0
    learning_words = db.scalar(
        select(func.count(models.SpellingReview.id))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(models.SpellingReview.current_stage == models.SpellingStage.learning)
    ) or 0
    trouble_words = db.scalar(
        select(func.count(models.SpellingReview.id))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(models.SpellingReview.current_stage == models.SpellingStage.trouble)
    ) or 0
    total = db.scalar(select(func.count(models.SpellingAttempt.id)).where(models.SpellingAttempt.retry_index == 0)) or 0
    correct = db.scalar(
        select(func.count(models.SpellingAttempt.id)).where(
            models.SpellingAttempt.retry_index == 0,
            models.SpellingAttempt.is_correct.is_(True),
        )
    ) or 0
    top_patterns = []
    for row in db.scalars(select(models.SpellingUserPatternStat).order_by(models.SpellingUserPatternStat.recent_error_rate.desc()).limit(5)).all():
        pattern = db.get(models.SpellingPattern, row.pattern_id)
        if pattern:
            top_patterns.append(
                {
                    "code": pattern.code,
                    "label": pattern.label,
                    "recent_error_rate": row.recent_error_rate,
                    "mastery_score": row.mastery_score,
                    "examples": pattern.examples or [],
                }
            )
    return schemas.SpellingAnalyticsOut(
        mastered_words=mastered_words,
        learning_words=learning_words,
        trouble_words=trouble_words,
        average_first_try_accuracy=round((correct / total), 4) if total else 0.0,
        retention_7d=None,
        top_patterns=top_patterns,
    )


def get_core5k_overview(db: Session) -> schemas.Core5KOverviewOut:
    today = date.today()
    total_words = db.scalar(
        select(func.count(func.distinct(models.SpellingWord.id)))
        .select_from(models.SpellingWord)
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWord.id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
    ) or 0
    if total_words == 0:
        total_words = db.scalar(select(func.count(models.SpellingWord.id)).where(models.SpellingWord.is_active.is_(True))) or 0
    attempted_words = db.scalar(select(func.count(func.distinct(models.SpellingAttempt.word_id)))) or 0
    mastered_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id))).where(
            models.SpellingReview.current_stage == models.SpellingStage.mastered
        )
    ) or 0
    in_learning_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id))).where(
            models.SpellingReview.current_stage.in_([models.SpellingStage.learning, models.SpellingStage.review])
        )
    ) or 0
    due_today_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id)))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(_actionable_review_filter(today))
        .where(models.SpellingReview.due_date <= today)
    ) or 0
    return schemas.Core5KOverviewOut(
        total_words=total_words,
        attempted_words=attempted_words,
        mastered_words=mastered_words,
        in_learning_words=in_learning_words,
        due_today_words=due_today_words,
        coverage_percent=round((attempted_words / total_words) * 100, 2) if total_words else 0.0,
    )


def get_spelling_modes_overview(db: Session) -> schemas.SpellingModesOverviewOut:
    rows = db.execute(
        select(
            models.SpellingAttempt.mode,
            func.count(models.SpellingAttempt.id),
            func.sum(func.cast(models.SpellingAttempt.is_correct, Integer)),
        ).group_by(models.SpellingAttempt.mode)
    ).all()
    metrics: List[schemas.SpellingModeMetric] = []
    for mode, total_attempts, correct_attempts in rows:
        total = int(total_attempts or 0)
        correct = int(correct_attempts or 0)
        metrics.append(
            schemas.SpellingModeMetric(
                mode=mode.value if hasattr(mode, "value") else str(mode),
                total_attempts=total,
                correct_attempts=correct,
                accuracy=round((correct / total), 4) if total else 0.0,
            )
        )
    return schemas.SpellingModesOverviewOut(modes=metrics)


def get_spelling_daily_plan(db: Session) -> schemas.SpellingDailyPlanOut:
    today = date.today()
    review_candidate = _actionable_review_filter(today)
    due_reviews = db.scalar(
        select(func.count(models.SpellingReview.id))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(review_candidate)
        .where(models.SpellingReview.due_date <= today)
    ) or 0
    mistake_words = db.scalar(
        select(func.count(models.SpellingReview.id))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(
            or_(
                models.SpellingReview.forced_correction_required.is_(True),
                models.SpellingWord.diagnostic_status == "missed",
                models.SpellingReview.incorrect_count > 0,
                models.SpellingReview.lapse_count > 0,
                models.SpellingReview.current_stage == models.SpellingStage.trouble,
            )
        )
    ) or 0
    new_words = db.scalar(
        select(func.count(models.SpellingWord.id))
        .where(*_active_learning_word_filter())
        .where(or_(models.SpellingWord.introduced_at.is_(None), models.SpellingWord.mastery_state == "new"))
    ) or 0
    dictation_ready = db.scalar(
        select(func.count(models.SpellingWord.id))
        .where(*_active_learning_word_filter())
        .where(models.SpellingWord.introduced_at.is_not(None))
    ) or 0
    diagnostic_ranked = _diagnostic_candidate_words(db, 10)
    practice_ranked = _review_priority_words(db, 10, models.SpellingSessionType.practice)
    review_due_ranked = _review_priority_words(db, 10, models.SpellingSessionType.review_due)
    scheduled_review_ranked = [
        item
        for item in review_due_ranked
        if item.score.reason in {"delayed audit", "due review"}
    ]
    exploration_words = _target_exploration_words(db)

    def top_learning_value(items: List[RankedWord]) -> float:
        top = items[:3]
        return round(sum(item.score.total for item in top) / len(top), 4) if top else 0.0

    diagnostic_coverage_pressure = min(len(diagnostic_ranked) / 5, 2.0)
    mode_scores = {
        models.SpellingSessionType.diagnostic.value: round(
            top_learning_value(diagnostic_ranked) + diagnostic_coverage_pressure,
            4,
        ),
        models.SpellingSessionType.practice.value: (
            top_learning_value(practice_ranked) if mistake_words else 0.0
        ),
        models.SpellingSessionType.review_due.value: (
            top_learning_value(scheduled_review_ranked) if due_reviews else 0.0
        ),
        models.SpellingSessionType.exploration.value: (
            round(
                max(
                    (_word_usefulness_score(word) for word in exploration_words),
                    default=0.0,
                )
                + 1.0,
                4,
            )
            if exploration_words
            else 0.0
        ),
        models.SpellingSessionType.dictation.value: (
            round(top_learning_value(practice_ranked) * 0.8, 4)
            if practice_ranked
            else round(1.0 + min(dictation_ready, 10) * 0.05, 4)
            if dictation_ready
            else 0.0
        ),
    }
    recommended = max(mode_scores, key=mode_scores.get)
    recommended_reasons = {
        models.SpellingSessionType.diagnostic.value: "Expand diagnostic coverage with high-value untested words.",
        models.SpellingSessionType.practice.value: "Repair the highest-risk recent spelling mistakes.",
        models.SpellingSessionType.review_due.value: "Complete the most valuable scheduled reviews.",
        models.SpellingSessionType.exploration.value: "Introduce a useful new Oxford word.",
        models.SpellingSessionType.dictation.value: "Strengthen recall through sentence dictation.",
    }
    return schemas.SpellingDailyPlanOut(
        recommended_mode=recommended,
        recommended_reason=recommended_reasons[recommended],
        mode_scores=mode_scores,
        due_reviews=due_reviews,
        mistake_words=mistake_words,
        new_words=new_words,
        dictation_ready=dictation_ready,
    )


def get_spelling_cost_overview(db: Session) -> schemas.SpellingCostOverview:
    return schemas.SpellingCostOverview(
        feedback_cache_entries=db.scalar(select(func.count(models.SpellingFeedbackCache.id))) or 0,
        feedback_cache_hits=db.scalar(select(func.coalesce(func.sum(models.SpellingFeedbackCache.hit_count), 0))) or 0,
        estimated_feedback_input_tokens=db.scalar(select(func.coalesce(func.sum(models.SpellingFeedbackCache.estimated_input_tokens), 0))) or 0,
        estimated_feedback_output_tokens=db.scalar(select(func.coalesce(func.sum(models.SpellingFeedbackCache.estimated_output_tokens), 0))) or 0,
        generated_audio_files=db.scalar(
            select(func.count(models.SpellingAudioManifest.id)).where(models.SpellingAudioManifest.status == "generated")
        ) or 0,
        failed_audio_files=db.scalar(
            select(func.count(models.SpellingAudioManifest.id)).where(models.SpellingAudioManifest.status == "failed")
        ) or 0,
    )


def _accuracy_for_modes(db: Session, modes: Optional[List[models.SpellingMode]] = None) -> float:
    filters = [models.SpellingAttempt.retry_index == 0]
    if modes:
        filters.append(models.SpellingAttempt.mode.in_(modes))
    total = db.scalar(select(func.count(models.SpellingAttempt.id)).where(*filters)) or 0
    correct = db.scalar(
        select(func.count(models.SpellingAttempt.id)).where(*filters, models.SpellingAttempt.is_correct.is_(True))
    ) or 0
    return round((correct / total), 4) if total else 0.0


def _retention_accuracy_after_days(db: Session, days: int) -> float:
    rows = db.execute(
        select(models.SpellingAttempt.is_correct, models.SpellingAttempt.created_at, models.SpellingWord.introduced_at)
        .join(models.SpellingWord, models.SpellingAttempt.word_id == models.SpellingWord.id)
        .where(models.SpellingAttempt.retry_index == 0)
        .where(models.SpellingWord.introduced_at.is_not(None))
    ).all()
    eligible = [
        is_correct
        for is_correct, attempted_at, introduced_at in rows
        if introduced_at and attempted_at and (attempted_at - introduced_at).days >= days
    ]
    if not eligible:
        return 0.0
    return round(sum(1 for is_correct in eligible if is_correct) / len(eligible), 4)


def _lapse_rate(db: Session) -> float:
    filters = [
        models.SpellingAttempt.retry_index == 0,
        models.SpellingAttempt.mastery_state_before.in_(list(STABLE_MASTERY_STATES)),
    ]
    total = db.scalar(select(func.count(models.SpellingAttempt.id)).where(*filters)) or 0
    if not total:
        return 0.0
    missed = db.scalar(
        select(func.count(models.SpellingAttempt.id)).where(*filters, models.SpellingAttempt.is_correct.is_(False))
    ) or 0
    return round(missed / total, 4)


def _dashboard_pattern_metrics(db: Session, limit: int = 5) -> List[schemas.DashboardPatternMetric]:
    rows = db.execute(
        select(models.SpellingUserPatternStat, models.SpellingPattern)
        .join(models.SpellingPattern, models.SpellingUserPatternStat.pattern_id == models.SpellingPattern.id)
        .where(models.SpellingUserPatternStat.total_attempts > 0)
        .order_by(models.SpellingUserPatternStat.recent_error_rate.desc(), models.SpellingUserPatternStat.total_attempts.desc())
        .limit(limit)
    ).all()
    return [
        schemas.DashboardPatternMetric(
            code=pattern.code,
            label=pattern.label,
            total_attempts=stat.total_attempts,
            incorrect_attempts=stat.incorrect_attempts,
            recent_error_rate=stat.recent_error_rate,
        )
        for stat, pattern in rows
    ]


def get_dashboard_stats(db: Session) -> schemas.DashboardStats:
    today = date.today()
    oxford_word_ids = (
        select(models.SpellingWordSource.word_id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .distinct()
    )
    review_candidate = _actionable_review_filter(today)

    oxford_loaded_words = db.scalar(select(func.count()).select_from(oxford_word_ids.subquery())) or 0
    oxford_explored_words = db.scalar(
        select(func.count(func.distinct(models.SpellingWord.id)))
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWord.id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .where(models.SpellingWord.introduced_at.is_not(None))
    ) or 0
    practice_distinct_words = db.scalar(
        select(func.count(func.distinct(models.SpellingAttempt.word_id))).where(models.SpellingAttempt.mode == models.SpellingMode.practice)
    ) or 0
    dictation_distinct_words = db.scalar(
        select(func.count(func.distinct(models.SpellingAttempt.word_id))).where(models.SpellingAttempt.mode == models.SpellingMode.dictation)
    ) or 0
    diagnostic_tested_words = db.scalar(
        select(func.count(func.distinct(models.SpellingAttempt.word_id))).where(models.SpellingAttempt.mode == models.SpellingMode.diagnostic)
    ) or 0
    diagnostic_attempted_ids = (
        select(models.SpellingAttempt.word_id)
        .where(models.SpellingAttempt.mode == models.SpellingMode.diagnostic)
        .distinct()
    )
    diagnostic_ready_words = db.scalar(
        select(func.count(models.SpellingWord.id))
        .where(models.SpellingWord.is_active.is_(True))
        .where(models.SpellingWord.known_skipped.is_(False))
        .where(models.SpellingWord.id.not_in(diagnostic_attempted_ids))
    ) or 0
    diagnostic_missed_words = db.scalar(
        select(func.count(models.SpellingWord.id)).where(models.SpellingWord.diagnostic_status == "missed")
    ) or 0
    known_provisional_words = db.scalar(
        select(func.count(models.SpellingWord.id)).where(models.SpellingWord.mastery_state == "known_provisional")
    ) or 0
    stable_known_words = db.scalar(
        select(func.count(models.SpellingWord.id)).where(models.SpellingWord.mastery_state == "stable_known")
    ) or 0
    mastered_words = stable_known_words
    due_audit_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id)))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(models.SpellingWord.mastery_state == "known_provisional")
        .where(models.SpellingReview.due_date <= today)
    ) or 0
    learning_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id))).where(
            models.SpellingReview.current_stage.in_([models.SpellingStage.learning, models.SpellingStage.review])
        )
    ) or 0
    trouble_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id))).where(
            models.SpellingReview.current_stage == models.SpellingStage.trouble
        )
    ) or 0
    due_today_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id)))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(review_candidate)
        .where(models.SpellingReview.due_date <= today)
    ) or 0
    review_debt_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id)))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(review_candidate)
        .where(models.SpellingReview.due_date < today)
    ) or 0
    forced_correction_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id))).where(
            models.SpellingReview.forced_correction_required.is_(True)
        )
    ) or 0
    practice_queue_words = db.scalar(
        select(func.count(func.distinct(models.SpellingReview.word_id)))
        .join(models.SpellingWord, models.SpellingReview.word_id == models.SpellingWord.id)
        .where(*_active_learning_word_filter())
        .where(review_candidate)
    ) or 0
    dictation_ready_words = practice_queue_words
    llm_suggested_words = db.scalar(
        select(func.count(models.SpellingSuggestion.id)).where(
            models.SpellingSuggestion.status.in_(["pending", "auto_added", "approved"])
        )
    ) or 0
    llm_pending_suggestions = db.scalar(
        select(func.count(models.SpellingSuggestion.id)).where(models.SpellingSuggestion.status.in_(["pending", "auto_added"]))
    ) or 0
    content_generated_words = db.scalar(
        select(func.count(func.distinct(models.SpellingWordContent.word_id)))
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWordContent.word_id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .where(models.SpellingWordContent.status == "generated")
    ) or 0
    audio_generated_words = db.scalar(
        select(func.count(func.distinct(models.SpellingAudioManifest.word_id)))
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingAudioManifest.word_id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .where(models.SpellingAudioManifest.status == "generated")
    ) or 0

    return schemas.DashboardStats(
        oxford_loaded_words=oxford_loaded_words,
        oxford_explored_words=oxford_explored_words,
        practice_distinct_words=practice_distinct_words,
        dictation_distinct_words=dictation_distinct_words,
        mastered_words=mastered_words,
        learning_words=learning_words,
        trouble_words=trouble_words,
        due_today_words=due_today_words,
        forced_correction_words=forced_correction_words,
        practice_queue_words=practice_queue_words,
        dictation_ready_words=dictation_ready_words,
        diagnostic_ready_words=diagnostic_ready_words,
        diagnostic_tested_words=diagnostic_tested_words,
        diagnostic_missed_words=diagnostic_missed_words,
        diagnostic_accuracy=_accuracy_for_modes(db, [models.SpellingMode.diagnostic]),
        first_try_accuracy=_accuracy_for_modes(db),
        exploration_accuracy=_accuracy_for_modes(db, [models.SpellingMode.exploration]),
        practice_accuracy=_accuracy_for_modes(db, [models.SpellingMode.practice]),
        dictation_accuracy=_accuracy_for_modes(db, [models.SpellingMode.dictation]),
        retention_accuracy_7d=_retention_accuracy_after_days(db, 7),
        retention_accuracy_14d=_retention_accuracy_after_days(db, 14),
        retention_accuracy_30d=_retention_accuracy_after_days(db, 30),
        retention_accuracy_60d=_retention_accuracy_after_days(db, 60),
        lapse_rate=_lapse_rate(db),
        review_debt_words=review_debt_words,
        known_provisional_words=known_provisional_words,
        stable_known_words=stable_known_words,
        due_audit_words=due_audit_words,
        llm_suggested_words=llm_suggested_words,
        llm_pending_suggestions=llm_pending_suggestions,
        content_generated_words=content_generated_words,
        audio_generated_words=audio_generated_words,
        pattern_error_rates=_dashboard_pattern_metrics(db),
    )


def get_dashboard(db: Session) -> schemas.DashboardOut:
    profile = get_profile(db)
    overview = get_spelling_overview(db, date.today())
    core = get_core5k_overview(db)
    analytics = get_spelling_analytics(db)
    stats = get_dashboard_stats(db)
    activity = list(
        db.scalars(select(models.ActivityEvent).order_by(models.ActivityEvent.created_at.desc()).limit(8)).all()
    )
    achievements = get_achievements(db)
    words_learned = db.scalar(
        select(func.count(models.SpellingWord.id)).where(models.SpellingWord.introduced_at.is_not(None))
    ) or 0
    return schemas.DashboardOut(
        profile=schemas.ProfileRead.model_validate(profile),
        overview=overview,
        core5k=core,
        stats=stats,
        words_learned=words_learned,
        accuracy=analytics.average_first_try_accuracy,
        practice_time_seconds=profile.practice_time_seconds,
        recent_activity=[schemas.ActivityRead.model_validate(row) for row in activity],
        achievements=[schemas.AchievementRead.model_validate(row) for row in achievements[:5]],
    )
