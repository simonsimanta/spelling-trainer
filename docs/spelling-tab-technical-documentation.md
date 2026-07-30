# Spelling Trainer Technical Documentation

Last updated: 2026-05-24

## Purpose

The app is now a dedicated single-user spelling trainer. The first development pass focused on product flow, UI/UX, learning interactions, progress tracking, and clear separation between the three core learning jobs:

- Exploration: introduce new words from Oxford 5K or suggested difficult words.
- Practice: repair missed spellings with audio-only word spelling.
- Dictation: type a sentence or phrase that contains a known trouble word.

The app is intentionally not a general vocabulary flashcard tool. The main training target is spelling recall: the learner hears audio, uses meaning for context, types from memory, and corrects mistakes before moving on.

## Current Product Model

### Primary Learner Flow

1. Load Oxford words from the local Oxford PDFs in Settings.
2. Optionally pre-generate learning content and audio cache for loaded Oxford words.
3. Use Exploration to work through the Oxford 5K in order, or AI/difficult-word suggestions.
4. Exploration plays word audio and shows meaning/part of speech, but hides the spelling before submit.
5. If the learner spells correctly, the word is marked as explored/seen and does not enter Practice immediately.
6. If the learner spells incorrectly, the word enters the review/practice queue and the UI requires a correction.
7. Practice pulls only from missed/due/trouble words. It never reveals the target spelling before submit.
8. Dictation pulls from the same mistake/review pool and asks for a full sentence or phrase.
9. Dashboard, Progress, Achievements, Word Lists, and Settings give tracking and maintenance controls.

### Navigation Tabs

- Dashboard: summary analytics, streak, points, loaded/explored/mastered progress, funnel charts, queue health, mode shortcuts, recent activity.
- Exploration: audio-first new-word exploration from Oxford 5K, AI Difficult Words, or Mixed pool.
- Practice: focused audio word spelling for repair/review.
- Dictation: sentence or phrase typing with strict target-word grading.
- Word Lists: Core 5K, personal words, trouble words, mastered words, and manual personal word add.
- Progress: compact progress summary and recent activity.
- Achievements: progress badges for exploration, practice, dictation, accuracy, and streaks.
- Settings: theme/voice/model/batch controls, Oxford loader, AI content cache, and audio cache tools.

## Architecture

### Runtime Stack

- Frontend: Vite + React + TypeScript in `web/`.
- Backend: FastAPI in `app/backend/api.py`.
- Persistence: SQLAlchemy models in `app/backend/models.py`.
- Schemas: Pydantic response/request models in `app/backend/schemas.py`.
- Shared domain logic: `app/backend/repository.py`.
- Focused spelling service wrappers: `app/backend/spelling/`.
- Local source data: Oxford PDFs in `data/The_Oxford_3000.pdf` and `data/The_Oxford_5000.pdf`.
- Local generated audio cache: `data/spelling_audio/*.mp3`.

### Frontend Shape

The first React build is mostly implemented in `web/src/App.tsx`, with shared API helpers in `web/src/api.ts`, shared TypeScript shapes in `web/src/types.ts`, and CSS-only layout/charts in `web/src/styles.css`.

This is acceptable for the first product pass, but the next engineering pass should split `App.tsx` into feature components:

- `DashboardView`
- `ExplorationView`
- `PracticeView`
- `DictationView`
- `WordListsView`
- `SettingsView`
- shared feedback, progress ring, metric card, modal, audio prompt, and form controls

### Backend Shape

`app/backend/api.py` defines the public HTTP surface. Thin spelling modules delegate to repository functions:

- `spelling/analytics.py`: overview, analytics, Core 5K overview, mode overview.
- `spelling/attempts.py`: attempt submit and correction submit wrappers.
- `spelling/audio.py`: TTS generation, audio cache, audio bulk status/preview/generation.
- `spelling/oxford.py`: Oxford PDF parsing and batch loading.
- `spelling/sessions.py`: session create/read wrappers.
- `spelling/suggestions.py`: suggestions list/update wrappers.
- `spelling/words.py`: spelling word list/create wrappers.

Most learning logic still lives in `repository.py`. This is the largest remaining architecture debt.

## Public API Surface

