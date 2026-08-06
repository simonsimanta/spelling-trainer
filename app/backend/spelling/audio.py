from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import requests
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend import models, schemas
from app.backend.db import SessionLocal


DEFAULT_TTS_VOICE = "cedar"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_AUDIO_FORMAT = "mp3"
DEFAULT_LOCALE = "en-GB"
PRONUNCIATION_VERSION = "en-gb-v2"
PASSAGE_RETENTION_DAYS = 30
PASSAGE_CACHE_MAX_BYTES = 512 * 1024 * 1024
LOCK_STALE_SECONDS = 90
LOCK_WAIT_SECONDS = 75
STREAM_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class AudioSpec:
    text: str
    asset_kind: str
    mode: str
    voice: str
    model: str
    audio_format: str
    locale: str
    instructions: str
    pronunciation_version: str = PRONUNCIATION_VERSION
    word_id: int | None = None
    dictation_text_id: int | None = None
    session_item_id: int | None = None
    segment_index: int | None = None

    @property
    def fingerprint(self) -> str:
        return audio_fingerprint(
            self.text,
            asset_kind=self.asset_kind,
            mode=self.mode,
            voice=self.voice,
            model=self.model,
            audio_format=self.audio_format,
            locale=self.locale,
            instructions=self.instructions,
            pronunciation_version=self.pronunciation_version,
        )


def audio_cache_dir() -> Path:
    cache_dir = Path(__file__).resolve().parents[3] / "data" / "spelling_audio"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_audio_variant(voice: str, model: str) -> tuple[str, str]:
    return (
        voice.strip().lower() or DEFAULT_TTS_VOICE,
        model.strip().lower() or DEFAULT_TTS_MODEL,
    )


def _supports_instructions(model: str) -> bool:
    return model.strip().lower() not in {"tts-1", "tts-1-hd"}


def pronunciation_instructions(
    text: str,
    word: models.SpellingWord | None = None,
    mode: str = "word",
) -> str:
    if mode == "dictation" or " " in _normalize_text(text):
        return (
            "Read the text exactly once in a clear, neutral British English accent at a measured "
            "learner pace. Keep natural rhythm and punctuation. Do not add commentary."
        )

    guidance: list[str] = []
    if word and word.phonetic_hint:
        guidance.append(f"Pronunciation hint: {word.phonetic_hint.strip()}.")
    if word and word.ipa:
        guidance.append(f"IPA: {word.ipa.strip()}.")
    pronunciation = " ".join(guidance)
    return (
        "Pronounce the word clearly once in a neutral British English accent at a measured learner "
        f"pace. {pronunciation} Do not spell it aloud or add commentary."
    ).strip()


def audio_fingerprint(
    text: str,
    *,
    asset_kind: str = "word",
    mode: str = "word",
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    locale: str = DEFAULT_LOCALE,
    instructions: str = "",
    pronunciation_version: str = PRONUNCIATION_VERSION,
) -> str:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    active_instructions = instructions.strip() if _supports_instructions(normalized_model) else ""
    payload = {
        "text": _normalize_text(text),
        "asset_kind": asset_kind.strip().lower(),
        "mode": mode.strip().lower(),
        "voice": normalized_voice,
        "model": normalized_model,
        "format": audio_format.strip().lower(),
        "locale": locale.strip() or DEFAULT_LOCALE,
        "instructions": active_instructions,
        "pronunciation_version": pronunciation_version.strip(),
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def audio_cache_path(
    text: str,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    instructions: str = "",
    *,
    asset_kind: str = "word",
    mode: str = "word",
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    locale: str = DEFAULT_LOCALE,
    pronunciation_version: str = PRONUNCIATION_VERSION,
) -> Path:
    digest = audio_fingerprint(
        text,
        asset_kind=asset_kind,
        mode=mode,
        voice=voice,
        model=model,
        audio_format=audio_format,
        locale=locale,
        instructions=instructions,
        pronunciation_version=pronunciation_version,
    )
    return audio_cache_dir() / f"{digest}.{audio_format.strip().lower()}"


def _tts_payload(spec: AudioSpec) -> dict[str, str]:
    payload = {
        "model": spec.model,
        "voice": spec.voice,
        "input": spec.text,
        "response_format": spec.audio_format,
    }
    if spec.instructions and _supports_instructions(spec.model):
        payload["instructions"] = spec.instructions
    return payload


def _api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Audio generation is unavailable because the OpenAI API key is not configured.",
        )
    return api_key


