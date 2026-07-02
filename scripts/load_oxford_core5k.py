#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Set, Tuple

from dotenv import load_dotenv
from pypdf import PdfReader
from sqlalchemy import func, select

from app.backend import models, repository, schemas
from app.backend.db import SessionLocal

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


def normalize_term(term: str) -> str:
    cleaned = term.lower().strip("-'")
    cleaned = re.sub(r"[^a-z\-']", "", cleaned)
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.strip("-")
    if cleaned.endswith("-"):
        cleaned = cleaned[:-1]
    return cleaned


def extract_terms_from_pdf(pdf_path: Path) -> List[str]:
    reader = PdfReader(str(pdf_path))
    terms: List[str] = []
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


def unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def source_level_from_name(source_name: str) -> str:
    if source_name == "oxford_3000":
        return "core_3000"
    if source_name == "oxford_5000":
        return "core_5000"
    return "core_5k"


def ingest_source(
    source_name: str,
    pdf_path: Path,
    dry_run: bool,
    db: "Session",  # type: ignore[name-defined]
) -> Tuple[Dict[str, int], Set[str]]:
    extracted = extract_terms_from_pdf(pdf_path)
    unique_terms = unique_preserve_order(extracted)

    stats = {
        "source_terms": len(extracted),
        "unique_terms": len(unique_terms),
        "created": 0,
        "updated": 0,
    }

    COMMIT_BATCH = 200

    for rank, term in enumerate(unique_terms, start=1):
        if dry_run:
            stats["created"] += 1
            continue

        existing = db.scalar(select(models.SpellingWord).where(models.SpellingWord.term == term))
        created = False
        if not existing:
            created_word = repository.create_spelling_word(
                db,
                schemas.SpellingWordCreate(term=term, level="core5k", source="oxford"),
            )
            existing = created_word
            created = True

        repository.upsert_spelling_word_source(
            db=db,
            word_id=existing.id,
            source_name=source_name,
            source_level=source_level_from_name(source_name),
            list_rank=rank,
        )

        source_values = set((existing.source_list or "").split(",")) if existing.source_list else set()
        source_values = {item.strip() for item in source_values if item and item.strip()}
        source_values.add(source_name)
        existing.source_list = ",".join(sorted(source_values))

        if existing.level not in {"personal", "daily", "confusion"}:
            existing.level = "core5k"

        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1

        if rank % COMMIT_BATCH == 0:
            db.commit()

    if not dry_run:
        db.commit()

    return stats, set(unique_terms)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Oxford 3000/5000 words into Core 5K mode")
    parser.add_argument("--data-dir", default="data", help="Data directory containing Oxford PDFs")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count without DB writes")
    args = parser.parse_args()

    load_dotenv()

    data_dir = Path(args.data_dir)
    pdf_3000 = data_dir / "The_Oxford_3000.pdf"
    pdf_5000 = data_dir / "The_Oxford_5000.pdf"

    if not pdf_3000.exists() or not pdf_5000.exists():
        raise SystemExit("Missing Oxford PDFs in data directory")

    db = None if args.dry_run else SessionLocal()
    try:
        stats_3000, terms_3000 = ingest_source("oxford_3000", pdf_3000, args.dry_run, db)
        stats_5000, terms_5000 = ingest_source("oxford_5000", pdf_5000, args.dry_run, db)

        overlap = len(terms_3000.intersection(terms_5000))
        total_unique_estimate = len(terms_3000.union(terms_5000))

        total_unique_db = 0
        if not args.dry_run and db is not None:
            try:
                total_unique_db = db.scalar(
                    select(func.count(func.distinct(models.SpellingWordSource.word_id))).where(
                        models.SpellingWordSource.source_name.in_(["oxford_3000", "oxford_5000"])
                    )
                ) or 0
            except Exception:
                total_unique_db = 0
    finally:
        if db is not None:
            db.close()

    print("Oxford ingestion complete")
    print(
        {
            "oxford_3000": stats_3000,
            "oxford_5000": stats_5000,
            "overlap": overlap,
            "total_unique_estimate": total_unique_estimate,
            "total_unique_db": total_unique_db,
            "dry_run": args.dry_run,
        }
    )


if __name__ == "__main__":
    main()
