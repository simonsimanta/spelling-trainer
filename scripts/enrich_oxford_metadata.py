#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
from sqlalchemy import select

from app.backend import models, repository
from app.backend.db import SessionLocal


def build_prompt(term: str) -> str:
    return (
        "Return strict JSON with keys short_meaning, example_sentence, ipa, part_of_speech for this English word. "
        "Keep short_meaning under 14 words. Keep example_sentence under 14 words. "
        f"Word: {term}."
    )


def parse_response_payload(data: Dict[str, Any]) -> Dict[str, Optional[str]]:
    output = data.get("output", [])
    texts = []
    for item in output:
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                texts.append(text)

    merged = "\n".join(texts).strip()
    if not merged:
        return {"short_meaning": None, "example_sentence": None, "ipa": None, "part_of_speech": None}

    start = merged.find("{")
    end = merged.rfind("}")
    if start >= 0 and end >= 0 and end > start:
        merged = merged[start : end + 1]

    try:
        parsed = json.loads(merged)
    except json.JSONDecodeError:
        return {"short_meaning": None, "example_sentence": None, "ipa": None, "part_of_speech": None}

    return {
        "short_meaning": parsed.get("short_meaning"),
        "example_sentence": parsed.get("example_sentence"),
        "ipa": parsed.get("ipa"),
        "part_of_speech": parsed.get("part_of_speech"),
    }


def call_openai_for_word(term: str, api_key: str, model: str) -> Dict[str, Optional[str]]:
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "input": build_prompt(term)},
        timeout=20,
    )
    if response.status_code >= 400:
        return {"short_meaning": None, "example_sentence": None, "ipa": None, "part_of_speech": None}
    return parse_response_payload(response.json())


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich Oxford words with meaning/example/ipa/part_of_speech")
    parser.add_argument("--limit", type=int, default=200, help="Max words to enrich in one run")
    parser.add_argument("--sleep-ms", type=int, default=200, help="Delay between requests")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")

    db = SessionLocal()
    try:
        words = db.scalars(
            select(models.SpellingWord)
            .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingWord.id)
            .where(models.SpellingWordSource.source_name.in_(["oxford_3000", "oxford_5000"]))
            .where(
                (models.SpellingWord.short_meaning.is_(None))
                | (models.SpellingWord.example_sentence.is_(None))
                | (models.SpellingWord.ipa.is_(None))
                | (models.SpellingWord.part_of_speech.is_(None))
            )
            .order_by(models.SpellingWord.id.asc())
            .limit(args.limit)
        ).all()

        updated = 0
        for word in words:
            enriched = call_openai_for_word(word.term, api_key=api_key, model=model)
            repository.enrich_spelling_word_metadata(
                db=db,
                word=word,
                short_meaning=enriched.get("short_meaning"),
                example_sentence=enriched.get("example_sentence"),
                ipa=enriched.get("ipa"),
                part_of_speech=enriched.get("part_of_speech"),
            )
            db.commit()
            updated += 1
            time.sleep(max(args.sleep_ms, 0) / 1000.0)

        print({"updated": updated, "requested_limit": args.limit})
    finally:
        db.close()


if __name__ == "__main__":
    main()