### App-Level APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health check. |
| `GET` | `/profile` | Single-user profile, streak, points, goal. |
| `PATCH` | `/profile` | Update profile fields. |
| `GET` | `/settings` | Theme, TTS voice/model, AI model, batch size. |
| `PATCH` | `/settings` | Update settings. |
| `GET` | `/dashboard` | Main dashboard payload with stats, activity, achievements. |
| `GET` | `/achievements` | Full achievement list. |

### Spelling Word And Oxford APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/spelling/words?level=...` | List active words by list/filter: `core5k`, `personal`, `trouble`, `mastered`, or raw level. |
| `POST` | `/spelling/words` | Add a personal/manual word. |
| `GET` | `/spelling/word-content/{word_id}` | Get or generate cached meaning, IPA, examples, and family. |
| `GET` | `/spelling/oxford/load-status` | Show loaded Oxford count, remaining count, batch size, and PDF availability. |
| `POST` | `/spelling/oxford/load-batch` | Load the next N Oxford words from local PDFs without generating content/audio. |

### Exploration APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/spelling/exploration/next?pool=oxford|suggested|mixed` | Get the next available exploration word and content. |
| `POST` | `/spelling/exploration/action` | Backend support for `known`, `practice`, and `viewed` actions. The current UI mostly uses spelling attempts instead. |
| `POST` | `/spelling/placement/attempt` | Backend placement action for marking a word known or adding it to practice. |

### Session And Attempt APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/spelling/sessions` | Canonical session creator for practice, dictation, review, and legacy session types. |
| `GET` | `/spelling/sessions/{session_id}` | Read session state and ordered items. |
| `POST` | `/spelling/attempts` | Submit exploration/practice/dictation spelling attempt. |
| `POST` | `/spelling/attempts/{attempt_id}/correct` | Submit required correction after a wrong answer. |

### Analytics APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/spelling/overview` | Due today, hard words, attempts today, points today. |
| `GET` | `/spelling/analytics` | Mastered/learning/trouble, first-try accuracy, top patterns. |
| `GET` | `/spelling/core5k/overview` | Core 5K counts and coverage. |
| `GET` | `/spelling/overview/modes` | Per-mode attempt accuracy. |
| `GET` | `/spelling/daily-plan` | Recommended mode and queue counts. |
| `GET` | `/spelling/costs` | Feedback/audio cache token and file counters. |

### Suggestions, Content, And Audio APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/spelling/suggestions?status=pending` | List suggested difficult words. |
| `PATCH` | `/spelling/suggestions/{suggestion_id}` | Mark suggestion `approved`, `rejected`, or `ignored`. |
| `GET` | `/spelling/content/bulk-status` | Count loaded Oxford words with generated/pending/failed content. |
| `GET` | `/spelling/content/bulk-preview?limit=100` | Preview content generation batch and estimated API calls. |
| `POST` | `/spelling/content/bulk-generate` | Generate cached learning content for loaded Oxford words. |
| `GET` | `/spelling/audio?text=...&voice=alloy&model=gpt-4o-mini-tts` | Return or generate the selected TTS variant; omitted voice/model values use saved settings. |
| `POST` | `/spelling/audio/preload` | Preload text using request voice/model values or saved settings. |
| `GET` | `/spelling/audio/bulk-status?voice=alloy&model=gpt-4o-mini-tts` | Count generated/pending/failed audio for one selected variant. |
| `GET` | `/spelling/audio/bulk-preview?limit=100&voice=alloy&model=gpt-4o-mini-tts` | Preview audio generation batch. |
| `POST` | `/spelling/audio/bulk-generate` | Generate cached OpenAI TTS files for loaded Oxford words. |

### Removed Old App APIs

The spelling-only app should no longer expose old habit/journal surfaces:

- `/categories`
- `/habits`
- `/logs`
- `/journal`
- `/summary`
- `/metrics`

Tests currently assert these return 404.

## Data Model

### Single-User App Tables

- `learner_profile`: points, streaks, practice time, daily goal, last practice date.
- `app_settings`: theme, TTS voice/model, AI model, AI generation flag, batch size.
- `activity_events`: recent activity stream for dashboard/progress.
- `achievements`: badge definitions, progress, unlock time.