def _raise_for_tts_status(status_code: int) -> None:
    if status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Audio generation failed because the OpenAI API key is invalid.",
        )
    if status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="OpenAI rejected audio generation because the quota or rate limit was reached.",
        )
    if status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="OpenAI audio generation is temporarily unavailable. Try again later.",
        )


def _spec(
    text: str,
    *,
    asset_kind: str,
    mode: str,
    voice: str,
    model: str,
    word: models.SpellingWord | None = None,
    word_id: int | None = None,
    dictation_text_id: int | None = None,
    session_item_id: int | None = None,
    segment_index: int | None = None,
    locale: str = DEFAULT_LOCALE,
) -> AudioSpec:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    instructions = pronunciation_instructions(text, word, mode)
    if not _supports_instructions(normalized_model):
        instructions = ""
    return AudioSpec(
        text=_normalize_text(text),
        asset_kind=asset_kind,
        mode=mode,
        voice=normalized_voice,
        model=normalized_model,
        audio_format=DEFAULT_AUDIO_FORMAT,
        locale=locale or DEFAULT_LOCALE,
        instructions=instructions,
        word_id=word_id,
        dictation_text_id=dictation_text_id,
        session_item_id=session_item_id,
        segment_index=segment_index,
    )


def generate_tts_audio(
    text: str,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    instructions: str = "",
) -> bytes:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    spec = AudioSpec(
        text=_normalize_text(text),
        asset_kind="legacy",
        mode="word",
        voice=normalized_voice,
        model=normalized_model,
        audio_format=DEFAULT_AUDIO_FORMAT,
        locale=DEFAULT_LOCALE,
        instructions=instructions.strip() if _supports_instructions(normalized_model) else "",
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
            json=_tts_payload(spec),
            timeout=30,
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Audio generation could not reach OpenAI. Check the network connection and try again.",
        )
    _raise_for_tts_status(response.status_code)
    return response.content


def _open_tts_stream(spec: AudioSpec):
    try:
        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
            json=_tts_payload(spec),
            timeout=(10, 75),
            stream=True,
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Audio generation could not reach OpenAI. Check the network connection and try again.",
        )
    try:
        _raise_for_tts_status(response.status_code)
    except HTTPException:
        response.close()
        raise
    return response


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_audio_asset(db: Session, spec: AudioSpec) -> models.SpellingAudioAsset:
    fingerprint = spec.fingerprint
    asset = db.scalar(
        select(models.SpellingAudioAsset).where(
            models.SpellingAudioAsset.fingerprint == fingerprint
        )
    )
    if asset:
        if asset.word_id is None and spec.word_id is not None:
            asset.word_id = spec.word_id
        if asset.dictation_text_id is None and spec.dictation_text_id is not None:
            asset.dictation_text_id = spec.dictation_text_id
        if asset.session_item_id is None and spec.session_item_id is not None:
            asset.session_item_id = spec.session_item_id
        if asset.status == "expired":
            asset.status = "pending"
            asset.updated_at = datetime.utcnow()
        return asset

    asset = models.SpellingAudioAsset(
        fingerprint=fingerprint,
        asset_kind=spec.asset_kind,
        word_id=spec.word_id,
        dictation_text_id=spec.dictation_text_id,
        session_item_id=spec.session_item_id,
        segment_index=spec.segment_index,
        text_hash=_sha256(spec.text),
        locale=spec.locale,
        mode=spec.mode,
        voice=spec.voice,
        model=spec.model,
        audio_format=spec.audio_format,
        instructions=spec.instructions,
        instructions_hash=_sha256(spec.instructions),
        pronunciation_version=spec.pronunciation_version,
        status="pending",
        file_path=f"{fingerprint}.{spec.audio_format}",
    )
    try:
        with db.begin_nested():
            db.add(asset)
            db.flush()
    except IntegrityError:
        asset = db.scalar(
            select(models.SpellingAudioAsset).where(
                models.SpellingAudioAsset.fingerprint == fingerprint
            )
        )
        if asset is None:
            raise
    return asset


