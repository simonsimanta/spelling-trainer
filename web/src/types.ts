export type ViewKey =
  | "dashboard"
  | "diagnostic"
  | "exploration"
  | "practice"
  | "dictation"
  | "wordLists"
  | "progress"
  | "achievements"
  | "settings";

export type Profile = {
  id: number;
  name: string;
  avatar: string;
  level_label: string;
  current_streak: number;
  best_streak: number;
  points: number;
  practice_time_seconds: number;
  daily_goal: number;
};

export type Overview = {
  due_today: number;
  hard_words: number;
  attempts_today: number;
  points_today: number;
};

export type Core5k = {
  total_words: number;
  attempted_words: number;
  mastered_words: number;
  in_learning_words: number;
  due_today_words: number;
  coverage_percent: number;
};

export type Activity = {
  id: number;
  event_type: string;
  title: string;
  detail?: string | null;
  points: number;
  accuracy?: number | null;
  created_at: string;
};

export type Achievement = {
  code: string;
  title: string;
  description: string;
  category: string;
  target: number;
  progress: number;
  unlocked_at?: string | null;
};

export type Dashboard = {
  profile: Profile;
  overview: Overview;
  core5k: Core5k;
  stats: {
    oxford_target_words: number;
    oxford_loaded_words: number;
    oxford_explored_words: number;
    practice_distinct_words: number;
    dictation_distinct_words: number;
    mastered_words: number;
    learning_words: number;
    trouble_words: number;
    due_today_words: number;
    forced_correction_words: number;
    practice_queue_words: number;
    dictation_ready_words: number;
    diagnostic_ready_words: number;
    diagnostic_tested_words: number;
    diagnostic_missed_words: number;
    diagnostic_accuracy: number;
    first_try_accuracy: number;
    exploration_accuracy: number;
    practice_accuracy: number;
    dictation_accuracy: number;
    retention_accuracy_7d: number;
    retention_accuracy_14d: number;
    retention_accuracy_30d: number;
    retention_accuracy_60d: number;
    lapse_rate: number;
    review_debt_words: number;
    known_provisional_words: number;
    stable_known_words: number;
    due_audit_words: number;
    llm_suggested_words: number;
    llm_pending_suggestions: number;
    content_generated_words: number;
    audio_generated_words: number;
    pattern_error_rates: Array<{
      code: string;
      label: string;
      total_attempts: number;
      incorrect_attempts: number;
      recent_error_rate: number;
    }>;
  };
  words_learned: number;
  accuracy: number;
  practice_time_seconds: number;
  recent_activity: Activity[];
  achievements: Achievement[];
};

export type Word = {
  id: number;
  term: string;
  level: string;
  source: string;
  is_active: boolean;
  short_meaning?: string | null;
  example_sentence?: string | null;
  ipa?: string | null;
  part_of_speech?: string | null;
  cefr_level?: string | null;
  mastery_state: string;
  diagnostic_status: string;
  priority_score: number;
  known_skipped: boolean;
};

export type WordContent = {
  word_id: number;
  term: string;
  meaning: string;
  ipa?: string | null;
  part_of_speech?: string | null;
  examples: string[];
  word_family: Array<{ term: string; label: string }>;
  status: string;
};

export type Exploration = {
  word: Word;
  content: WordContent;
  pool: "oxford" | "suggested" | "mixed";
  previous_word_id?: number | null;
  next_word_id?: number | null;
  progress_index: number;
  total_words: number;
};

export type SessionItem = {
  session_item_id: number;
  word_id?: number | null;
  term: string;
  item_type: string;
  mode: string;
  prompt_text: string;
  source_reason?: string | null;
  queue_reason?: string | null;
  selection_score: number;
  score_breakdown: Record<string, number>;
  status: string;
  audio_ready: boolean;
  choices?: string[] | null;
  short_meaning?: string | null;
  part_of_speech?: string | null;
  chunked_form?: string | null;
  phonetic_hint?: string | null;
  difficulty_score?: number | null;
};

export type SpellingSession = {
  session_id: number;
  session_type: string;
  total_items: number;
  completed_items: number;
  items: SessionItem[];
};

export type AttemptResult = {
  attempt_id?: number | null;
  word_id: number;
  term: string;
  attempt_text: string;
  is_correct: boolean;
  points_awarded: number;
  error_pattern?: string | null;
  next_due_date: string;
  llm_feedback?: string | null;
  chunk_hint: string;
  mnemonic: string;
  example_sentence: string;
  diff_json?: {
    operations?: Array<Record<string, string | number>>;
  } | null;
  sentence_diff_json?: {
    expected?: string;
    attempt?: string;
    target_word?: string;
    target_correct?: boolean;
    target_spelling_correct?: boolean;
    sentence_complete?: boolean;
    sentence_similarity?: number;
    operations?: Array<Record<string, string | number | boolean>>;
  } | null;
  target_spelling_correct?: boolean | null;
  sentence_complete?: boolean | null;
  sentence_similarity?: number | null;
  forced_correction_required: boolean;
  allow_next: boolean;
  mastery_state?: string | null;
  mastery_state_before?: string | null;
  mastery_state_after?: string | null;
  retry_prompt?: string | null;
  skip_available: boolean;
};

export type Settings = {
  id: number;
  theme: string;
  tts_voice: string;
  tts_model: string;
  ai_model: string;
  ai_generation_enabled: boolean;
  content_bulk_limit: number;
};

export type BulkStatus = {
  total_words: number;
  generated: number;
  pending: number;
  failed: number;
  voice?: string | null;
  model?: string | null;
};

export type BulkPreview = BulkStatus & {
  limit: number;
  will_process: number;
  estimated_api_calls: number;
  model: string;
  voice?: string | null;
};

export type BulkGenerateResult = {
  requested_limit: number;
  generated: number;
  cached: number;
  failed: number;
  remaining: number;
  voice?: string | null;
  model?: string | null;
};

export type OxfordLoadStatus = {
  target_words: number;
  loaded_words: number;
  remaining_words: number;
  next_batch_size: number;
  source_available: boolean;
};

export type OxfordLoadResult = {
  requested_limit: number;
  created: number;
  updated: number;
  skipped: number;
  loaded_words: number;
  remaining_words: number;
};
