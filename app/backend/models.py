import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.db import Base


class LearnerProfile(Base):
    __tablename__ = "learner_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(120), default="Ananya", nullable=False)
    avatar: Mapped[str] = mapped_column(String(80), default="student", nullable=False)
    level_label: Mapped[str] = mapped_column(String(40), default="Level 4", nullable=False)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    practice_time_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_goal: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    last_practice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    theme: Mapped[str] = mapped_column(String(40), default="light", nullable=False)
    tts_voice: Mapped[str] = mapped_column(String(40), default="alloy", nullable=False)
    tts_model: Mapped[str] = mapped_column(String(80), default="gpt-4o-mini-tts", nullable=False)
    ai_model: Mapped[str] = mapped_column(String(80), default="gpt-4o-mini", nullable=False)
    ai_generation_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    content_bulk_limit: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SpellingStage(str, enum.Enum):
    new = "new"
    learning = "learning"
    review = "review"
    trouble = "trouble"
    mastered = "mastered"


class SpellingSessionType(str, enum.Enum):
    diagnostic = "diagnostic"
    exploration = "exploration"
    practice = "practice"
    dictation = "dictation"
    review_due = "review_due"
    learn_new = "learn_new"
    fix_mistakes = "fix_mistakes"
    core_5k = "core_5k"


class SpellingSessionItemType(str, enum.Enum):
    review_word = "review_word"
    core_word = "core_word"
    new_word = "new_word"
    spelling_quiz = "spelling_quiz"
    fill_blank = "fill_blank"
    word_scramble = "word_scramble"
    choose_correct = "choose_correct"
    sentence_dictation = "sentence_dictation"


class SpellingSessionItemStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    skipped = "skipped"


class SpellingMode(str, enum.Enum):
    diagnostic = "diagnostic"
    exploration = "exploration"
    practice = "practice"
    dictation = "dictation"
    review_due = "review_due"
    learn_new = "learn_new"
    fix_mistakes = "fix_mistakes"
    core_5k = "core_5k"


