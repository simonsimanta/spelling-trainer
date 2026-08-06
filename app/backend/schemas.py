from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ProfileRead(BaseModel):
    id: int = 1
    name: str
    avatar: str
    level_label: str
    current_streak: int
    best_streak: int
    points: int
    practice_time_seconds: int
    daily_goal: int

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    avatar: Optional[str] = Field(default=None, max_length=80)
    level_label: Optional[str] = Field(default=None, max_length=40)
    daily_goal: Optional[int] = Field(default=None, ge=1, le=200)


class SettingsRead(BaseModel):
    id: int = 1
    theme: str
    tts_voice: str
    tts_model: str
    ai_model: str
    ai_generation_enabled: bool
    english_variant: str = "en-GB"
    content_bulk_limit: int

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    theme: Optional[str] = Field(default=None, max_length=40)
    tts_voice: Optional[str] = Field(default=None, min_length=1, max_length=40)
    tts_model: Optional[str] = Field(default=None, min_length=1, max_length=80)
    ai_model: Optional[str] = Field(default=None, max_length=80)
    ai_generation_enabled: Optional[bool] = None
    english_variant: Optional[Literal["en-GB", "en-US"]] = None
    content_bulk_limit: Optional[int] = Field(default=None, ge=1, le=5000)


class ReadinessCheck(BaseModel):
    key: str
    label: str
    status: Literal["ready", "warning", "failed"]
    required: bool
    detail: str
    action: Optional[str] = None


class ReadinessReport(BaseModel):
    status: Literal["ready", "degraded", "unavailable"]
    database_backend: str
    database_target: str
    checks: List[ReadinessCheck] = Field(default_factory=list)


class OxfordLoadStatus(BaseModel):
    target_words: int = 5000
    loaded_words: int
    remaining_words: int
    next_batch_size: int
    source_available: bool


class OxfordLoadBatchRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)


class OxfordLoadBatchResult(BaseModel):
    requested_limit: int
    created: int
    updated: int
    skipped: int
    loaded_words: int
    remaining_words: int


class SpellingWordCreate(BaseModel):
    term: str = Field(min_length=2, max_length=120)
    level: str = Field(default="personal", min_length=2, max_length=30)
    source: str = Field(default="manual", min_length=2, max_length=30)


class SpellingWordRead(BaseModel):
    id: int
    term: str
    level: str
    source: str
    is_active: bool
    source_list: Optional[str] = None
    short_meaning: Optional[str] = None
    example_sentence: Optional[str] = None
    ipa: Optional[str] = None
    part_of_speech: Optional[str] = None
    cefr_level: Optional[str] = None
    mastery_state: str = "new"
    diagnostic_status: str = "untested"
    priority_score: float = 0.0
    known_skipped: bool = False

    model_config = {"from_attributes": True}


class SpellingWordManagementItem(BaseModel):
    id: int
    term: str
    level: str
    source: str
    source_label: str
    is_active: bool
    is_personal: bool
    source_list: Optional[str] = None
    short_meaning: Optional[str] = None
    example_sentence: Optional[str] = None
    part_of_speech: Optional[str] = None
    cefr_level: Optional[str] = None
    frequency_rank: Optional[int] = None
    mastery_state: str
    diagnostic_status: str
    known_skipped: bool
    priority_score: float
    review_stage: Optional[str] = None
    due_date: Optional[date] = None
    last_attempt_at: Optional[datetime] = None
    last_attempt_correct: Optional[bool] = None


class SpellingWordManagementCounts(BaseModel):
    all: int = 0
    oxford: int = 0
    personal: int = 0
    suggested: int = 0
    trouble: int = 0
    provisional: int = 0
    stable: int = 0
    seed: int = 0
    archived: int = 0


class SpellingWordManagementPage(BaseModel):
    items: List[SpellingWordManagementItem] = Field(default_factory=list)
    total: int
    counts: SpellingWordManagementCounts