def _word_spec(
    word: models.SpellingWord,
    *,
    voice: str,
    model: str,
    session_item_id: int | None = None,
) -> AudioSpec:
    return _spec(
        word.term,
        asset_kind="word",
        mode="word",
        voice=voice,
        model=model,
        word=word,
        word_id=word.id,
        session_item_id=session_item_id,
    )


def session_item_audio_assets(
    db: Session,
    item: models.SpellingSessionItem,
    *,
    voice: str,
    model: str,
) -> tuple[models.SpellingAudioAsset, list[models.SpellingAudioAsset]]:
    from app.backend.spelling import dictation_grading

    if item.dictation_text_id and item.dictation_text:
        text = item.dictation_text
        complete = ensure_audio_asset(
            db,
            _spec(
                text.content,
                asset_kind="dictation_complete",
                mode="dictation",
                voice=voice,
                model=model,
                dictation_text_id=text.id,
                session_item_id=item.id,
                locale=text.locale,
            ),
        )
        segment_assets = [
            ensure_audio_asset(
                db,
                _spec(
                    segment,
                    asset_kind="dictation_segment",
                    mode="dictation",
                    voice=voice,
                    model=model,
                    dictation_text_id=text.id,
                    session_item_id=item.id,
                    segment_index=index,
                    locale=text.locale,
                ),
            )
            for index, segment in enumerate(dictation_grading.split_sentence_segments(text.content))
        ]
        return complete, segment_assets

    if item.session and item.session.session_type == models.SpellingSessionType.dictation:
        complete = ensure_audio_asset(
            db,
            _spec(
                item.prompt_text,
                asset_kind="dictation_complete",
                mode="dictation",
                voice=voice,
                model=model,
                word=item.word,
                word_id=item.word_id,
                session_item_id=item.id,
            ),
        )
        return complete, []

    if item.word:
        return ensure_audio_asset(
            db,
            _word_spec(item.word, voice=voice, model=model, session_item_id=item.id),
        ), []

    return ensure_audio_asset(
        db,
        _spec(
            item.prompt_text,
            asset_kind="session_prompt",
            mode="word",
            voice=voice,
            model=model,
            session_item_id=item.id,
        ),
    ), []


def asset_url(asset: models.SpellingAudioAsset, *, force: bool = False) -> str:
    path = f"/spelling/audio/assets/{asset.id}"
    return f"{path}?force=true" if force else path


def asset_read(asset: models.SpellingAudioAsset, *, force: bool = False) -> schemas.SpellingAudioAssetRead:
    path = _asset_file(asset)
    ready = asset.status == "ready" and path.exists()
    return schemas.SpellingAudioAssetRead(
        asset_id=asset.id,
        url=asset_url(asset, force=force),
        status=asset.status,
        kind=asset.asset_kind,
        ready=ready,
    )


def resolve_audio_asset(
    db: Session,
    payload: schemas.SpellingAudioAssetResolveRequest,
    *,
    voice: str,
    model: str,
) -> schemas.SpellingAudioAssetRead:
    if (payload.word_id is None) == (payload.session_item_id is None):
        raise ValueError("Provide exactly one word_id or session_item_id.")
    if payload.word_id is not None:
        if payload.segment_index is not None:
            raise ValueError("Segments are available only for dictation session items.")
        word = db.get(models.SpellingWord, payload.word_id)
        if not word:
            raise LookupError("Word not found.")
        asset = ensure_audio_asset(db, _word_spec(word, voice=voice, model=model))
    else:
        item = db.get(models.SpellingSessionItem, payload.session_item_id)
        if not item:
            raise LookupError("Session item not found.")
        complete, segments = session_item_audio_assets(db, item, voice=voice, model=model)
        if payload.segment_index is None:
            asset = complete
        elif payload.segment_index >= len(segments):
            raise LookupError("Dictation segment not found.")
        else:
            asset = segments[payload.segment_index]
    db.commit()
    db.refresh(asset)
    return asset_read(asset, force=payload.force)