### Core Spelling Tables

- `spelling_words`: canonical word rows. Contains term, source, level, meaning hints, IPA, example, difficulty, source list, mastery state, and exploration timestamps.
- `spelling_word_sources`: Oxford source mapping. This is how Oxford 5K coverage stays honest. Rows use `oxford_3000` and/or `oxford_5000`.
- `spelling_word_content`: generated/cached learning content: meaning, IPA, part of speech, examples, word family, status/error.
- `spelling_reviews`: SRS/review state: due date, interval, incorrect count, lapse count, forced correction, stage, mastery score.
- `spelling_attempts`: every spelling submission and correction attempt, including mode, correctness, points, diff JSON, feedback, session links.
- `spelling_sessions`: session header with type, totals, completion, first-try counts.
- `spelling_session_items`: ordered session items, prompt text, item type, status, choices for legacy types.
- `spelling_suggestions`: difficult/similar word suggestions and statuses.
- `spelling_patterns`, `spelling_word_patterns`, `spelling_user_pattern_stats`: pattern taxonomy and learner error rates.
- `spelling_confusion_groups`, `spelling_confusion_group_words`: static related/confusable word groups.
- `spelling_audio_manifest`: generated audio status per word/voice/model.
- `spelling_feedback_cache`: cached tutor feedback keyed by word, normalized attempt, and error pattern.

### Important Source Pools

- Oxford pool: words with `spelling_word_sources.source_name in ('oxford_3000', 'oxford_5000')`.
- Suggested pool: words with `source in ('llm', 'llm_suggestion')`, `level='suggested'`, or linked suggestions.
- Personal pool: manual words created through Word Lists.
- Practice queue: active, not skipped words with forced correction, previous incorrect/lapse, trouble stage, or due review stage.

## Oxford Loading, Content, And Audio Cache

The Settings tab now makes the maintenance flow explicit:

```text
Load Oxford words -> Generate AI learning content -> Generate audio cache
```

### Oxford Loader

`POST /spelling/oxford/load-batch`:

- Reads `data/The_Oxford_3000.pdf` and `data/The_Oxford_5000.pdf`.
- Extracts normalized terms using the PDF parser in `app/backend/spelling/oxford.py`.
- Preserves rank order as parsed from Oxford 3000 first, then Oxford 5000.
- Skips words already mapped to Oxford sources.
- Creates or updates `spelling_words`.
- Creates `spelling_word_sources` mappings.
- Does not generate learning content.
- Does not generate audio.

`GET /spelling/oxford/load-status` returns:

- `target_words`: fixed at `5000`.
- `loaded_words`: distinct words with Oxford source rows.
- `remaining_words`: `5000 - loaded_words`, floored at zero.
- `next_batch_size`: saved Settings batch size.
- `source_available`: whether both local PDFs exist.

### Batch Size

The Settings `Batch size` value controls three separate manual operations:

- how many Oxford words to load;
- how many loaded Oxford words to generate learning content for;
- how many loaded Oxford words to generate audio for.

Default is 100 for development. It is a cap, not a promise. If only 20 pending items exist, a batch size of 100 processes 20.

### AI Learning Content

Content generation caches:

- meaning;
- IPA;
- part of speech;
- example sentences;
- word family.

If `OPENAI_API_KEY` is missing, content generation falls back to deterministic local content and still marks content as generated. Exploration also calls `get_word_content`, so content can be generated on demand when a word is opened.

### Audio Cache

Audio generation uses OpenAI TTS and stores MP3 files in `data/spelling_audio`. Cache filenames are SHA-256 hashes of normalized text, voice, and model.

- Word audio uses the isolated word.
- Dictation audio uses the full sentence/phrase prompt.
- Bulk audio generation and status are scoped to loaded Oxford words and the selected voice/model variant.
- Legacy manifests that point at the old text-only cache path are regenerated into a variant-specific file.
- On-demand `GET /spelling/audio` uses saved TTS settings unless explicit voice/model query parameters are provided.
- Missing/invalid credentials, quota/rate limits, network failures, and provider failures produce actionable UI messages.

## Learning Logic

### Exploration

Exploration is for discovering and testing words before they enter the repair loop.

Current UI behavior:

- User chooses `Oxford 5K`, `AI Difficult Words`, or `Mixed`.
- App loads the next word with content.
- The spelling is hidden before submit.
- User hears audio, sees meaning and part of speech, and types the spelling.
- Correct answer reveals the word, shows feedback, records an exploration attempt, awards points, and does not put the word in Practice immediately.
- Wrong answer reveals the word, shows diff/feedback/chunking/mnemonic/example, creates review state, creates suggestions, and requires correction before Next.

Exploration target selection:

- Oxford pool: loaded Oxford words not already attempted in exploration, not known-skipped, not mastered.
- Suggested pool: auto-added/suggested words not already attempted in exploration, not known-skipped, not mastered.
- Mixed pool: suggested words first, then Oxford words, de-duplicated.

### Practice

Practice is audio-only word spelling. It intentionally removed multiple choice, fill-in-the-blank, scramble, hints, and skip controls from the main UI.

Session creation:

- Frontend posts `POST /spelling/sessions` with `session_type='practice'`, `target_size=8`.
- Backend selects from the review/mistake queue only.
- Practice items use `item_type='review_word'`.
- Session item includes `short_meaning` and `part_of_speech` so the frontend does not need a per-item content fetch.

Practice UI:

- Shows question progress and score summary.
- Plays audio for the hidden target word.
- Shows meaning and part of speech.
- Uses a large spelling input with browser spellcheck/autocomplete/autocorrect disabled.
- Shows answer overview tiles.
- Shows current streak and a goal panel.
- Blocks Next after wrong answer until correction is submitted.

### Dictation

Dictation is sentence or phrase typing, not isolated word spelling.

Session creation:

- Frontend posts `POST /spelling/sessions` with `session_type='dictation'`, `target_size=10`.
- Backend selects from the same review/mistake queue.
- Items use `item_type='sentence_dictation'`.
- `prompt_text` is the example sentence or fallback sentence.
- `term` is still the target word.

Grading:

- Dictation returns separate `target_spelling_correct`, `sentence_complete`, and `sentence_similarity` outcomes.
- Target matching is case-insensitive and token-based while preserving meaningful apostrophes and hyphens.
- Sentence completeness compares normalized token sequences, so capitalization and surrounding punctuation do not lower the score.
- `is_correct`, points, session completion, activity accuracy, and SRS/mastery progression use target spelling only.
- Sentence completeness and similarity are feedback signals and do not advance or penalize spelling mastery.
- Wrong target spelling requires correction before moving on.

### Review And SRS

Stages:

- `new`
- `learning`
- `review`
- `trouble`
- `mastered`

Normal SRS intervals:

```text
[0, 1, 3, 7, 14, 30, 60]
```

Hard SRS intervals:

```text
[0, 1, 2, 4, 7, 14, 30]
```

Correct attempt:

- Awards 3 points for a first-try answer without hint/reveal.
- Awards fewer points for retries or hinted/revealed cases in backend compatibility paths.
- Increases consecutive correct and mastery score.
- Slightly raises ease factor.
- Schedules next due date based on adaptive interval.
- Updates profile streak and points.
- Writes activity event.
- Updates achievements.

Wrong attempt:

- Awards 0 points.
- Increments incorrect count and lapse count.
- Lowers mastery score and ease factor.
- Makes word due today.
- Sets `forced_correction_required=true`.
- Builds word-level diff JSON.
- Caches/fetches tutor feedback.
- Creates difficult/similar word suggestions.
- Writes activity event.
- Updates achievements.

Correction attempt:

- Correct correction awards 1 point and unblocks the item.
- Correction keeps the word due today/soon.
- Backend supports skip availability after repeated failed corrections, but the current UI does not expose a skip action.

## Feedback And Suggestions

### Error Patterns

The backend classifies wrong attempts as:

- `missing_letter`
- `extra_letter`
- `close_spelling`
- `pattern_confusion`
- `none` for correct attempts

It maps patterns into broader taxonomy such as:

- double consonants;
- ie/ei confusion;
- silent letters;
- homophone/confusion fallback.

### AI Tutor Feedback

Feedback is cached in `spelling_feedback_cache` by:

- word id;
- normalized attempt text;
- error pattern.