class SpellingWordUpdate(BaseModel):
    term: Optional[str] = Field(default=None, min_length=2, max_length=120)
    short_meaning: Optional[str] = Field(default=None, max_length=1000)
    example_sentence: Optional[str] = Field(default=None, max_length=1000)
    part_of_speech: Optional[str] = Field(default=None, max_length=60)
    cefr_level: Optional[str] = Field(default=None, pattern="^(A1|A2|B1|B2|C1|C2)?$")


class SpellingWordAction(BaseModel):
    action: Literal["practice", "mark_known", "reset", "archive", "restore"]


class SpellingWordActionResult(BaseModel):
    word_id: int
    term: str
    action: str
    message: str


class SpellingWordContentRead(BaseModel):
    word_id: int
    term: str
    meaning: str
    ipa: Optional[str] = None
    part_of_speech: Optional[str] = None
    examples: List[str] = Field(default_factory=list)
    word_family: List[Dict[str, str]] = Field(default_factory=list)
    chunked_form: Optional[str] = None
    mnemonic: Optional[str] = None
    phonetic_hint: Optional[str] = None
    generation_source: str = "ai"
    quality_warnings: List[str] = Field(default_factory=list)
    fallback_reason: Optional[str] = None
    review_notes: Optional[str] = None
    status: str = "generated"


class SpellingWordContentOverride(BaseModel):
    meaning: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    ipa: Optional[str] = Field(default=None, max_length=255)
    part_of_speech: Optional[str] = Field(default=None, max_length=60)
    examples: Optional[List[str]] = Field(default=None, min_length=1, max_length=3)
    word_family: Optional[List[Dict[str, str]]] = Field(default=None, max_length=6)
    chunked_form: Optional[str] = Field(default=None, max_length=255)
    mnemonic: Optional[str] = Field(default=None, max_length=500)
    phonetic_hint: Optional[str] = Field(default=None, max_length=255)
    review_notes: Optional[str] = Field(default=None, max_length=1000)


class SpellingAttemptCreate(BaseModel):
    word_id: int
    attempt_text: str = Field(min_length=1, max_length=120)
    session_id: Optional[int] = None
    session_item_id: Optional[int] = None
    mode: Literal["diagnostic", "exploration", "practice", "dictation", "review_due", "learn_new", "fix_mistakes", "core_5k"] = "practice"
    response_ms: Optional[int] = Field(default=None, ge=0)
    used_hint: bool = False
    used_reveal: bool = False
    input_method: str = "typed"
    confidence_score: Optional[float] = None


class SpellingAttemptResult(BaseModel):
    attempt_id: Optional[int] = None
    word_id: int
    term: str
    attempt_text: str
    is_correct: bool
    points_awarded: int
    error_pattern: Optional[str]
    next_due_date: date
    llm_feedback: Optional[str]
    error_analysis: Optional[Dict[str, Any]] = None
    chunk_hint: str
    mnemonic: str
    example_sentence: str
    diff_json: Optional[Dict[str, Any]] = None
    sentence_diff_json: Optional[Dict[str, Any]] = None
    target_spelling_correct: Optional[bool] = None
    sentence_complete: Optional[bool] = None
    sentence_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    chunk_feedback: Optional[str] = None
    phonetic_feedback: Optional[Dict[str, Any]] = None
    forced_correction_required: bool = False
    allow_next: bool = True
    mastery_state: Optional[str] = None
    mastery_state_before: Optional[str] = None
    mastery_state_after: Optional[str] = None
    retry_prompt: Optional[str] = None
    retry_index: int = 0
    skip_available: bool = False
    skip_after_retries: int = 2


class SpellingCorrectionSubmit(BaseModel):
    correction_text: str = Field(min_length=1, max_length=300)
    attempt_text: Optional[str] = None


class SpellingCorrectionResult(BaseModel):
    accepted: bool
    allow_next: bool
    review_stage: str
    due_date: Optional[date] = None
    retries_remaining: int = 0
    skip_available: bool = False