def _asset_file(asset: models.SpellingAudioAsset) -> Path:
    filename = Path(asset.file_path or f"{asset.fingerprint}.{asset.audio_format}").name
    return audio_cache_dir() / filename


def _spoken_text_for_asset(db: Session, asset: models.SpellingAudioAsset) -> str:
    from app.backend.spelling import dictation_grading

    if asset.asset_kind == "word" and asset.word_id:
        word = db.get(models.SpellingWord, asset.word_id)
        if word:
            return _normalize_text(word.term)
    if asset.dictation_text_id:
        text = db.get(models.SpellingDictationText, asset.dictation_text_id)
        if text:
            if asset.asset_kind == "dictation_segment":
                segments = dictation_grading.split_sentence_segments(text.content)
                if asset.segment_index is None or asset.segment_index >= len(segments):
                    raise HTTPException(status_code=409, detail="The dictation segment has changed.")
                return _normalize_text(segments[asset.segment_index])
            return _normalize_text(text.content)
    if asset.session_item_id:
        item = db.get(models.SpellingSessionItem, asset.session_item_id)
        if item:
            return _normalize_text(item.word.term if asset.asset_kind == "word" and item.word else item.prompt_text)
    raise HTTPException(status_code=404, detail="The source for this audio asset no longer exists.")


def _spec_for_asset(db: Session, asset: models.SpellingAudioAsset) -> AudioSpec:
    text = _spoken_text_for_asset(db, asset)
    if _sha256(text) != asset.text_hash:
        raise HTTPException(
            status_code=409,
            detail="This audio asset is stale. Refresh the exercise to resolve a new asset.",
        )
    return AudioSpec(
        text=text,
        asset_kind=asset.asset_kind,
        mode=asset.mode,
        voice=asset.voice,
        model=asset.model,
        audio_format=asset.audio_format,
        locale=asset.locale,
        instructions=asset.instructions,
        pronunciation_version=asset.pronunciation_version,
        word_id=asset.word_id,
        dictation_text_id=asset.dictation_text_id,
        session_item_id=asset.session_item_id,
        segment_index=asset.segment_index,
    )


def _lock_path(path: Path) -> Path:
    return path.with_suffix(f"{path.suffix}.lock")