When `OPENAI_API_KEY` is set, the backend calls the Responses API for short spelling feedback. Without a key or on errors, deterministic fallback text is returned.

Frontend feedback rendering shows:

- correctness and points;
- tutor/fallback text;
- diff chips for wrong word attempts;
- sentence diff for dictation;
- chunking;
- memory hook;
- example sentence.

Raw `diff_json` is not shown to the learner.

### Suggested Difficult Words

The current implementation auto-adds suggestions using deterministic confusion groups and common difficult-word lists. Suggested words are stored as `source='llm_suggestion'` and suggestions get status `auto_added`, `pending`, `approved`, `rejected`, or `ignored`.

Important: despite the product label "AI Difficult Words", the current suggestion creation logic is not yet true LLM generation. It is a first-pass deterministic substitute that can later be replaced or augmented with LLM-generated near-neighbor words based on the learner's actual error patterns.

## Dashboard Metrics

`GET /dashboard` returns a single payload so the frontend does not need to call many endpoints on dashboard load.

Main stats:

- `oxford_target_words`: fixed `5000`.
- `oxford_loaded_words`: loaded Oxford source rows.
- `oxford_explored_words`: Oxford words with `introduced_at`.
- `practice_distinct_words`: distinct words attempted in Practice.
- `dictation_distinct_words`: distinct words attempted in Dictation.
- `mastered_words`: review rows in mastered stage.
- `learning_words`: review rows in learning/review stage.
- `trouble_words`: review rows in trouble stage.
- `due_today_words`: reviews due today or earlier.
- `forced_correction_words`: words currently blocked by correction.
- `practice_queue_words`: forced, wrong, trouble, lapse, or due review words.
- `dictation_ready_words`: currently equal to practice queue words.
- `first_try_accuracy`: all first-try attempt accuracy.
- `practice_accuracy`: practice first-try accuracy.
- `dictation_accuracy`: dictation first-try accuracy.
- `llm_suggested_words`: active/pending/approved/auto-added suggestions.
- `llm_pending_suggestions`: pending or auto-added suggestions.
- `content_generated_words`: generated content among loaded Oxford words.
- `audio_generated_words`: generated audio among loaded Oxford words.

Dashboard charts:

- Learning Funnel: Oxford Loaded -> Explored -> Practiced -> Mastered.
- Mastery Breakdown: New / Learning / Trouble / Mastered.
- Queue Health: Due Today / Trouble / Forced Correction / Dictation Ready.
- Mode Accuracy: Exploration / Practice / Dictation.

Known metric caveat: the current frontend labels the first Mode Accuracy row as "Exploration", but it uses `first_try_accuracy`, which is all-mode first-try accuracy. This should become an explicit `exploration_accuracy` stat or use `/spelling/overview/modes`.

## Settings UX

Settings has three jobs:

1. General settings:
   - theme;
   - TTS voice;
   - batch size;
   - AI generation enabled;
   - advanced TTS model;
   - advanced AI model.
2. Oxford 5K Loader:
   - loaded/target/remaining counts;
   - source PDF ready/missing status;
   - load next batch button;
   - last import result.
3. Advanced Content & Audio Cache:
   - word learning content status and preview/confirm generation;
   - word audio cache status and preview/confirm generation;
   - generated/pending/failed counts;
   - quota warning via estimated API calls.

Disabled cache button labels are meaningful:

- `Preview Content Batch` or `Preview Audio Batch` when pending loaded words exist.
- `Load More Oxford Words First` when all loaded words are already cached but not all 5000 are loaded.
- `All Loaded Words Cached` when all target words are loaded and cached.

## Frontend Interaction Details

- All spelling/correction/dictation inputs use `spellCheck={false}`, `autoComplete="off"`, `autoCorrect="off"`, and `autoCapitalize="off"` to avoid browser spelling help.
- Audio errors appear inline as warning banners.
- Practice and Exploration hide the target spelling before submit.
- Practice does not expose hints or skip.
- Previous in Practice is review-only in behavior because completed items cannot be resubmitted in the current UI.
- The app uses CSS-only charts and lucide icons, with no charting dependency.
- The UI is responsive through CSS media queries that stack panels and grids on smaller screens.

## Configuration And Local Development

Environment:

