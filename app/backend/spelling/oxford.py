from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backend import models, schemas
from app.backend import repository


OXFORD_TARGET_WORDS = 5000
OXFORD_3000 = "oxford_3000"
OXFORD_5000 = "oxford_5000"
OXFORD_SOURCE_NAMES = {OXFORD_3000, OXFORD_5000}
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{1,}")
BLOCKED_TOKENS = {
    "oxford",
    "word",
    "list",
    "cefr",
    "american",
    "english",
    "british",
    "levels",
    "level",
    "guide",
    "copyright",
}


@dataclass(frozen=True)
class OxfordSourceTerm:
    term: str
    source_name: str
    source_level: str
    rank: int


def data_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data"


def source_paths() -> dict[str, Path]:
    base = data_dir()
    return {
        OXFORD_3000: base / "The_Oxford_3000.pdf",
        OXFORD_5000: base / "The_Oxford_5000.pdf",
    }


def sources_available() -> bool:
    return all(path.exists() for path in source_paths().values())


def normalize_term(term: str) -> str:
    cleaned = term.lower().strip("-'")
    cleaned = re.sub(r"[^a-z\-']", "", cleaned)
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.strip("-")
    if cleaned.endswith("-"):
        cleaned = cleaned[:-1]
    return cleaned


def extract_terms_from_pdf(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    terms: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for match in WORD_RE.findall(text):
            term = normalize_term(match)
            if len(term) < 2:
                continue
            if term in BLOCKED_TOKENS:
                continue
            if term.isdigit():
                continue
            if len(term) > 32:
                continue
            terms.append(term)
    return terms


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def source_level_from_name(source_name: str) -> str:
    if source_name == OXFORD_3000:
        return "core_3000"
    if source_name == OXFORD_5000:
        return "core_5000"
    return "core_5k"


def source_terms_by_word() -> tuple[list[str], dict[str, list[OxfordSourceTerm]]]:
    if not sources_available():
        return [], {}

    ordered_terms: list[str] = []
    seen: set[str] = set()
    source_map: dict[str, list[OxfordSourceTerm]] = {}

    for source_name, pdf_path in source_paths().items():
        source_terms = unique_preserve_order(extract_terms_from_pdf(pdf_path))
        for rank, term in enumerate(source_terms, start=1):
            source_map.setdefault(term, []).append(
                OxfordSourceTerm(
                    term=term,
                    source_name=source_name,
                    source_level=source_level_from_name(source_name),
                    rank=rank,
                )
            )
            if term in seen:
                continue
            seen.add(term)
            ordered_terms.append(term)

    return ordered_terms, source_map


def loaded_oxford_word_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(func.distinct(models.SpellingWordSource.word_id))).where(
                models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES))
            )
        )
        or 0
    )


def load_status(db: Session) -> schemas.OxfordLoadStatus:
    settings = repository.get_settings(db)
    loaded = loaded_oxford_word_count(db)
    return schemas.OxfordLoadStatus(
        target_words=OXFORD_TARGET_WORDS,
        loaded_words=loaded,
        remaining_words=max(OXFORD_TARGET_WORDS - loaded, 0),
        next_batch_size=settings.content_bulk_limit,
        source_available=sources_available(),
    )


def load_batch(db: Session, payload: schemas.OxfordLoadBatchRequest) -> schemas.OxfordLoadBatchResult:
    ordered_terms, source_map = source_terms_by_word()
    if not ordered_terms:
        raise ValueError("Oxford source PDFs are missing.")

    loaded_terms = set(
        db.scalars(
            select(models.SpellingWord.term)
            .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWord.id)
            .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        ).all()
    )

    created = 0
    updated = 0
    skipped = 0
    processed = 0

    for term in ordered_terms:
        if processed >= payload.limit:
            break
        if term in loaded_terms:
            skipped += 1
            continue

        word = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == term))
        if word is None:
            word = models.SpellingWord(
                term=term,
                level="core5k",
                source="oxford",
                mastery_state="new",
            )
            db.add(word)
            db.flush()
            created += 1
        else:
            word.level = "core5k"
            if word.source in {"seed", "manual"}:
                word.source = "oxford"
            updated += 1

        source_values = set((word.source_list or "").split(",")) if word.source_list else set()
        source_values = {value.strip() for value in source_values if value and value.strip()}
        for source_term in source_map.get(term, []):
            repository.upsert_spelling_word_source(
                db=db,
                word_id=word.id,
                source_name=source_term.source_name,
                source_level=source_term.source_level,
                list_rank=source_term.rank,
            )
            source_values.add(source_term.source_name)
            if word.frequency_rank is None or source_term.rank < word.frequency_rank:
                word.frequency_rank = source_term.rank
        word.source_list = ",".join(sorted(source_values))

        loaded_terms.add(term)
        processed += 1

    db.commit()
    loaded = loaded_oxford_word_count(db)
    return schemas.OxfordLoadBatchResult(
        requested_limit=payload.limit,
        created=created,
        updated=updated,
        skipped=skipped,
        loaded_words=loaded,
        remaining_words=max(OXFORD_TARGET_WORDS - loaded, 0),
    )
