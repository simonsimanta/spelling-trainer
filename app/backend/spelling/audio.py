from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

import requests
from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backend import models, schemas


OXFORD_SOURCE_NAMES = {"oxford_3000", "oxford_5000"}
DEFAULT_TTS_VOICE = "alloy"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"


def audio_cache_dir() -> Path:
    cache_dir = Path(__file__).resolve().parents[3] / "data" / "spelling_audio"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _normalize_audio_variant(voice: str, model: str) -> tuple[str, str]:
    return (
        voice.strip().lower() or DEFAULT_TTS_VOICE,
        model.strip().lower() or DEFAULT_TTS_MODEL,
    )


def _supports_instructions(model: str) -> bool:
    return model.strip().lower().startswith("gpt-4o-mini-tts")


def pronunciation_instructions(
    text: str,
    word: models.SpellingWord | None = None,
    mode: str = "word",
) -> str:
    target = word.term if word else text.strip()
    guidance: list[str] = []
    if word and word.phonetic_hint:
        guidance.append(f"Pronunciation hint: {word.phonetic_hint.strip()}.")
    if word and word.ipa:
        guidance.append(f"IPA: {word.ipa.strip()}.")
    pronunciation = " ".join(guidance)
    if mode == "dictation" or " " in text.strip():
        return (
            f"Read the sentence once at a measured learner pace. Clearly articulate the target "
            f"spelling word '{target}'. {pronunciation} Do not add commentary."
        ).strip()
    return (
        f"Pronounce the spelling word '{target}' clearly once in neutral English. "
        f"{pronunciation} Do not spell it aloud or add commentary."
    ).strip()


def audio_cache_path(
    text: str,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    instructions: str = "",
) -> Path:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    active_instructions = instructions.strip() if _supports_instructions(normalized_model) else ""
    cache_key = "\0".join(
        [text.strip().lower(), normalized_voice, normalized_model, active_instructions]
    )
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return audio_cache_dir() / f"{digest}.mp3"


def generate_tts_audio(
    text: str,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    instructions: str = "",
) -> bytes:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Audio generation is unavailable because the OpenAI API key is not configured.",
        )

    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    try:
        payload = {
            "model": normalized_model,
            "voice": normalized_voice,
            "input": text,
            "response_format": "mp3",
        }
        if instructions.strip() and _supports_instructions(normalized_model):
            payload["instructions"] = instructions.strip()
        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Audio generation could not reach OpenAI. Check the network connection and try again.",
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Audio generation failed because the OpenAI API key is invalid.",
        )
    if response.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="OpenAI rejected audio generation because the quota or rate limit was reached.",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="OpenAI audio generation is temporarily unavailable. Try again later.",
        )

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


def bulk_audio_status(
    db: Session,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
) -> schemas.SpellingAudioBulkStatus:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    words = _audio_target_words(db)
    failed_word_ids = set(
        db.scalars(
            select(models.SpellingAudioManifest.word_id).where(
                models.SpellingAudioManifest.voice == normalized_voice,
                models.SpellingAudioManifest.model == normalized_model,
                models.SpellingAudioManifest.status == "failed",
            )
        ).all()
    )
    generated = 0
    failed = 0
    for word in words:
        instructions = pronunciation_instructions(word.term, word)
        cache_exists = audio_cache_path(
            word.term,
            voice=normalized_voice,
            model=normalized_model,
            instructions=instructions,
        ).exists()
        if cache_exists:
            generated += 1
        elif word.id in failed_word_ids:
            failed += 1
    total_words = len(words)
    pending = max(total_words - generated - failed, 0)
    return schemas.SpellingAudioBulkStatus(
        total_words=total_words,
        generated=generated,
        pending=pending,
        failed=failed,
        voice=normalized_voice,
        model=normalized_model,
    )