- `DATABASE_URL`: defaults to `sqlite:///./data/spelling.db`.
- `OPENAI_API_KEY`: enables TTS and AI feedback/content.
- `OPENAI_MODEL`: fallback model setting used by feedback paths.
- `VITE_API_BASE_URL`: frontend API target, default `http://127.0.0.1:8000`.

Install/start:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
cd web
npm install
cd ..
./start_local.sh
```

Useful checks:

```bash
.venv/bin/pytest tests/backend/test_spelling_api.py
cd web
npm run build
```

## Current Test Coverage

Primary automated tests are in `tests/backend/test_spelling_api.py`.

Covered:

- spelling-only public app routes and removed habit/journal routes returning 404;
- dashboard stats shape;
- LLM/suggested words separate from Oxford coverage;
- Oxford loader status and batch import;
- Exploration Oxford ordering and known action support;
- suggested-word exploration pool;
- content/audio preview endpoints;
- content/audio generation result shapes;
- practice and dictation session item semantics;
- practice empty queue;
- wrong exploration attempt entering Practice;
- dictation target grading;
- correction flow;
- attempt scoring and activity/dashboard updates;
- content and audio bulk generation with monkeypatched audio generation.

Frontend verification is currently manual/browser-based:

- Vite build must pass;
- Settings renders loader and cache controls;
- loading an Oxford batch refreshes content/audio pending counts;
- Practice hides target spelling;
- Exploration hides target spelling before submit;
- Dictation plays sentence text.

## Known Gaps And Improvement Opportunities

### Product / Learning Logic

- Add a true "Known on first try" policy for Exploration that differentiates "correct once" from "mastered forever".
- Decide whether Exploration should expose a deliberate "I know this, skip it" action again. Backend supports it, current UI does not.
- Replace deterministic difficult-word suggestions with LLM-generated words based on actual error patterns, while keeping Oxford coverage separate.
- Add clearer progression rules for when a word graduates from Practice to Dictation.
- Add spaced dictation scheduling separate from practice queue if dictation becomes a higher-level skill.
- Add phonetic or syllable metadata only after submit, not before, if it risks revealing spelling.

### Backend / Architecture

- Split `repository.py` into focused modules: content, dashboard, sessions, attempts, review/SRS, suggestions, profile/settings.
- Move legacy mini-game item types behind compatibility-only code or remove once no clients depend on them.
- Make `ai_generation_enabled` actually gate OpenAI content generation. It is currently stored in settings, but content generation still uses OpenAI when a key is present.
- Add an explicit `exploration_accuracy` dashboard stat.
- Consider background jobs for long content/audio batches before increasing batch size heavily.

### Frontend / UX

- Split the monolithic `App.tsx` into feature components and shared UI primitives.
- Add explicit loading/success/error states for every async action, not just Settings.
- In correction submit flows, respect `accepted=false` from the backend instead of assuming any correction post unblocks the item.
- Add accessible labels and keyboard focus review across all custom controls.
- Make Word Lists more operational: source filters, search, status columns, and actions for suggested words.
- Add visual distinction between Oxford loaded, Oxford explored, and generated content/audio on Word Lists.
- Add a small "why is this in Practice?" reason label from `source_reason` or review state.

### Data / Migration

- Historical Alembic revisions still include the previous habit/journal schema lineage. Public routes are removed, but the migration history is not fully spelling-only.
- Decide whether to create a fresh squashed spelling-only migration before the app becomes long-lived.
- The Oxford PDF parser is heuristic. If exact Oxford rank fidelity becomes important, switch to a structured source file.

## Mental Model For Future Improvements

Use this decision rule when adding features:

- If it introduces a new word, it belongs in Exploration.
- If it repairs a missed spelling, it belongs in Practice.
- If it tests spelling inside natural language, it belongs in Dictation.
- If it changes setup, caches, models, or import size, it belongs in Settings.
- If it explains progress or priority, it belongs in Dashboard/Progress.

The strongest current product idea is:

```text
Oxford 5K provides coverage.
Wrong attempts create the repair queue.
Repair queue drives Practice.
Practice/trouble words drive Dictation.
Error patterns create suggested difficult words.
Dashboard tells the learner what needs work next.
```
