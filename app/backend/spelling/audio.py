from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests
from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backend import models, schemas


OXFORD_SOURCE_NAMES = {"oxford_3000", "oxford_5000"}


def audio_cache_dir() -> Path:
    cache_dir = Path(__file__).resolve().parents[3] / "data" / "spelling_audio"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def audio_cache_path(text: str) -> Path:
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    return audio_cache_dir() / f"{digest}.mp3"


def generate_tts_audio(text: str, voice: str = "alloy", model: str = "gpt-4o-mini-tts") -> bytes:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    try:
        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "voice": voice,
                "input": text,
                "format": "mp3",
            },
            timeout=30,
        )
    except requests.RequestException as err:
        raise HTTPException(status_code=502, detail=f"TTS request failed: {err}")

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid OpenAI API key")
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="OpenAI quota exceeded")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="OpenAI TTS unavailable")

    return response.content


def _has_oxford_words(db: Session) -> bool:
    count = db.scalar(
        select(func.count(func.distinct(models.SpellingWordSource.word_id))).where(
            models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES))
        )
    ) or 0
    return count > 0


def _audio_target_words(db: Session, limit: int | None = None) -> list[models.SpellingWord]:
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


def _manifest_for(
    db: Session, word: models.SpellingWord, voice: str, model: str
) -> models.SpellingAudioManifest:
    manifest = db.scalar(
        select(models.SpellingAudioManifest).where(
            models.SpellingAudioManifest.word_id == word.id,
            models.SpellingAudioManifest.voice == voice,
            models.SpellingAudioManifest.model == model,
        )
    )
    if manifest:
        return manifest

    manifest = models.SpellingAudioManifest(
        word_id=word.id,
        term=word.term,
        voice=voice,
        model=model,
        status="pending",
    )
    db.add(manifest)
    db.flush()
    return manifest


def bulk_audio_status(db: Session) -> schemas.SpellingAudioBulkStatus:
    total_words = len(_audio_target_words(db))
    generated = db.scalar(
        select(func.count(func.distinct(models.SpellingAudioManifest.word_id)))
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingAudioManifest.word_id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .where(models.SpellingAudioManifest.status == "generated")
    ) or 0
    failed = db.scalar(
        select(func.count(func.distinct(models.SpellingAudioManifest.word_id)))
        .join(models.SpellingWordSource, models.SpellingWordSource.word_id == models.SpellingAudioManifest.word_id)
        .where(models.SpellingWordSource.source_name.in_(list(OXFORD_SOURCE_NAMES)))
        .where(models.SpellingAudioManifest.status == "failed")
    ) or 0
    pending = max(total_words - int(generated) - int(failed), 0)
    return schemas.SpellingAudioBulkStatus(
        total_words=total_words,
        generated=generated,
        pending=pending,
        failed=failed,
    )


def bulk_audio_preview(
    db: Session, limit: int, voice: str = "alloy", model: str = "gpt-4o-mini-tts"
) -> schemas.BulkGeneratePreview:
    status = bulk_audio_status(db)
    will_process = min(limit, status.pending)
    return schemas.BulkGeneratePreview(
        limit=limit,
        total_words=status.total_words,
        generated=status.generated,
        pending=status.pending,
        failed=status.failed,
        will_process=will_process,
        estimated_api_calls=will_process if os.getenv("OPENAI_API_KEY", "").strip() else 0,
        model=model,
        voice=voice,
    )


def bulk_generate_audio(
    db: Session, payload: schemas.SpellingAudioBulkGenerateRequest
) -> schemas.SpellingAudioBulkGenerateResult:
    requested_limit = payload.limit
    generated = 0
    cached = 0
    failed = 0

    candidates = _audio_target_words(db)
    processed = 0
    for word in candidates:
        if processed >= requested_limit:
            break
        manifest = _manifest_for(db, word, payload.voice, payload.model)
        cache_path = audio_cache_path(word.term)

        if manifest.status == "generated" and manifest.file_path and Path(manifest.file_path).exists():
            continue
        if cache_path.exists():
            manifest.status = "generated"
            manifest.file_path = str(cache_path)
            manifest.error = None
            cached += 1
            processed += 1
            continue

        try:
            cache_path.write_bytes(generate_tts_audio(word.term, voice=payload.voice, model=payload.model))
            manifest.status = "generated"
            manifest.file_path = str(cache_path)
            manifest.error = None
            generated += 1
        except HTTPException as err:
            manifest.status = "failed"
            manifest.error = str(err.detail)
            failed += 1
        except Exception as err:
            manifest.status = "failed"
            manifest.error = str(err)
            failed += 1
        processed += 1

    db.commit()
    status = bulk_audio_status(db)
    return schemas.SpellingAudioBulkGenerateResult(
        requested_limit=requested_limit,
        generated=generated,
        cached=cached,
        failed=failed,
        remaining=status.pending,
    )


def preload_audio(payload: schemas.SpellingAudioPreloadRequest) -> schemas.SpellingAudioPreloadResponse:
    requested = len(payload.texts)
    cached = 0
    generated = 0

    for text in payload.texts:
        normalized = text.strip()
        if not normalized:
            continue
        cache_path = audio_cache_path(normalized)
        if cache_path.exists():
            cached += 1
            continue
        cache_path.write_bytes(generate_tts_audio(normalized))
        generated += 1

    return schemas.SpellingAudioPreloadResponse(requested=requested, cached=cached, generated=generated)


def get_audio_response(text: str) -> Response:
    cache_path = audio_cache_path(text)
    if cache_path.exists():
        return Response(content=cache_path.read_bytes(), media_type="audio/mpeg")

    audio_bytes = generate_tts_audio(text)
    cache_path.write_bytes(audio_bytes)
    return Response(content=audio_bytes, media_type="audio/mpeg")
