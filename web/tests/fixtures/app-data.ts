export const firstRunDashboard = {
  profile: {
    id: 1,
    name: "Learner",
    avatar: "default",
    level_label: "Starter",
    current_streak: 0,
    best_streak: 0,
    points: 0,
    practice_time_seconds: 0,
    daily_goal: 10
  },
  overview: {
    due_today: 0,
    hard_words: 0,
    attempts_today: 0,
    points_today: 0
  },
  core5k: {
    total_words: 5000,
    attempted_words: 0,
    mastered_words: 0,
    in_learning_words: 0,
    due_today_words: 0,
    coverage_percent: 0
  },
  stats: {
    oxford_target_words: 5000,
    oxford_loaded_words: 0,
    oxford_explored_words: 0,
    practice_distinct_words: 0,
    dictation_distinct_words: 0,
    mastered_words: 0,
    learning_words: 19,
    trouble_words: 0,
    due_today_words: 19,
    forced_correction_words: 0,
    practice_queue_words: 0,
    dictation_ready_words: 0,
    diagnostic_ready_words: 19,
    diagnostic_tested_words: 0,
    diagnostic_missed_words: 0,
    diagnostic_accuracy: 0,
    first_try_accuracy: 0,
    exploration_accuracy: 0,
    practice_accuracy: 0,
    dictation_accuracy: 0,
    retention_accuracy_7d: 0,
    retention_accuracy_14d: 0,
    retention_accuracy_30d: 0,
    retention_accuracy_60d: 0,
    lapse_rate: 0,
    review_debt_words: 19,
    known_provisional_words: 0,
    stable_known_words: 0,
    due_audit_words: 0,
    llm_suggested_words: 0,
    llm_pending_suggestions: 0,
    content_generated_words: 0,
    audio_generated_words: 0,
    pattern_error_rates: [],
    recent_mode_accuracy: [],
    accuracy_trend: Array.from({ length: 14 }, (_, index) => ({
      day: `2026-07-${String(index + 18).padStart(2, "0")}`,
      total_attempts: 0,
      correct_attempts: 0,
      accuracy: 0
    }))
  },
  words_learned: 0,
  accuracy: 0,
  practice_time_seconds: 0,
  recent_activity: [],
  achievements: [],
  daily_plan: {
    recommended_mode: "diagnostic",
    recommended_reason: "Start with a short diagnostic so the trainer can build a focused practice queue.",
    mode_scores: { diagnostic: 100, practice: 0, review_due: 0, exploration: 0, dictation: 0 },
    due_reviews: 0,
    mistake_words: 0,
    new_words: 19,
    dictation_ready: 0
  }
};

export const diagnosticSession = {
  session_id: 1,
  session_type: "diagnostic",
  total_items: 1,
  completed_items: 0,
  items: [
    {
      session_item_id: 1,
      word_id: 1,
      term: "definitely",
      item_type: "review_word",
      mode: "diagnostic",
      prompt_text: "Listen to the word and type its spelling.",
      source_reason: "starter diagnostic",
      queue_reason: "starter diagnostic",
      status: "pending",
      audio_ready: true,
      choices: null,
      short_meaning: "Without doubt; clearly and certainly.",
      part_of_speech: "adverb",
      chunked_form: "de-fin-ite-ly",
      phonetic_hint: null,
      difficulty_score: 0.5
    }
  ]
};

export const readyEnvironment = {
  status: "ready",
  database_backend: "sqlite",
  database_target: "Local SQLite",
  checks: [
    { key: "api", label: "Backend API", status: "ready", required: true, detail: "The API is responding.", action: null },
    { key: "database", label: "Database connection", status: "ready", required: true, detail: "Local SQLite accepted a test query.", action: null },
    { key: "schema", label: "Database schema", status: "ready", required: true, detail: "Schema and migrations are current.", action: null },
    { key: "openai", label: "OpenAI", status: "ready", required: false, detail: "An OpenAI API key is configured.", action: null },
    { key: "oxford", label: "Oxford source PDFs", status: "ready", required: false, detail: "All Oxford source PDFs are available.", action: null },
    { key: "audio_cache", label: "Audio cache", status: "ready", required: false, detail: "The audio cache is writable.", action: null }
  ]
};

export const readySettings = {
  id: 1,
  theme: "light",
  tts_voice: "alloy",
  tts_model: "gpt-4o-mini-tts",
  ai_model: "gpt-4o-mini",
  ai_generation_enabled: true,
  content_bulk_limit: 100
};

export const oxfordLoadStatus = {
  target_words: 5000,
  loaded_words: 4,
  remaining_words: 4996,
  next_batch_size: 100,
  source_available: true
};

export const pendingBulkStatus = {
  total_words: 4,
  generated: 0,
  pending: 4,
  failed: 0
};

export const practiceSession = {
  session_id: 2,
  session_type: "practice",
  total_items: 1,
  completed_items: 0,
  items: [
    {
      session_item_id: 2,
      word_id: 1,
      term: "definitely",
      item_type: "review_word",
      mode: "practice",
      prompt_text: "Listen to the word and type its spelling.",
      source_reason: "recent miss",
      queue_reason: "recent miss",
      status: "pending",
      audio_ready: true,
      choices: null,
      short_meaning: "Without doubt; clearly and certainly.",
      part_of_speech: "adverb"
    }
  ]
};

export const dictationSession = {
  session_id: 3,
  session_type: "dictation",
  total_items: 1,
  completed_items: 0,
  items: [
    {
      session_item_id: 3,
      word_id: 1,
      term: "definitely",
      item_type: "sentence_dictation",
      mode: "dictation",
      prompt_text: "I definitely finished the task.",
      source_reason: "recent miss",
      queue_reason: "recent miss",
      status: "pending",
      audio_ready: true,
      choices: null
    }
  ]
};

export function dashboardWithStats(overrides: Partial<typeof firstRunDashboard.stats>) {
  return {
    ...firstRunDashboard,
    stats: {
      ...firstRunDashboard.stats,
      ...overrides
    }
  };
}
