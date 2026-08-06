import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  Loader2,
  Mic,
  PenLine,
  Sparkles,
  Volume2,
  XCircle
} from "lucide-react";
import {
  CSSProperties,
  FormEvent,
  useEffect,
  useState
} from "react";

import { playAudioPath, postJson, prefetchAudioPath, prefetchAudioPaths } from "../api";
import type {
  AttemptResult,
  Dashboard,
  SessionItem,
  SpellingSession,
  ViewKey
} from "../types";

import { title } from "../utils/format";
import { practiceEmptyState } from "./guidance";
import { DictationLibrary } from "./DictationLibrary";


export function PracticeView({
  mode,
  dashboard,
  onRefresh,
  onNavigate,
  initialSession = null,
  onInitialSessionConsumed
}: {
  mode: "diagnostic" | "practice" | "dictation";
  dashboard: Dashboard | null;
  onRefresh: () => Promise<void>;
  onNavigate: (view: ViewKey) => void;
  initialSession?: SpellingSession | null;
  onInitialSessionConsumed?: () => void;
}) {
  const [session, setSession] = useState<SpellingSession | null>(initialSession);
  const [index, setIndex] = useState(0);
  const [attempt, setAttempt] = useState("");
  const [itemResults, setItemResults] = useState<Record<number, AttemptResult>>({});
  const [correction, setCorrection] = useState("");
  const [audioError, setAudioError] = useState<string | null>(null);
  const [audioPreparing, setAudioPreparing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const current = session?.items[index];
  const complete = session ? index >= session.items.length : false;
  const currentResult = current ? itemResults[current.session_item_id] : null;
  const isDictation = mode === "dictation";
  const isDiagnostic = mode === "diagnostic";

  useEffect(() => {
    if (initialSession) onInitialSessionConsumed?.();
  }, [initialSession, onInitialSessionConsumed]);

  useEffect(() => {
    const audioUrl = session?.items[index]?.audio_url;
    if (!session || !audioUrl) {
      setAudioPreparing(false);
      return;
    }
    let cancelled = false;
    setAudioPreparing(true);
    setAudioError(null);
    prefetchAudioPath(audioUrl)
      .catch((error) => {
        if (!cancelled) {
          setAudioError(error instanceof Error ? error.message : "Unable to prepare audio");
        }
      })
      .finally(() => {
        if (!cancelled) setAudioPreparing(false);
      });
    prefetchAudioPaths(
      session.items.slice(index + 1, index + 3).map((item) => item.audio_url)
    ).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [session, index]);

  async function start() {
    if (starting) return;
    setStarting(true);
    setStartError(null);
    try {
      const created = await postJson<SpellingSession>("/spelling/sessions", {
        session_type: mode,
        target_size: isDictation ? 10 : isDiagnostic ? 20 : 8,
        exercise_type: "mixed"
      });
      setSession(created);
      setIndex(0);
      setAttempt("");
      setItemResults({});
      setCorrection("");
      setAudioError(null);
      setSubmitError(null);
    } catch (error) {
      setStartError(error instanceof Error ? error.message : "Unable to start this session.");
    } finally {
      setStarting(false);
    }
  }

  async function submit(value?: string) {
    if (!current?.word_id) return;
    if (currentResult || submitting) return;
    const text = value ?? attempt;
    if (!text.trim()) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const submitted = await postJson<AttemptResult>("/spelling/attempts", {
        session_id: session?.session_id,
        session_item_id: current.session_item_id,
        word_id: current.word_id,
        attempt_text: text,
        mode,
        response_ms: 1000,
        used_hint: false,
        used_reveal: false
      });
      setItemResults((existing) => ({ ...existing, [current.session_item_id]: submitted }));
      setAttempt("");
      void onRefresh().catch(() => undefined);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unable to check this spelling.");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitCorrection(event: FormEvent) {
    event.preventDefault();
    if (!current || !currentResult?.attempt_id || !correction.trim() || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await postJson(`/spelling/attempts/${currentResult.attempt_id}/correct`, { correction_text: correction });
      setCorrection("");
      setItemResults((existing) => ({
        ...existing,
        [current.session_item_id]: { ...currentResult, forced_correction_required: false, allow_next: true }
      }));
      void onRefresh().catch(() => undefined);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unable to submit this correction.");
    } finally {
      setSubmitting(false);
    }
  }

  function next() {
    if (blocked) return;
    setAttempt("");
    setCorrection("");
    setAudioError(null);
    setSubmitError(null);
    setIndex((value) => value + 1);
  }

  function previous() {
    if (index === 0 || blocked) return;
    setAttempt("");
    setCorrection("");
    setAudioError(null);
    setSubmitError(null);
    setIndex((value) => Math.max(value - 1, 0));
  }

  async function playCurrentAudio() {
    if (!current?.audio_url) {
      setAudioError("Audio is not available for this item.");
      return;
    }
    if (audioPreparing) return;
    setAudioPreparing(true);
    try {
      await playAudioPath(current.audio_url);
      setAudioError(null);
    } catch (err) {
      setAudioError(err instanceof Error ? err.message : "Unable to play audio");
    } finally {
      setAudioPreparing(false);
    }
  }

  if (!session) {
    return (
      <section className="workbench">
        <div className="workbench-head">
          <div className={`round-icon ${isDictation ? "orange" : isDiagnostic ? "purple" : "blue"}`}>{isDictation ? <Mic /> : isDiagnostic ? <ListChecks /> : <PenLine />}</div>
          <div>
            <p className="eyebrow">{isDictation ? "Dictation Mode" : isDiagnostic ? "Diagnostic Mode" : "Practice Mode"}</p>
            <h1>{isDictation ? "Listen and type the sentence" : isDiagnostic ? "Find your weak spellings" : "Listen and spell the word"}</h1>
          </div>
        </div>
        <div className="start-panel">
          <p>
            {isDictation
              ? "Dictation uses phrases that contain words you have missed before."
              : isDiagnostic
              ? "Diagnostic tests useful words without correction blocking, then sends misses into Practice."
              : "Practice uses only words from your mistake and review queue."}
          </p>
          <button className="large-action" disabled={starting} onClick={start}>
            {starting ? <Loader2 className="spin" size={18} /> : null}
            {starting ? "Starting..." : isDictation ? "Start Dictation" : isDiagnostic ? "Start Diagnostic" : "Start Practice"}
            {!starting ? <ChevronRight size={18} /> : null}
          </button>
        </div>
        {startError ? <div className="banner error" role="alert">{startError}</div> : null}
        {isDictation ? <DictationLibrary /> : null}
      </section>
    );
  }

  if (session.items.length === 0) {
    const emptyState = practiceEmptyState(mode, dashboard);
    return (
      <section className="workbench centered">
        <Volume2 size={54} />
        <h1>{emptyState.title}</h1>
        <p>{emptyState.text}</p>
        <div className="center-actions">
          <button onClick={() => onNavigate(emptyState.primaryView)}>{emptyState.primaryLabel}</button>
          {emptyState.secondaryView ? (
            <button className="secondary" onClick={() => onNavigate(emptyState.secondaryView as ViewKey)}>
              {emptyState.secondaryLabel}
            </button>
          ) : null}
          <button className="secondary" onClick={() => setSession(null)}>Back</button>
        </div>
      </section>
    );
  }

  if (complete || !current) {
    return (
      <section className="workbench centered">
        <CheckCircle2 size={54} />
        <h1>Session complete</h1>
        <p>You finished {session.total_items} items.</p>
        <button disabled={starting} onClick={start}>
          {starting ? <Loader2 className="spin" size={18} /> : null}
          {starting ? "Starting..." : "Start another session"}
        </button>
        {startError ? <div className="banner error" role="alert">{startError}</div> : null}
      </section>
    );
  }

  const completedCount = Object.keys(itemResults).length;
  const correctCount = Object.values(itemResults).filter((item) => item.is_correct).length;
  const incorrectCount = Object.values(itemResults).filter((item) => !item.is_correct).length;
  const progress = Math.round((completedCount / session.items.length) * 100);
  const questionProgress = Math.round(((index + 1) / session.items.length) * 100);
  const blocked = Boolean(currentResult?.forced_correction_required && !currentResult.allow_next);

  if (mode === "practice" || mode === "diagnostic") {
    return (
      <section className="practice-screen">
        <div className="practice-title-row">
          <div className="workbench-head compact">
            <div className={`round-icon ${isDiagnostic ? "purple" : "blue"}`}>{isDiagnostic ? <ListChecks /> : <PenLine />}</div>
            <div>
              <h1>{isDiagnostic ? "Diagnostic Mode" : "Practice Mode"}</h1>
              <p>{isDiagnostic ? "Listen, spell, and let misses build your personal practice queue." : "Listen to the word and type the correct spelling."}</p>
            </div>
          </div>
          <button className="secondary exit-practice" onClick={() => setSession(null)}>
            <ChevronLeft size={18} /> {isDiagnostic ? "Exit Diagnostic" : "Exit Practice"}
          </button>
        </div>

        <div className="practice-layout polished">
          <div className="workbench practice-main polished">
            <div className="practice-session-top">
              <div>
                <strong>Question {index + 1} of {session.items.length}</strong>
                <div className="question-progress">
                  <i style={{ "--bar": `${questionProgress}%` } as CSSProperties} />
                </div>
              </div>
              <div className="practice-score">
                <strong>Score: {dashboard?.profile.points ?? 0}</strong>
                <span>Correct: {correctCount}</span>
                <span>Incorrect: {incorrectCount}</span>
                <span>Remaining: {Math.max(session.items.length - completedCount, 0)}</span>
              </div>
            </div>

            <PracticeExercise
              item={current}
              attempt={attempt}
              audioError={audioError}
              audioPreparing={audioPreparing}
              disabled={Boolean(currentResult) || submitting}
              playAudio={playCurrentAudio}
              setAttempt={setAttempt}
              submit={submit}
              submitError={submitError}
              submitting={submitting}
            />

            {currentResult ? <Feedback result={currentResult} /> : null}

            {blocked ? (
              <form className="correction-form practice-correction" onSubmit={submitCorrection}>
                <label>Type the correct spelling once to continue</label>
                <input
                  autoCapitalize="off"
                  autoComplete="off"
                  autoCorrect="off"
                  spellCheck={false}
                  value={correction}
                  onChange={(event) => setCorrection(event.target.value)}
                />
                <button disabled={submitting}>
                  {submitting ? <Loader2 className="spin" size={18} /> : null}
                  {submitting ? "Submitting..." : "Submit correction"}
                </button>
                {submitError ? <div className="banner error" role="alert">{submitError}</div> : null}
              </form>
            ) : null}

            <div className="practice-navigation">
              <button className="secondary" disabled={index === 0 || blocked} onClick={previous}>
                <ChevronLeft size={18} /> Previous
              </button>
              <button disabled={blocked || !currentResult} onClick={next}>
                {index + 1 >= session.items.length ? "Finish" : "Next"} <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <PracticeProgressPanel
            session={session}
            index={index}
            progress={progress}
            correctCount={correctCount}
            incorrectCount={incorrectCount}
            itemResults={itemResults}
            streak={dashboard?.profile.current_streak ?? 0}
          />
        </div>

        <div className="practice-goal-footer">
          <div><Sparkles size={24} /> <strong>Goal:</strong> {isDiagnostic ? "Find misses honestly. Wrong answers become practice." : "Score 80% or more to master this session."}</div>
          <button className="ghost" onClick={() => onNavigate("progress")}>
            View Goals <ChevronRight size={16} />
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="practice-layout">
      <div className="workbench practice-main">
        <div className="workbench-head compact">
          <div className={`round-icon ${mode === "dictation" ? "orange" : "blue"}`}>{mode === "dictation" ? <Mic /> : <PenLine />}</div>
          <div>
            <p className="eyebrow">{mode === "dictation" ? "Dictation Mode" : "Practice Mode"}</p>
            <h1>{mode === "dictation" ? "Sentence Dictation" : "Audio Spelling"}</h1>
          </div>
          <span className="pill">{index + 1} / {session.items.length}</span>
        </div>

        <Exercise attempt={attempt} disabled={Boolean(currentResult) || submitting} setAttempt={setAttempt} submit={submit} submitting={submitting} />

        <div className="audio-row">
          <button className="listen-button" disabled={audioPreparing} onClick={playCurrentAudio}>
            {audioPreparing ? <Loader2 className="spin" size={24} /> : <Volume2 size={24} />}
            {audioPreparing ? "Preparing audio..." : "Listen"}
          </button>
        </div>
        {audioError ? <div className="banner warn">Audio unavailable: {audioError}</div> : null}
        {submitError ? <div className="banner error" role="alert">{submitError}</div> : null}

        {currentResult ? <Feedback result={currentResult} /> : null}

        {blocked ? (
          <form className="correction-form" onSubmit={submitCorrection}>
            <label>Type the correct spelling once</label>
            <input
              autoCapitalize="off"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              value={correction}
              onChange={(event) => setCorrection(event.target.value)}
            />
            <button disabled={submitting}>
              {submitting ? <Loader2 className="spin" size={18} /> : null}
              {submitting ? "Submitting..." : "Submit correction"}
            </button>
          </form>
        ) : null}

        <div className="action-row">
          <button className="secondary" onClick={() => setSession(null)}>Exit</button>
          <button disabled={blocked || !currentResult} onClick={next}>Next <ChevronRight size={16} /></button>
        </div>
      </div>

      <aside className="progress-panel">
        <div className="progress-ring" style={{ "--progress": `${progress}%` } as CSSProperties}>
          <span>{progress}%</span>
        </div>
        <strong>Your Progress</strong>
        <span>{completedCount} of {session.items.length}</span>
        <div className="recent-words">
          {session.items.filter((item) => itemResults[item.session_item_id]).map((item) => (
            <span key={item.session_item_id}><CheckCircle2 size={14} /> {item.term}</span>
          ))}
          {!currentResult ? <span>Current word hidden</span> : null}
        </div>
      </aside>
    </section>
  );
}

function Exercise({
  attempt,
  disabled,
  setAttempt,
  submit,
  submitting
}: {
  attempt: string;
  disabled: boolean;
  setAttempt: (value: string) => void;
  submit: (value?: string) => Promise<void>;
  submitting: boolean;
}) {
  return (
    <div className="exercise-card">
      <p>Listen carefully and type the full sentence or phrase.</p>
      <div className="waveform"><i /><i /><i /><i /><i /></div>
      <input
        autoCapitalize="off"
        autoComplete="off"
        autoCorrect="off"
        disabled={disabled}
        placeholder="Type the sentence here..."
        spellCheck={false}
        value={attempt}
        onChange={(event) => setAttempt(event.target.value)}
      />
      <button disabled={disabled} onClick={() => submit()}>
        {submitting ? <Loader2 className="spin" size={18} /> : null}
        {submitting ? "Checking..." : "Submit"}
      </button>
    </div>
  );
}

function PracticeExercise({
  item,
  attempt,
  audioError,
  audioPreparing,
  disabled,
  playAudio,
  setAttempt,
  submit,
  submitError,
  submitting
}: {
  item: SessionItem;
  attempt: string;
  audioError: string | null;
  audioPreparing: boolean;
  disabled: boolean;
  playAudio: () => Promise<void>;
  setAttempt: (value: string) => void;
  submit: (value?: string) => Promise<void>;
  submitError: string | null;
  submitting: boolean;
}) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  return (
    <form className="practice-card" onSubmit={handleSubmit}>
      <div className="practice-audio-stage">
        <div className="waveform blue"><i /><i /><i /><i /><i /></div>
        <button className="audio-orb" disabled={audioPreparing} type="button" onClick={playAudio} aria-label={audioPreparing ? "Preparing word audio" : "Play word audio"}>
          {audioPreparing ? <Loader2 className="spin" size={34} /> : <Volume2 size={34} />}
        </button>
        <div className="waveform blue"><i /><i /><i /><i /><i /></div>
      </div>
      <strong>Listen to the word and type your answer.</strong>

      <div className="meaning-strip">
        <span>Meaning</span>
        <p>{item.short_meaning || "A word from your spelling practice queue."}</p>
        {item.part_of_speech ? <b>{title(item.part_of_speech)}</b> : null}
      </div>

      {item.queue_reason ? (
        <div className="queue-reason">
          <span>Why this is here</span>
          <strong>{title(item.queue_reason)}</strong>
        </div>
      ) : null}

      <input
        autoFocus
        autoCapitalize="off"
        autoComplete="off"
        autoCorrect="off"
        disabled={disabled}
        placeholder="Type the spelling here..."
        spellCheck={false}
        value={attempt}
        onChange={(event) => setAttempt(event.target.value)}
      />
      {audioError ? <div className="banner warn">Audio unavailable: {audioError}</div> : null}
      {submitError ? <div className="banner error" role="alert">{submitError}</div> : null}

      <div className="practice-card-actions">
        <button className="secondary" disabled={audioPreparing} type="button" onClick={playAudio}>
          {audioPreparing ? <Loader2 className="spin" size={18} /> : <Volume2 size={18} />}
          {audioPreparing ? "Preparing audio..." : "Hear Again"}
        </button>
        <button disabled={disabled || !attempt.trim()} type="submit">
          {submitting ? <Loader2 className="spin" size={18} /> : null}
          {submitting ? "Checking..." : "Check Answer"}
        </button>
      </div>
    </form>
  );
}

function PracticeProgressPanel({
  session,
  index,
  progress,
  correctCount,
  incorrectCount,
  itemResults,
  streak
}: {
  session: SpellingSession;
  index: number;
  progress: number;
  correctCount: number;
  incorrectCount: number;
  itemResults: Record<number, AttemptResult>;
  streak: number;
}) {
  const days = ["S", "M", "T", "W", "T", "F", "S"];
  return (
    <aside className="practice-side">
      <section>
        <h2>Your Progress</h2>
        <div className="progress-summary">
          <div className="progress-ring blue-ring" style={{ "--progress": `${progress}%` } as CSSProperties}>
            <span>{progress}%</span>
          </div>
          <div className="progress-legend">
            <span><b className="dot blue-dot" /> Correct <strong>{correctCount}</strong></span>
            <span><b className="dot red-dot" /> Incorrect <strong>{incorrectCount}</strong></span>
            <span><b className="dot gray-dot" /> Remaining <strong>{Math.max(session.items.length - correctCount - incorrectCount, 0)}</strong></span>
          </div>
        </div>
      </section>

      <section>
        <h2>Answer Overview</h2>
        <div className="answer-grid">
          {session.items.map((item, itemIndex) => {
            const itemResult = itemResults[item.session_item_id];
            const status = itemResult ? (itemResult.is_correct ? "correct" : "incorrect") : itemIndex === index ? "current" : "pending";
            return (
              <span className={`answer-tile ${status}`} key={item.session_item_id}>
                <b>{itemIndex + 1}</b>
                {status === "correct" ? <CheckCircle2 size={16} /> : null}
                {status === "incorrect" ? <XCircle size={16} /> : null}
                {status === "pending" ? <i /> : null}
              </span>
            );
          })}
        </div>
      </section>

      <section className="tip-panel">
        <Sparkles size={24} />
        <div>
          <h2>Tip</h2>
          <p>Use the meaning for context, then rely on the sound of the word and the spelling patterns you know.</p>
        </div>
      </section>

      <section>
        <h2>Current Streak</h2>
        <div className="streak-card">
          <strong>{streak} days</strong>
          <div>
            {days.map((day, dayIndex) => (
              <span className={dayIndex < Math.min(streak, days.length) ? "done" : ""} key={`${day}-${dayIndex}`}>
                {day}
              </span>
            ))}
          </div>
        </div>
      </section>
    </aside>
  );
}

export function Feedback({ result }: { result: AttemptResult }) {
  const feedbackText = result.llm_feedback?.replace(/\*\*/g, "");
  const isDictation = result.target_spelling_correct != null || result.sentence_diff_json != null;
  const targetSpellingCorrect =
    result.target_spelling_correct ??
    result.sentence_diff_json?.target_spelling_correct ??
    result.sentence_diff_json?.target_correct ??
    result.is_correct;
  const sentenceComplete =
    result.sentence_complete ??
    result.sentence_diff_json?.sentence_complete ??
    false;
  const sentenceSimilarity =
    result.sentence_similarity ??
    result.sentence_diff_json?.sentence_similarity ??
    0;
  const resultCorrect = isDictation ? targetSpellingCorrect : result.is_correct;
  let headline = result.is_correct ? `Correct. +${result.points_awarded} points` : "Not correct yet.";
  if (isDictation) {
    headline = targetSpellingCorrect
      ? `Target spelling correct. +${result.points_awarded} points`
      : "Target spelling needs work.";
  }

  return (
    <div className={resultCorrect ? "feedback correct" : "feedback wrong"}>
      <strong>{headline}</strong>
      {isDictation ? (
        <div className="dictation-outcomes" aria-label="Dictation results">
          <span className={targetSpellingCorrect ? "outcome-pass" : "outcome-review"}>
            <b>Target spelling</b>
            <strong>
              {targetSpellingCorrect ? <CheckCircle2 size={17} /> : <XCircle size={17} />}
              {targetSpellingCorrect ? "Correct" : "Needs practice"}
            </strong>
          </span>
          <span className={sentenceComplete ? "outcome-pass" : "outcome-review"}>
            <b>Sentence completeness</b>
            <strong>
              {sentenceComplete ? <CheckCircle2 size={17} /> : <XCircle size={17} />}
              {sentenceComplete ? "Complete" : `${Math.round(sentenceSimilarity * 100)}% match`}
            </strong>
          </span>
        </div>
      ) : null}
      {feedbackText ? <p>{feedbackText}</p> : null}
      {!resultCorrect && result.error_analysis ? (
        <div className="error-analysis-summary">
          <span>
            <b>Pattern</b>
            <strong>{result.error_analysis.pattern_label}</strong>
          </span>
          <span>
            <b>Analysis</b>
            <strong>{Math.round(result.error_analysis.confidence * 100)}% confidence</strong>
          </span>
          {result.error_analysis.transfer_words.length ? (
            <div>
              <b>Related practice words</b>
              <p>{result.error_analysis.transfer_words.map((item) => item.term).join(", ")}</p>
            </div>
          ) : null}
        </div>
      ) : null}
      {!resultCorrect && result.diff_json?.operations?.length ? (
        <div className="diff-row">
          {result.diff_json.operations.map((operation, index) => (
            <span key={index}>{String(operation.type)} {String(operation.expected ?? operation.actual ?? "")}</span>
          ))}
        </div>
      ) : null}
      {result.sentence_diff_json?.operations?.length ? (
        <div className="sentence-diff">
          <b>Sentence check</b>
          <div>
            {result.sentence_diff_json.operations.slice(0, 4).map((operation, index) => (
              <span key={index}>
                {String(operation.type)}: {String(operation.expected || operation.actual)}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <div className="hint-grid">
        <span><b>Chunking</b>{result.chunk_hint}</span>
        <span><b>Memory hook</b>{result.mnemonic}</span>
        <span><b>Example</b>{result.example_sentence}</span>
      </div>
    </div>
  );
}
