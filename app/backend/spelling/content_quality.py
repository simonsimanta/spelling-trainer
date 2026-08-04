from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


PART_OF_SPEECH_ALIASES = {
    "adj": "adjective",
    "adv": "adverb",
    "conj": "conjunction",
    "det": "determiner",
    "n": "noun",
    "prep": "preposition",
    "pron": "pronoun",
    "v": "verb",
}
PARTS_OF_SPEECH = {
    "adjective",
    "adverb",
    "conjunction",
    "determiner",
    "interjection",
    "noun",
    "preposition",
    "pronoun",
    "verb",
    "word",
}


class GeneratedWordFamilyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=40)


class GeneratedWordContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meaning: str = Field(min_length=1, max_length=300)
    ipa: Optional[str] = Field(max_length=255)
    part_of_speech: str = Field(min_length=1, max_length=40)
    examples: List[str] = Field(min_length=2, max_length=3)
    word_family: List[GeneratedWordFamilyItem] = Field(min_length=1, max_length=6)
    chunked_form: str = Field(min_length=1, max_length=255)
    mnemonic: str = Field(min_length=1, max_length=240)


@dataclass(frozen=True)
class ContentGenerationResult:
    data: Dict[str, Any]
    source: str
    warnings: List[str]
    fallback_reason: Optional[str] = None


def structured_content_schema() -> Dict[str, Any]:
    return GeneratedWordContent.model_json_schema()


def normalize_part_of_speech(value: Optional[str]) -> str:
    normalized = (value or "word").strip().lower().rstrip(".")
    normalized = PART_OF_SPEECH_ALIASES.get(normalized, normalized)
    return normalized if normalized in PARTS_OF_SPEECH else "word"


def contains_target(example: str, target: str) -> bool:
    pattern = rf"(?<![A-Za-z]){re.escape(target.strip())}(?![A-Za-z])"
    return bool(re.search(pattern, example, flags=re.IGNORECASE))


def normalize_letters(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalpha())


def _clean_family(target: str, values: List[GeneratedWordFamilyItem]) -> List[Dict[str, str]]:
    target_normalized = target.strip().lower()
    cleaned: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in values:
        term = item.term.strip().lower()
        if not term or term in seen or not term.replace("-", "").replace("'", "").isalpha():
            continue
        if term != target_normalized and SequenceMatcher(None, target_normalized, term).ratio() < 0.45:
            continue
        raw_label = item.label.strip().lower()
        label = raw_label if raw_label in {"base", "related"} else normalize_part_of_speech(raw_label)
        cleaned.append({"term": term, "label": label if label != "word" else "related"})
        seen.add(term)
    if target_normalized not in seen:
        cleaned.insert(0, {"term": target_normalized, "label": "base"})
    return cleaned[:6]


def validate_generated_content(target: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        content = GeneratedWordContent.model_validate(payload)
    except ValidationError as err:
        raise ValueError("AI response did not match the required content structure.") from err

    examples = [example.strip() for example in content.examples]
    if any(len(example.split()) > 24 or len(example) > 180 for example in examples):
        raise ValueError("AI examples were too complex for a spelling learner.")
    if any(not contains_target(example, target) for example in examples):
        raise ValueError("Every AI example must contain the target word.")
    if normalize_letters(content.chunked_form) != normalize_letters(target):
        raise ValueError("AI chunking did not reproduce the target word.")

    family = _clean_family(target, content.word_family)
    if not family:
        raise ValueError("AI response did not contain a valid word family.")

    return {
        "meaning": content.meaning.strip(),
        "ipa": content.ipa.strip() if content.ipa else None,
        "part_of_speech": normalize_part_of_speech(content.part_of_speech),
        "examples": examples,
        "word_family": family,
        "chunked_form": content.chunked_form.strip(),
        "mnemonic": content.mnemonic.strip(),
    }
