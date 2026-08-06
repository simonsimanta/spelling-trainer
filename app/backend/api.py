import logging
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.backend import models, readiness, repository, schemas
from app.backend.db import get_db
from app.backend.spelling import (
    analytics,
    attempts,
    audio,
    dictation_texts,
    oxford,
    sessions,
    suggestions,
    words,
)


logger = logging.getLogger(__name__)
app = FastAPI(title="Spelling Trainer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(_request: Request, error: SQLAlchemyError) -> JSONResponse:
    logger.warning(
        "Database-backed request failed (%s). Check /readiness.",
        type(error).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unavailable. Open Settings for readiness details."},
    )


@app.on_event("startup")
def startup_seed() -> None:
    db = next(get_db())
    try:
        try:
            repository.seed_defaults(db)
        except (SQLAlchemyError, OSError) as error:
            logger.warning(
                "Startup seed deferred because the database is not ready (%s). Check /readiness.",
                type(error).__name__,
            )
            db.rollback()
            return
        try:
            audio.cleanup_audio_cache(db)
        except (SQLAlchemyError, OSError) as error:
            db.rollback()
            logger.warning(
                "Audio cache cleanup deferred because its schema or storage is not ready (%s).",
                type(error).__name__,
            )
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness", response_model=schemas.ReadinessReport)
def get_readiness() -> schemas.ReadinessReport:
    return readiness.build_readiness_report()


@app.get("/profile", response_model=schemas.ProfileRead)
def get_profile(db: Session = Depends(get_db)) -> schemas.ProfileRead:
    return repository.get_profile(db)


@app.patch("/profile", response_model=schemas.ProfileRead)
def patch_profile(payload: schemas.ProfileUpdate, db: Session = Depends(get_db)) -> schemas.ProfileRead:
    return repository.update_profile(db, payload)


@app.get("/settings", response_model=schemas.SettingsRead)
def get_settings(db: Session = Depends(get_db)) -> schemas.SettingsRead:
    return repository.get_settings(db)


@app.patch("/settings", response_model=schemas.SettingsRead)
def patch_settings(payload: schemas.SettingsUpdate, db: Session = Depends(get_db)) -> schemas.SettingsRead:
    return repository.update_settings(db, payload)


@app.get("/dashboard", response_model=schemas.DashboardOut)
def get_dashboard(db: Session = Depends(get_db)) -> schemas.DashboardOut:
    return repository.get_dashboard(db)


@app.get("/achievements", response_model=list[schemas.AchievementRead])
def get_achievements(db: Session = Depends(get_db)) -> list[schemas.AchievementRead]:
    return repository.get_achievements(db)


@app.get("/spelling/words", response_model=list[schemas.SpellingWordRead])
def get_spelling_words(
    level: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[schemas.SpellingWordRead]:
    return words.list_words(db, level=level)


@app.get("/spelling/word-management", response_model=schemas.SpellingWordManagementPage)
def get_spelling_word_management(
    query: str = Query(default="", max_length=120),
    category: str = Query(default="all"),
    mastery_state: str = Query(default=""),
    diagnostic_status: str = Query(default=""),
    sort: str = Query(default="term"),
    direction: str = Query(default="asc"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> schemas.SpellingWordManagementPage:
    return words.list_managed_words(
        db,
        query=query,
        category=category,
        mastery_state=mastery_state,
        diagnostic_status=diagnostic_status,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )


@app.get("/spelling/oxford/load-status", response_model=schemas.OxfordLoadStatus)
def get_spelling_oxford_load_status(db: Session = Depends(get_db)) -> schemas.OxfordLoadStatus:
    return oxford.load_status(db)


@app.post("/spelling/oxford/load-batch", response_model=schemas.OxfordLoadBatchResult)
def post_spelling_oxford_load_batch(
    payload: schemas.OxfordLoadBatchRequest,
    db: Session = Depends(get_db),
) -> schemas.OxfordLoadBatchResult:
    try:
        return oxford.load_batch(db, payload)
    except ValueError as err:
        raise HTTPException(status_code=503, detail=str(err))


@app.post("/spelling/words", response_model=schemas.SpellingWordRead)
def post_spelling_word(payload: schemas.SpellingWordCreate, db: Session = Depends(get_db)) -> schemas.SpellingWordRead:
    try:
        return words.create_word(db, payload)
    except ValueError as err:
        status_code = 400 if str(err).startswith("Word must") else 409
        raise HTTPException(status_code=status_code, detail=str(err))


@app.patch("/spelling/words/{word_id}", response_model=schemas.SpellingWordRead)
def patch_spelling_word(
    word_id: int,
    payload: schemas.SpellingWordUpdate,
    db: Session = Depends(get_db),
) -> schemas.SpellingWordRead:
    try:
        return words.update_word(db, word_id, payload)
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        if str(err) == "Word not found":
            status_code = 404
        elif str(err).startswith("Word must"):
            status_code = 400
        else:
            status_code = 409
        raise HTTPException(status_code=status_code, detail=str(err))


@app.post("/spelling/words/{word_id}/actions", response_model=schemas.SpellingWordActionResult)
def post_spelling_word_action(
    word_id: int,
    payload: schemas.SpellingWordAction,
    db: Session = Depends(get_db),
) -> schemas.SpellingWordActionResult:
    try:
        return words.apply_action(db, word_id, payload)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.get("/spelling/word-content/{word_id}", response_model=schemas.SpellingWordContentRead)
def get_spelling_word_content(word_id: int, db: Session = Depends(get_db)) -> schemas.SpellingWordContentRead:
    try:
        return repository.get_word_content(db, word_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.patch("/spelling/word-content/{word_id}", response_model=schemas.SpellingWordContentRead)
def patch_spelling_word_content(
    word_id: int,
    payload: schemas.SpellingWordContentOverride,
    db: Session = Depends(get_db),
) -> schemas.SpellingWordContentRead:
    try:
        return repository.override_word_content(db, word_id, payload)
    except ValueError as err:
        status_code = 404 if str(err) == "Word not found" else 400
        raise HTTPException(status_code=status_code, detail=str(err))


@app.post("/spelling/content/bulk-generate", response_model=schemas.ContentBulkGenerateResult)
def post_spelling_content_bulk_generate(
    payload: schemas.ContentBulkGenerateRequest,
    db: Session = Depends(get_db),
) -> schemas.ContentBulkGenerateResult:
    return repository.content_bulk_generate(db, payload)


@app.get("/spelling/content/bulk-preview", response_model=schemas.BulkGeneratePreview)
def get_spelling_content_bulk_preview(
    limit: int = Query(default=100, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> schemas.BulkGeneratePreview:
    return repository.content_bulk_preview(db, limit=limit)


@app.get("/spelling/content/bulk-status", response_model=schemas.ContentBulkStatus)
def get_spelling_content_bulk_status(db: Session = Depends(get_db)) -> schemas.ContentBulkStatus:
    return repository.content_bulk_status(db)


@app.get("/spelling/dictation/texts", response_model=schemas.DictationTextListOut)
def get_dictation_texts(
    level: Optional[str] = Query(default=None, pattern="^(sentence|passage|paragraph)$"),
    source_type: Optional[str] = Query(default=None, pattern="^(curated|personal|ai_adapted)$"),
    status: str = Query(default="active", pattern="^(active|reviewed|needs_adaptation|archived|all)$"),
    db: Session = Depends(get_db),
) -> schemas.DictationTextListOut:
    return dictation_texts.list_dictation_texts(
        db,
        level=level,
        source_type=source_type,
        status=status,
    )


@app.post("/spelling/dictation/texts", response_model=schemas.DictationTextRead)
def post_dictation_text(
    payload: schemas.DictationTextCreate,
    db: Session = Depends(get_db),
) -> schemas.DictationTextRead:
    try:
        return dictation_texts.create_personal_text(db, payload)
    except ValueError as error:
        status_code = 409 if "already in the library" in str(error) else 400
        raise HTTPException(status_code=status_code, detail=str(error))


@app.patch("/spelling/dictation/texts/{text_id}", response_model=schemas.DictationTextRead)
def patch_dictation_text(
    text_id: int,
    payload: schemas.DictationTextAction,
    db: Session = Depends(get_db),
) -> schemas.DictationTextRead:
    try:
        return dictation_texts.update_dictation_text(db, text_id, payload)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@app.delete("/spelling/dictation/texts/{text_id}", status_code=204)
def delete_dictation_text(text_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        dictation_texts.delete_dictation_text(db, text_id)
    except PermissionError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return Response(status_code=204)


@app.post(
    "/spelling/dictation/texts/{text_id}/adapt",
    response_model=schemas.DictationTextAdaptResult,
)
def post_dictation_text_adaptation(
    text_id: int,
    payload: schemas.DictationTextAdaptRequest,
    db: Session = Depends(get_db),
) -> schemas.DictationTextAdaptResult:
    try:
        return dictation_texts.adapt_dictation_text(db, text_id, payload)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))
    except ValueError as error:
        status_code = 404 if "not found" in str(error).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(error))


@app.get("/spelling/dictation/progress", response_model=schemas.DictationProgressOut)
def get_dictation_progress(db: Session = Depends(get_db)) -> schemas.DictationProgressOut:
    return repository.get_dictation_progress(db)


@app.post("/spelling/dictation/submissions", response_model=schemas.DictationSubmissionResult)
def post_dictation_submission(
    payload: schemas.DictationSubmissionCreate,
    db: Session = Depends(get_db),
) -> schemas.DictationSubmissionResult:
    try:
        return repository.submit_dictation_submission(db, payload)
    except ValueError as error:
        status_code = 409 if "already been submitted" in str(error) else 404
        raise HTTPException(status_code=status_code, detail=str(error))


@app.get("/spelling/dictation/items/{item_id}/audio")
def get_dictation_item_audio(
    item_id: int,
    segment: Optional[int] = Query(default=None, ge=0),
    db: Session = Depends(get_db),
) -> Response:
    item = db.get(models.SpellingSessionItem, item_id)
    if not item or not item.dictation_text:
        raise HTTPException(status_code=404, detail="Dictation item not found.")
    settings = repository.get_settings(db)
    try:
        resolved = audio.resolve_audio_asset(
            db,
            schemas.SpellingAudioAssetResolveRequest(
                session_item_id=item_id,
                segment_index=segment,
            ),
            voice=settings.tts_voice,
            model=settings.tts_model,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return audio.get_audio_asset_response(
        db,
        resolved.asset_id,
    )


@app.post("/spelling/audio/assets/resolve", response_model=schemas.SpellingAudioAssetRead)
def resolve_spelling_audio_asset(
    payload: schemas.SpellingAudioAssetResolveRequest,
    db: Session = Depends(get_db),
) -> schemas.SpellingAudioAssetRead:
    settings = repository.get_settings(db)
    try:
        return audio.resolve_audio_asset(
            db,
            payload,
            voice=settings.tts_voice,
            model=settings.tts_model,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/spelling/audio/assets/{asset_id}")
def get_spelling_audio_asset(
    asset_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Response:
    return audio.get_audio_asset_response(db, asset_id, force=force)


@app.post("/spelling/audio/cleanup", response_model=schemas.SpellingAudioCleanupResult)
def cleanup_spelling_audio(
    db: Session = Depends(get_db),
) -> schemas.SpellingAudioCleanupResult:
    return audio.cleanup_audio_cache(db)


@app.get("/spelling/exploration/next", response_model=schemas.ExplorationNextOut)
def get_spelling_exploration_next(
    word_id: Optional[int] = Query(default=None),
    direction: str = Query(default="next"),
    pool: str = Query(default="oxford"),
    db: Session = Depends(get_db),
) -> schemas.ExplorationNextOut:
    try:
        return repository.get_exploration_next(db, word_id=word_id, direction=direction, pool=pool)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.post("/spelling/exploration/action", response_model=schemas.ExplorationActionResult)
def post_spelling_exploration_action(
    payload: schemas.ExplorationAction,
    db: Session = Depends(get_db),
) -> schemas.ExplorationActionResult:
    try:
        return repository.submit_exploration_action(db, payload)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.post("/spelling/placement/attempt", response_model=schemas.SpellingPlacementResult)
def post_spelling_placement(
    payload: schemas.SpellingPlacementAttempt,
    db: Session = Depends(get_db),
) -> schemas.SpellingPlacementResult:
    try:
        return repository.submit_spelling_placement(db, payload)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.post("/spelling/sessions", response_model=schemas.SpellingSessionOut)
def post_spelling_session(
    payload: schemas.SpellingSessionCreate,
    db: Session = Depends(get_db),
) -> schemas.SpellingSessionOut:
    return sessions.create_session(db, payload)


@app.get("/spelling/sessions/{session_id}", response_model=schemas.SpellingSessionOut)
def get_spelling_session(session_id: int, db: Session = Depends(get_db)) -> schemas.SpellingSessionOut:
    session = sessions.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/spelling/attempts", response_model=schemas.SpellingAttemptResult)
def post_spelling_attempts(
    payload: schemas.SpellingAttemptCreate,
    db: Session = Depends(get_db),
) -> schemas.SpellingAttemptResult:
    try:
        return attempts.submit_attempt(db, payload)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.post("/spelling/attempts/{attempt_id}/correct", response_model=schemas.SpellingCorrectionResult)
def post_spelling_correction(
    attempt_id: int,
    payload: schemas.SpellingCorrectionSubmit,
    db: Session = Depends(get_db),
) -> schemas.SpellingCorrectionResult:
    try:
        return attempts.submit_correction(db, attempt_id, payload)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.get("/spelling/suggestions", response_model=list[schemas.SpellingSuggestionRead])
def get_spelling_suggestions(
    status: str = Query(default="pending"),
    db: Session = Depends(get_db),
) -> list[schemas.SpellingSuggestionRead]:
    return suggestions.list_suggestions(db, status=status)


@app.patch("/spelling/suggestions/{suggestion_id}", response_model=schemas.SpellingSuggestionRead)
def patch_spelling_suggestion(
    suggestion_id: int,
    payload: schemas.SpellingSuggestionAction,
    db: Session = Depends(get_db),
) -> schemas.SpellingSuggestionRead:
    suggestion = suggestions.update_suggestion(db, suggestion_id, payload)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return suggestion


@app.get("/spelling/overview", response_model=schemas.SpellingOverview)
def get_spelling_overview(
    as_of: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
) -> schemas.SpellingOverview:
    return analytics.overview(db, as_of)


@app.get("/spelling/analytics", response_model=schemas.SpellingAnalyticsOut)
def get_spelling_analytics(db: Session = Depends(get_db)) -> schemas.SpellingAnalyticsOut:
    return analytics.analytics(db)


@app.get("/spelling/core5k/overview", response_model=schemas.Core5KOverviewOut)
def get_spelling_core5k_overview(db: Session = Depends(get_db)) -> schemas.Core5KOverviewOut:
    return analytics.core5k_overview(db)


@app.get("/spelling/overview/modes", response_model=schemas.SpellingModesOverviewOut)
def get_spelling_modes_overview(db: Session = Depends(get_db)) -> schemas.SpellingModesOverviewOut:
    return analytics.mode_overview(db)


@app.get("/spelling/daily-plan", response_model=schemas.SpellingDailyPlanOut)
def get_spelling_daily_plan(db: Session = Depends(get_db)) -> schemas.SpellingDailyPlanOut:
    return repository.get_spelling_daily_plan(db)


@app.get("/spelling/costs", response_model=schemas.SpellingCostOverview)
def get_spelling_costs(db: Session = Depends(get_db)) -> schemas.SpellingCostOverview:
    return repository.get_spelling_cost_overview(db)


@app.get("/spelling/audio")
def get_spelling_audio(
    text: str = Query(min_length=1, max_length=200),
    voice: Optional[str] = Query(default=None, min_length=1, max_length=40),
    model: Optional[str] = Query(default=None, min_length=1, max_length=80),
    word_id: Optional[int] = Query(default=None, ge=1),
    mode: str = Query(default="word", pattern="^(word|dictation)$"),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Response:
    settings = repository.get_settings(db)
    word = db.get(models.SpellingWord, word_id) if word_id is not None else None
    if word_id is not None and word is None:
        raise HTTPException(status_code=404, detail="Word not found")
    return audio.get_audio_response(
        text,
        voice=voice or settings.tts_voice,
        model=model or settings.tts_model,
        instructions=audio.pronunciation_instructions(text, word, mode),
        force=force,
    )


@app.post("/spelling/audio/preload", response_model=schemas.SpellingAudioPreloadResponse)
def preload_spelling_audio(
    payload: schemas.SpellingAudioPreloadRequest,
    db: Session = Depends(get_db),
) -> schemas.SpellingAudioPreloadResponse:
    settings = repository.get_settings(db)
    return audio.preload_audio(
        payload,
        voice=payload.voice or settings.tts_voice,
        model=payload.model or settings.tts_model,
    )


@app.get("/spelling/audio/bulk-status", response_model=schemas.SpellingAudioBulkStatus)
def get_spelling_audio_bulk_status(
    voice: Optional[str] = Query(default=None, min_length=1, max_length=40),
    model: Optional[str] = Query(default=None, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> schemas.SpellingAudioBulkStatus:
    settings = repository.get_settings(db)
    return audio.bulk_audio_status(
        db,
        voice=voice or settings.tts_voice,
        model=model or settings.tts_model,
    )


@app.get("/spelling/audio/bulk-preview", response_model=schemas.BulkGeneratePreview)
def get_spelling_audio_bulk_preview(
    limit: int = Query(default=100, ge=1, le=5000),
    voice: Optional[str] = Query(default=None, min_length=1, max_length=40),
    model: Optional[str] = Query(default=None, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> schemas.BulkGeneratePreview:
    settings = repository.get_settings(db)
    return audio.bulk_audio_preview(
        db,
        limit=limit,
        voice=voice or settings.tts_voice,
        model=model or settings.tts_model,
    )


@app.post("/spelling/audio/bulk-generate", response_model=schemas.SpellingAudioBulkGenerateResult)
def post_spelling_audio_bulk_generate(
    payload: schemas.SpellingAudioBulkGenerateRequest,
    db: Session = Depends(get_db),
) -> schemas.SpellingAudioBulkGenerateResult:
    settings = repository.get_settings(db)
    selected = payload.model_copy(
        update={
            "voice": payload.voice if "voice" in payload.model_fields_set else settings.tts_voice,
            "model": payload.model if "model" in payload.model_fields_set else settings.tts_model,
        }
    )
    return audio.bulk_generate_audio(db, selected)