class SpellingSessionCreate(BaseModel):
    session_type: Literal["diagnostic", "exploration", "practice", "dictation", "review_due", "learn_new", "fix_mistakes", "core_5k"] = "practice"
    target_size: int = Field(default=10, ge=1, le=100)
    exercise_type: Literal["spelling_quiz", "fill_blank", "word_scramble", "choose_correct", "mixed"] = "mixed"
    level: str = "all"
    word_ids: List[int] = Field(default_factory=list, max_length=100)


class SpellingSessionItemOut(BaseModel):
    session_item_id: int
    word_id: Optional[int] = None
    term: str
    item_type: str
    mode: str
    prompt_text: str
    source_reason: Optional[str] = None
    queue_reason: Optional[str] = None
    selection_score: float = 0.0
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    status: str = "pending"
    audio_ready: bool = False
    choices: Optional[List[str]] = None
    short_meaning: Optional[str] = None
    part_of_speech: Optional[str] = None
    chunked_form: Optional[str] = None
    phonetic_hint: Optional[str] = None
    difficulty_score: Optional[float] = None


class SpellingSessionOut(BaseModel):
    session_id: int
    session_type: str
    total_items: int
    completed_items: int
    items: List[SpellingSessionItemOut]


class SpellingSuggestionRead(BaseModel):
    id: int
    word_id: Optional[int]
    term: str
    reason: str
    status: str
    pattern_code: Optional[str] = None
    confidence: float = 0.0
    evidence_count: int = 0
    validation_status: str = "pending"

    model_config = {"from_attributes": True}


class SpellingSuggestionAction(BaseModel):
    status: str = Field(pattern="^(approved|rejected|ignored)$")


class SpellingOverview(BaseModel):
    due_today: int
    hard_words: int
    attempts_today: int
    points_today: int


class SpellingAnalyticsOut(BaseModel):
    mastered_words: int
    learning_words: int
    trouble_words: int
    average_first_try_accuracy: float
    retention_7d: Optional[float] = None
    top_patterns: List[Dict[str, Any]] = Field(default_factory=list)


class Core5KOverviewOut(BaseModel):
    total_words: int
    attempted_words: int
    mastered_words: int
    in_learning_words: int
    due_today_words: int
    coverage_percent: float


class SpellingModeMetric(BaseModel):
    mode: str
    total_attempts: int
    correct_attempts: int
    accuracy: float


class SpellingModesOverviewOut(BaseModel):
    modes: List[SpellingModeMetric] = Field(default_factory=list)


class SpellingPlacementAttempt(BaseModel):
    word_id: int
    action: Literal["known", "practice"]
    session_id: Optional[int] = None
    session_item_id: Optional[int] = None


class SpellingPlacementResult(BaseModel):
    word_id: int
    term: str
    mastery_state: str
    known_skipped: bool
    due_date: Optional[date] = None


class ExplorationNextOut(BaseModel):
    word: SpellingWordRead
    content: SpellingWordContentRead
    pool: str = "oxford"
    source_reason: Optional[str] = None
    previous_word_id: Optional[int] = None
    next_word_id: Optional[int] = None
    progress_index: int
    total_words: int


class ExplorationAction(BaseModel):
    word_id: int
    action: Literal["known", "practice", "viewed"]


class ExplorationActionResult(BaseModel):
    word_id: int
    action: str
    next_word_id: Optional[int] = None
    points_awarded: int = 0


class ActivityRead(BaseModel):
    id: int
    event_type: str
    title: str
    detail: Optional[str]
    points: int
    accuracy: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


class AchievementRead(BaseModel):
    code: str
    title: str
    description: str
    category: str
    target: int
    progress: int
    unlocked_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DashboardPatternMetric(BaseModel):
    code: str
    label: str
    total_attempts: int
    incorrect_attempts: int
    recent_error_rate: float