class SpellingWord(Base):
    __tablename__ = "spelling_words"
    __table_args__ = (UniqueConstraint("term", name="uq_spelling_word_term"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    term: Mapped[str] = mapped_column(String(120), nullable=False)
    level: Mapped[str] = mapped_column(String(30), default="daily", nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="seed", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ipa: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phonetic_hint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chunked_form: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    example_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_list: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    short_meaning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    part_of_speech: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    is_confusable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mastery_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    cefr_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    mastery_state: Mapped[str] = mapped_column(String(30), default="new", nullable=False)
    diagnostic_status: Mapped[str] = mapped_column(String(30), default="untested", nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    known_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    introduced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    reviews = relationship("SpellingReview", back_populates="word", cascade="all, delete")
    attempts = relationship("SpellingAttempt", back_populates="word", cascade="all, delete")
    suggestions = relationship("SpellingSuggestion", back_populates="word", cascade="all, delete")
    session_items = relationship("SpellingSessionItem", back_populates="word", cascade="all, delete")
    pattern_links = relationship("SpellingWordPattern", back_populates="word", cascade="all, delete")
    confusion_links = relationship("SpellingConfusionGroupWord", back_populates="word", cascade="all, delete")
    sources = relationship("SpellingWordSource", back_populates="word", cascade="all, delete")
    audio_manifests = relationship("SpellingAudioManifest", back_populates="word", cascade="all, delete")
    feedback_cache_entries = relationship("SpellingFeedbackCache", back_populates="word", cascade="all, delete")
    content_cache = relationship("SpellingWordContent", back_populates="word", cascade="all, delete", uselist=False)


class SpellingWordContent(Base):
    __tablename__ = "spelling_word_content"
    __table_args__ = (UniqueConstraint("word_id", name="uq_spelling_word_content_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    meaning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ipa: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    part_of_speech: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    examples: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    word_family: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="generated", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    word = relationship("SpellingWord", back_populates="content_cache")


class SpellingWordSource(Base):
    __tablename__ = "spelling_word_sources"
    __table_args__ = (UniqueConstraint("word_id", "source_name", name="uq_spelling_word_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(40), nullable=False)
    source_level: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    list_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    word = relationship("SpellingWord", back_populates="sources")


class SpellingReview(Base):
    __tablename__ = "spelling_reviews"
    __table_args__ = (UniqueConstraint("word_id", name="uq_spelling_review_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_correct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.3, nullable=False)
    stability_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lapse_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    average_response_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forced_correction_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_stage: Mapped[SpellingStage] = mapped_column(
        SAEnum(SpellingStage, name="spelling_stage", native_enum=False),
        default=SpellingStage.learning,
        nullable=False,
    )
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    consecutive_forced_corrections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    word = relationship("SpellingWord", back_populates="reviews")


class SpellingSession(Base):
    __tablename__ = "spelling_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    session_type: Mapped[SpellingSessionType] = mapped_column(
        SAEnum(SpellingSessionType, name="spelling_session_type", native_enum=False), nullable=False
    )
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_first_try: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forced_corrections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confusion_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sentence_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    items = relationship(
        "SpellingSessionItem",
        back_populates="session",
        cascade="all, delete",
        order_by="SpellingSessionItem.order_index",
    )
    attempts = relationship("SpellingAttempt", back_populates="session")


class SpellingSessionItem(Base):
    __tablename__ = "spelling_session_items"
    __table_args__ = (UniqueConstraint("session_id", "order_index", name="uq_spelling_session_item_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("spelling_sessions.id", ondelete="CASCADE"), nullable=False)
    word_id: Mapped[Optional[int]] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    item_type: Mapped[SpellingSessionItemType] = mapped_column(
        SAEnum(SpellingSessionItemType, name="spelling_session_item_type", native_enum=False), nullable=False
    )
    source_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    choices: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[SpellingSessionItemStatus] = mapped_column(
        SAEnum(SpellingSessionItemStatus, name="spelling_session_item_status", native_enum=False),
        default=SpellingSessionItemStatus.pending,
        nullable=False,
    )
    forced_correction_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    session = relationship("SpellingSession", back_populates="items")
    word = relationship("SpellingWord", back_populates="session_items")
    attempts = relationship("SpellingAttempt", back_populates="session_item")


class SpellingAttempt(Base):
    __tablename__ = "spelling_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    attempt_date: Mapped[date] = mapped_column(Date, nullable=False)
    attempt_text: Mapped[str] = mapped_column(String(120), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_pattern: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    llm_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mode: Mapped[SpellingMode] = mapped_column(
        SAEnum(SpellingMode, name="spelling_mode", native_enum=False),
        default=SpellingMode.practice,
        nullable=False,
    )
    input_method: Mapped[str] = mapped_column(String(50), default="typed", nullable=False)
    diff_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    chunk_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phonetic_feedback: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    retry_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    was_forced_correction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mastery_state_before: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    mastery_state_after: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("spelling_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("spelling_session_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    word = relationship("SpellingWord", back_populates="attempts")
    session = relationship("SpellingSession", back_populates="attempts")
    session_item = relationship("SpellingSessionItem", back_populates="attempts")


class SpellingSuggestion(Base):
    __tablename__ = "spelling_suggestions"
    __table_args__ = (UniqueConstraint("term", name="uq_spelling_suggestion_term"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[Optional[int]] = mapped_column(ForeignKey("spelling_words.id", ondelete="SET NULL"), nullable=True)
    term: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    word = relationship("SpellingWord", back_populates="suggestions")


class SpellingPattern(Base):
    __tablename__ = "spelling_patterns"
    __table_args__ = (UniqueConstraint("code", name="uq_spelling_pattern_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    examples: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    difficulty_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    word_links = relationship("SpellingWordPattern", back_populates="pattern", cascade="all, delete")
    user_stats = relationship("SpellingUserPatternStat", back_populates="pattern", cascade="all, delete")


class SpellingWordPattern(Base):
    __tablename__ = "spelling_word_patterns"
    __table_args__ = (UniqueConstraint("word_id", "pattern_id", name="uq_spelling_word_pattern"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("spelling_patterns.id", ondelete="CASCADE"), nullable=False)
    strength: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    word = relationship("SpellingWord", back_populates="pattern_links")
    pattern = relationship("SpellingPattern", back_populates="word_links")


class SpellingConfusionGroup(Base):
    __tablename__ = "spelling_confusion_groups"
    __table_args__ = (UniqueConstraint("name", name="uq_spelling_confusion_group_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    words = relationship("SpellingConfusionGroupWord", back_populates="group", cascade="all, delete")


class SpellingConfusionGroupWord(Base):
    __tablename__ = "spelling_confusion_group_words"
    __table_args__ = (UniqueConstraint("group_id", "word_id", name="uq_spelling_confusion_group_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("spelling_confusion_groups.id", ondelete="CASCADE"), nullable=False)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group = relationship("SpellingConfusionGroup", back_populates="words")
    word = relationship("SpellingWord", back_populates="confusion_links")


class SpellingUserPatternStat(Base):
    __tablename__ = "spelling_user_pattern_stats"
    __table_args__ = (UniqueConstraint("pattern_id", name="uq_spelling_user_pattern_stat_pattern"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("spelling_patterns.id", ondelete="CASCADE"), nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recent_error_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    pattern = relationship("SpellingPattern", back_populates="user_stats")


class SpellingAudioManifest(Base):
    __tablename__ = "spelling_audio_manifest"
    __table_args__ = (UniqueConstraint("word_id", "voice", "model", name="uq_spelling_audio_manifest_variant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    term: Mapped[str] = mapped_column(String(120), nullable=False)
    voice: Mapped[str] = mapped_column(String(40), default="alloy", nullable=False)
    model: Mapped[str] = mapped_column(String(80), default="gpt-4o-mini-tts", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    word = relationship("SpellingWord", back_populates="audio_manifests")


class SpellingFeedbackCache(Base):
    __tablename__ = "spelling_feedback_cache"
    __table_args__ = (
        UniqueConstraint("word_id", "normalized_attempt", "error_pattern", name="uq_spelling_feedback_cache_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("spelling_words.id", ondelete="CASCADE"), nullable=False)
    normalized_attempt: Mapped[str] = mapped_column(String(120), nullable=False)
    error_pattern: Mapped[str] = mapped_column(String(120), nullable=False)
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    word = relationship("SpellingWord", back_populates="feedback_cache_entries")


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    word_id: Mapped[Optional[int]] = mapped_column(ForeignKey("spelling_words.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("code", name="uq_achievement_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    target: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unlocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
