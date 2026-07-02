from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.backend import repository, schemas
from app.backend.db import get_db
from app.backend.spelling import analytics, attempts, audio, oxford, sessions, suggestions, words


app = FastAPI(title="Spelling Trainer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_seed() -> None:
    db = next(get_db())
    try:
        repository.seed_defaults(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    return words.create_word(db, payload)


@app.get("/spelling/word-content/{word_id}", response_model=schemas.SpellingWordContentRead)
def get_spelling_word_content(word_id: int, db: Session = Depends(get_db)) -> schemas.SpellingWordContentRead:
    try:
        return repository.get_word_content(db, word_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


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
def get_spelling_audio(text: str = Query(min_length=1, max_length=200)) -> Response:
    return audio.get_audio_response(text)


@app.post("/spelling/audio/preload", response_model=schemas.SpellingAudioPreloadResponse)
def preload_spelling_audio(payload: schemas.SpellingAudioPreloadRequest) -> schemas.SpellingAudioPreloadResponse:
    return audio.preload_audio(payload)


@app.get("/spelling/audio/bulk-status", response_model=schemas.SpellingAudioBulkStatus)
def get_spelling_audio_bulk_status(db: Session = Depends(get_db)) -> schemas.SpellingAudioBulkStatus:
    return audio.bulk_audio_status(db)


@app.get("/spelling/audio/bulk-preview", response_model=schemas.BulkGeneratePreview)
def get_spelling_audio_bulk_preview(
    limit: int = Query(default=100, ge=1, le=5000),
    voice: str = Query(default="alloy", max_length=40),
    model: str = Query(default="gpt-4o-mini-tts", max_length=80),
    db: Session = Depends(get_db),
) -> schemas.BulkGeneratePreview:
    return audio.bulk_audio_preview(db, limit=limit, voice=voice, model=model)


@app.post("/spelling/audio/bulk-generate", response_model=schemas.SpellingAudioBulkGenerateResult)
def post_spelling_audio_bulk_generate(
    payload: schemas.SpellingAudioBulkGenerateRequest,
    db: Session = Depends(get_db),
) -> schemas.SpellingAudioBulkGenerateResult:
    return audio.bulk_generate_audio(db, payload)