class DashboardTrendPoint(BaseModel):
    day: date
    total_attempts: int
    correct_attempts: int
    accuracy: float


class DashboardStats(BaseModel):
    oxford_target_words: int = 5000
    oxford_loaded_words: int
    oxford_explored_words: int
    practice_distinct_words: int
    dictation_distinct_words: int
    mastered_words: int
    learning_words: int
    trouble_words: int
    due_today_words: int
    forced_correction_words: int
    practice_queue_words: int
    dictation_ready_words: int
    diagnostic_ready_words: int
    diagnostic_tested_words: int
    diagnostic_missed_words: int
    diagnostic_accuracy: float
    first_try_accuracy: float
    exploration_accuracy: float
    practice_accuracy: float
    dictation_accuracy: float
    retention_accuracy_7d: float
    retention_accuracy_14d: float
    retention_accuracy_30d: float
    retention_accuracy_60d: float
    lapse_rate: float
    review_debt_words: int
    known_provisional_words: int
    stable_known_words: int
    due_audit_words: int
    llm_suggested_words: int
    llm_pending_suggestions: int
    content_generated_words: int
    audio_generated_words: int
    pattern_error_rates: List[DashboardPatternMetric] = Field(default_factory=list)
    recent_mode_accuracy: List[SpellingModeMetric] = Field(default_factory=list)
    accuracy_trend: List[DashboardTrendPoint] = Field(default_factory=list)


class SpellingDailyPlanOut(BaseModel):
    recommended_mode: str
    recommended_reason: str
    mode_scores: Dict[str, float] = Field(default_factory=dict)
    due_reviews: int
    mistake_words: int
    new_words: int
    dictation_ready: int


class DashboardOut(BaseModel):
    profile: ProfileRead
    overview: SpellingOverview
    core5k: Core5KOverviewOut
    stats: DashboardStats
    words_learned: int
    accuracy: float
    practice_time_seconds: int
    recent_activity: List[ActivityRead]
    achievements: List[AchievementRead]
    daily_plan: SpellingDailyPlanOut


class ContentBulkGenerateRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)
    force: bool = False


class ContentBulkGenerateResult(BaseModel):
    requested_limit: int
    generated: int
    fallback: int = 0
    cached: int
    failed: int
    remaining: int


class ContentBulkStatus(BaseModel):
    total_words: int
    generated: int
    fallback: int
    reviewed: int
    pending: int
    failed: int


class BulkGeneratePreview(BaseModel):
    limit: int
    total_words: int
    generated: int
    pending: int
    failed: int
    will_process: int
    estimated_api_calls: int
    model: str
    voice: Optional[str] = None
    fallback: int = 0
    reviewed: int = 0
    ai_generation_enabled: Optional[bool] = None


class SpellingAudioPreloadRequest(BaseModel):
    texts: List[str] = Field(default_factory=list)
    voice: Optional[str] = Field(default=None, min_length=1, max_length=40)
    model: Optional[str] = Field(default=None, min_length=1, max_length=80)


class SpellingAudioPreloadResponse(BaseModel):
    requested: int
    cached: int
    generated: int
    voice: str
    model: str


class SpellingAudioBulkGenerateRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)
    voice: str = Field(default="alloy", min_length=1, max_length=40)
    model: str = Field(default="gpt-4o-mini-tts", min_length=1, max_length=80)


class SpellingAudioBulkGenerateResult(BaseModel):
    requested_limit: int
    generated: int
    cached: int
    failed: int
    remaining: int
    voice: str
    model: str


class SpellingAudioBulkStatus(BaseModel):
    total_words: int
    generated: int
    pending: int
    failed: int
    voice: str
    model: str


class SpellingCostOverview(BaseModel):
    feedback_cache_entries: int
    feedback_cache_hits: int
    estimated_feedback_input_tokens: int
    estimated_feedback_output_tokens: int
    generated_audio_files: int
    failed_audio_files: int