def _acquire_lock(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists() and time.time() - lock_path.stat().st_mtime > LOCK_STALE_SECONDS:
        lock_path.unlink(missing_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        handle.write(str(os.getpid()))
    return True


def _wait_for_file(path: Path, lock_path: Path, timeout: float = LOCK_WAIT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        if not lock_path.exists():
            return False
        if time.time() - lock_path.stat().st_mtime > LOCK_STALE_SECONDS:
            lock_path.unlink(missing_ok=True)
            return False
        time.sleep(0.05)
    return path.exists()


def _mark_asset_ready(asset_id: int, path: Path, byte_size: int) -> None:
    with SessionLocal() as db:
        asset = db.get(models.SpellingAudioAsset, asset_id)
        if not asset:
            return
        now = datetime.utcnow()
        asset.status = "ready"
        asset.file_path = path.name
        asset.byte_size = byte_size
        asset.generated_at = now
        asset.last_accessed_at = now
        asset.access_count += 1
        asset.error = None
        asset.updated_at = now
        db.commit()


def _mark_asset_failed(asset_id: int, detail: str) -> None:
    with SessionLocal() as db:
        asset = db.get(models.SpellingAudioAsset, asset_id)
        if not asset:
            return
        asset.status = "failed"
        asset.error = detail[:1000]
        asset.updated_at = datetime.utcnow()
        db.commit()


def _touch_asset(db: Session, asset: models.SpellingAudioAsset, path: Path) -> None:
    now = datetime.utcnow()
    asset.status = "ready"
    asset.file_path = path.name
    asset.byte_size = path.stat().st_size
    asset.last_accessed_at = now
    asset.access_count += 1
    asset.error = None
    asset.updated_at = now
    db.commit()


def _asset_headers(asset: models.SpellingAudioAsset, cache_status: str, force: bool) -> dict[str, str]:
    return {
        "Cache-Control": "no-store" if force else "private, max-age=31536000, immutable",
        "ETag": f'"{asset.fingerprint}"',
        "Accept-Ranges": "bytes",
        "X-Audio-Asset": str(asset.id),
        "X-Audio-Cache": cache_status,
    }


def _stream_and_cache(
    asset_id: int,
    spec: AudioSpec,
    upstream,
    path: Path,
    lock_path: Path,
) -> Iterator[bytes]:
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    byte_size = 0
    try:
        with temporary.open("wb") as handle:
            for chunk in upstream.iter_content(chunk_size=STREAM_CHUNK_BYTES):
                if not chunk:
                    continue
                handle.write(chunk)
                byte_size += len(chunk)
                yield chunk
            if byte_size == 0:
                raise RuntimeError("OpenAI returned an empty audio response.")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _mark_asset_ready(asset_id, path, byte_size)
    except BaseException as error:
        _mark_asset_failed(asset_id, str(error) or "Audio streaming was interrupted.")
        raise
    finally:
        upstream.close()
        temporary.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


def get_audio_asset_response(
    db: Session,
    asset_id: int,
    *,
    force: bool = False,
) -> Response:
    asset = db.get(models.SpellingAudioAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Audio asset not found.")
    path = _asset_file(asset)
    if path.exists() and not force:
        _touch_asset(db, asset, path)
        return FileResponse(
            path,
            media_type="audio/mpeg",
            headers=_asset_headers(asset, "hit", force=False),
        )

    spec = _spec_for_asset(db, asset)
    lock_path = _lock_path(path)
    if not _acquire_lock(lock_path):
        if _wait_for_file(path, lock_path):
            db.refresh(asset)
            _touch_asset(db, asset, path)
            return FileResponse(
                path,
                media_type="audio/mpeg",
                headers=_asset_headers(asset, "shared", force=force),
            )
        if not _acquire_lock(lock_path):
            raise HTTPException(status_code=503, detail="Audio generation is already in progress.")

    asset.status = "generating"
    asset.error = None
    asset.updated_at = datetime.utcnow()
    db.commit()
    try:
        upstream = _open_tts_stream(spec)
    except HTTPException as error:
        lock_path.unlink(missing_ok=True)
        asset.status = "failed"
        asset.error = str(error.detail)
        asset.updated_at = datetime.utcnow()
        db.commit()
        raise

    return StreamingResponse(
        _stream_and_cache(asset.id, spec, upstream, path, lock_path),
        media_type="audio/mpeg",
        headers=_asset_headers(asset, "miss", force=force),
    )


def _active_session_items(db: Session, session_limit: int = 10) -> list[models.SpellingSessionItem]:
    session_ids = list(
        db.scalars(
            select(models.SpellingSession.id)
            .where(models.SpellingSession.is_completed.is_(False))
            .order_by(models.SpellingSession.created_at.desc())
            .limit(session_limit)
        ).all()
    )
    if not session_ids:
        return []
    return list(
        db.scalars(
            select(models.SpellingSessionItem)
            .where(models.SpellingSessionItem.session_id.in_(session_ids))
            .where(models.SpellingSessionItem.status == models.SpellingSessionItemStatus.pending)
            .order_by(models.SpellingSessionItem.session_id.desc(), models.SpellingSessionItem.order_index)
        ).all()
    )


def active_audio_assets(
    db: Session,
    *,
    voice: str,
    model: str,
) -> list[models.SpellingAudioAsset]:
    assets: dict[int, models.SpellingAudioAsset] = {}
    for item in _active_session_items(db):
        complete, segments = session_item_audio_assets(db, item, voice=voice, model=model)
        for asset in [complete, *segments]:
            assets[asset.id] = asset

    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    recent = db.scalars(
        select(models.SpellingAudioAsset).where(
            models.SpellingAudioAsset.voice == _normalize_audio_variant(voice, model)[0],
            models.SpellingAudioAsset.model == _normalize_audio_variant(voice, model)[1],
            models.SpellingAudioAsset.created_at >= recent_cutoff,
            models.SpellingAudioAsset.status.in_(["pending", "failed"]),
        )
    ).all()
    for asset in recent:
        assets[asset.id] = asset

    for asset in assets.values():
        path = _asset_file(asset)
        if path.exists() and asset.status != "ready":
            asset.status = "ready"
            asset.file_path = path.name
            asset.byte_size = path.stat().st_size
            asset.error = None
        elif asset.status == "ready" and not path.exists():
            asset.status = "pending"
            asset.file_path = path.name
            asset.byte_size = 0
    db.commit()
    return list(assets.values())


def bulk_audio_status(
    db: Session,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
) -> schemas.SpellingAudioBulkStatus:
    normalized_voice, normalized_model = _normalize_audio_variant(voice, model)
    assets = active_audio_assets(db, voice=normalized_voice, model=normalized_model)
    generated = len([asset for asset in assets if asset.status == "ready" and _asset_file(asset).exists()])
    failed = len([asset for asset in assets if asset.status == "failed"])
    return schemas.SpellingAudioBulkStatus(
        total_words=len(assets),
        generated=generated,
        pending=max(len(assets) - generated - failed, 0),
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
    status = bulk_audio_status(db, voice=voice, model=model)
    will_process = min(limit, status.pending + status.failed)
    return schemas.BulkGeneratePreview(
        limit=limit,
        total_words=status.total_words,
        generated=status.generated,
        pending=status.pending,
        failed=status.failed,
        will_process=will_process,
        estimated_api_calls=will_process if os.getenv("OPENAI_API_KEY", "").strip() else 0,
        model=status.model,
        voice=status.voice,
    )


def _generate_asset_now(db: Session, asset: models.SpellingAudioAsset) -> str:
    path = _asset_file(asset)
    if path.exists():
        _touch_asset(db, asset, path)
        return "cached"
    lock_path = _lock_path(path)
    if not _acquire_lock(lock_path):
        if _wait_for_file(path, lock_path):
            _touch_asset(db, asset, path)
            return "cached"
        if not _acquire_lock(lock_path):
            raise RuntimeError("Audio generation is already in progress.")
    try:
        spec = _spec_for_asset(db, asset)
        asset.status = "generating"
        asset.updated_at = datetime.utcnow()
        db.commit()
        content = generate_tts_audio(
            spec.text,
            voice=spec.voice,
            model=spec.model,
            instructions=spec.instructions,
        )
        _atomic_write(path, content)
        now = datetime.utcnow()
        asset.status = "ready"
        asset.file_path = path.name
        asset.byte_size = len(content)
        asset.generated_at = now
        asset.last_accessed_at = now
        asset.access_count += 1
        asset.error = None
        asset.updated_at = now
        db.commit()
        return "generated"
    finally:
        lock_path.unlink(missing_ok=True)


def bulk_generate_audio(
    db: Session, payload: schemas.SpellingAudioBulkGenerateRequest
) -> schemas.SpellingAudioBulkGenerateResult:
    generated = 0
    cached = 0
    failed = 0
    voice, model = _normalize_audio_variant(payload.voice, payload.model)
    candidates = [
        asset
        for asset in active_audio_assets(db, voice=voice, model=model)
        if asset.status != "ready" or not _asset_file(asset).exists()
    ][: payload.limit]
    for asset in candidates:
        try:
            result = _generate_asset_now(db, asset)
            if result == "generated":
                generated += 1
            else:
                cached += 1
        except HTTPException as error:
            asset.status = "failed"
            asset.error = str(error.detail)
            asset.updated_at = datetime.utcnow()
            db.commit()
            failed += 1
        except Exception as error:
            asset.status = "failed"
            asset.error = str(error)
            asset.updated_at = datetime.utcnow()
            db.commit()
            failed += 1
    status = bulk_audio_status(db, voice=voice, model=model)
    return schemas.SpellingAudioBulkGenerateResult(
        requested_limit=payload.limit,
        generated=generated,
        cached=cached,
        failed=failed,
        remaining=status.pending + status.failed,
        voice=voice,
        model=model,
    )


def cleanup_audio_cache(
    db: Session,
    *,
    now: datetime | None = None,
    inactive_days: int = PASSAGE_RETENTION_DAYS,
    max_passage_bytes: int = PASSAGE_CACHE_MAX_BYTES,
) -> schemas.SpellingAudioCleanupResult:
    current = now or datetime.utcnow()
    cutoff = current - timedelta(days=inactive_days)
    expired = 0
    evicted = 0
    bytes_removed = 0
    reusable = list(
        db.scalars(
            select(models.SpellingAudioAsset).where(
                models.SpellingAudioAsset.asset_kind != "word",
                models.SpellingAudioAsset.status == "ready",
            )
        ).all()
    )

    def remove_asset(asset: models.SpellingAudioAsset, reason: str) -> int:
        path = _asset_file(asset)
        size = path.stat().st_size if path.exists() else asset.byte_size
        path.unlink(missing_ok=True)
        asset.status = "expired"
        asset.file_path = None
        asset.byte_size = 0
        asset.error = reason
        asset.updated_at = current
        return size

    retained: list[models.SpellingAudioAsset] = []
    for asset in reusable:
        activity_at = asset.last_accessed_at or asset.generated_at or asset.created_at
        if activity_at < cutoff:
            bytes_removed += remove_asset(asset, "Expired after 30 inactive days.")
            expired += 1
        else:
            retained.append(asset)

    retained_bytes = sum(
        _asset_file(asset).stat().st_size if _asset_file(asset).exists() else asset.byte_size
        for asset in retained
    )
    if retained_bytes > max_passage_bytes:
        retained.sort(
            key=lambda asset: (
                asset.access_count,
                asset.last_accessed_at or asset.generated_at or asset.created_at,
            )
        )
        for asset in retained:
            if retained_bytes <= max_passage_bytes:
                break
            removed = remove_asset(asset, "Evicted by the 512 MiB passage cache limit.")
            retained_bytes = max(0, retained_bytes - removed)
            bytes_removed += removed
            evicted += 1

    for temporary in audio_cache_dir().glob(".*.tmp"):
        if current.timestamp() - temporary.stat().st_mtime > LOCK_STALE_SECONDS:
            temporary.unlink(missing_ok=True)
    for lock in audio_cache_dir().glob("*.lock"):
        if current.timestamp() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
            lock.unlink(missing_ok=True)

    db.commit()
    return schemas.SpellingAudioCleanupResult(
        expired=expired,
        evicted=evicted,
        bytes_removed=bytes_removed,
        retained_bytes=retained_bytes,
    )


# Compatibility endpoints use the same complete fingerprint and atomic cache writes.
# New application flows resolve an opaque audio asset instead of sending text here.
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
        normalized = _normalize_text(text)
        if not normalized:
            continue
        mode = "dictation" if " " in normalized else "word"
        instructions = pronunciation_instructions(normalized, mode=mode)
        path = audio_cache_path(
            normalized,
            voice=normalized_voice,
            model=normalized_model,
            instructions=instructions,
            asset_kind="legacy",
            mode=mode,
        )
        if path.exists():
            cached += 1
            continue
        _atomic_write(
            path,
            generate_tts_audio(
                normalized,
                voice=normalized_voice,
                model=normalized_model,
                instructions=instructions,
            ),
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
    mode = "dictation" if " " in _normalize_text(text) else "word"
    path = audio_cache_path(
        text,
        voice=normalized_voice,
        model=normalized_model,
        instructions=instructions,
        asset_kind="legacy",
        mode=mode,
    )
    if path.exists() and not force:
        return FileResponse(
            path,
            media_type="audio/mpeg",
            headers={"X-Audio-Cache": "hit", "Accept-Ranges": "bytes"},
        )
    content = generate_tts_audio(
        text,
        voice=normalized_voice,
        model=normalized_model,
        instructions=instructions,
    )
    _atomic_write(path, content)
    return Response(
        content=content,
        media_type="audio/mpeg",
        headers={"X-Audio-Cache": "miss", "Accept-Ranges": "bytes"},
    )