def bulk_audio_preview(
    db: Session,
    limit: int,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
) -> schemas.BulkGeneratePreview:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    status = bulk_audio_status(db, voice=normalized_voice, model=normalized_model)
    will_process = min(limit, status.pending)
    return schemas.BulkGeneratePreview(
        limit=limit,
        total_words=status.total_words,
        generated=status.generated,
        pending=status.pending,
        failed=status.failed,
        will_process=will_process,
        estimated_api_calls=will_process if os.getenv("OPENAI_API_KEY", "").strip() else 0,
        model=normalized_model,
        voice=normalized_voice,
    )


def bulk_generate_audio(
    db: Session, payload: schemas.SpellingAudioBulkGenerateRequest
) -> schemas.SpellingAudioBulkGenerateResult:
    requested_limit = payload.limit
    generated = 0
    cached = 0
    failed = 0
    voice, model = _normalize_audio_variant(payload.voice, payload.model)

    candidates = _audio_target_words(db)
    processed = 0
    for word in candidates:
        if processed >= requested_limit:
            break
        manifest = _manifest_for(db, word, voice, model)
        instructions = pronunciation_instructions(word.term, word)
        cache_path = audio_cache_path(
            word.term,
            voice=voice,
            model=model,
            instructions=instructions,
        )

        if (
            manifest.status == "generated"
            and manifest.file_path == str(cache_path)
            and cache_path.exists()
        ):
            continue
        if cache_path.exists():
            manifest.status = "generated"
            manifest.file_path = str(cache_path)
            manifest.error = None
            manifest.generated_at = manifest.generated_at or datetime.utcnow()
            manifest.updated_at = datetime.utcnow()
            cached += 1
            processed += 1
            continue

        try:
            cache_path.write_bytes(
                generate_tts_audio(
                    word.term,
                    voice=voice,
                    model=model,
                    instructions=instructions,
                )
            )
            manifest.status = "generated"
            manifest.file_path = str(cache_path)
            manifest.error = None
            manifest.generated_at = datetime.utcnow()
            manifest.updated_at = datetime.utcnow()
            generated += 1
        except HTTPException as err:
            manifest.status = "failed"
            manifest.error = str(err.detail)
            manifest.updated_at = datetime.utcnow()
            failed += 1
        except Exception as err:
            manifest.status = "failed"
            manifest.error = str(err)
            manifest.updated_at = datetime.utcnow()
            failed += 1
        processed += 1

    db.commit()
    status = bulk_audio_status(db, voice=voice, model=model)
    return schemas.SpellingAudioBulkGenerateResult(
        requested_limit=requested_limit,
        generated=generated,
        cached=cached,
        failed=failed,
        remaining=status.pending,
        voice=voice,
        model=model,
    )


def preload_audio(
    payload: schemas.SpellingAudioPreloadRequest,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
) -> schemas.SpellingAudioPreloadResponse:
    requested = len(payload.texts)
    cached = 0
    generated = 0
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)

    for text in payload.texts:
        normalized = text.strip()
        if not normalized:
            continue
        instructions = pronunciation_instructions(normalized)
        cache_path = audio_cache_path(
            normalized,
            voice=normalized_voice,
            model=normalized_model,
            instructions=instructions,
        )
        if cache_path.exists():
            cached += 1
            continue
        cache_path.write_bytes(
            generate_tts_audio(
                normalized,
                voice=normalized_voice,
                model=normalized_model,
                instructions=instructions,
            )
        )
        generated += 1

    return schemas.SpellingAudioPreloadResponse(
        requested=requested,
        cached=cached,
        generated=generated,
        voice=normalized_voice,
        model=normalized_model,
    )


def get_audio_response(
    text: str,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    instructions: str = "",
    force: bool = False,
) -> Response:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    cache_path = audio_cache_path(
        text,
        voice=normalized_voice,
        model=normalized_model,
        instructions=instructions,
    )
    if cache_path.exists() and not force:
        return Response(
            content=cache_path.read_bytes(),
            media_type="audio/mpeg",
            headers={"X-Audio-Cache": "hit"},
        )

    audio_bytes = generate_tts_audio(
        text,
        voice=normalized_voice,
        model=normalized_model,
        instructions=instructions,
    )
    cache_path.write_bytes(audio_bytes)
    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"X-Audio-Cache": "miss"},
    )
