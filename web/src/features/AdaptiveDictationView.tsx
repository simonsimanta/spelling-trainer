import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Headphones,
  Loader2,
  Mic,
  RotateCcw,
  Volume2,
  XCircle
} from "lucide-react";
import { CSSProperties, FormEvent, useEffect, useState } from "react";

import { getJson, playAudioPath, postJson } from "../api";
import type {
  Dashboard,
  DictationProgress,
  DictationSubmissionResult,
  SpellingSession,
  ViewKey
} from "../types";
import { DictationLibrary } from "./DictationLibrary";

const levels = ["sentence", "passage", "paragraph"] as const;

function label(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function AdaptiveDictationView({
  dashboard,
  onRefresh,
  onNavigate
}: {
  dashboard: Dashboard | null;
  onRefresh: () => Promise<void>;
  onNavigate: (view: ViewKey) => void;
}) {
  const [progress, setProgress] = useState<DictationProgress | null>(null);
  const [session, setSession] = useState<SpellingSession | null>(null);
  const [index, setIndex] = useState(0);
  const [attempt, setAttempt] = useState("");
  const [results, setResults] = useState<Record<number, DictationSubmissionResult>>({});
  const [playCount, setPlayCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadProgress() {
    const next = await getJson<DictationProgress>("/spelling/dictation/progress");
    setProgress(next);
  }

  useEffect(() => {
    loadProgress()
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load dictation progress."))
      .finally(() => setLoading(false));
  }, []);

  const current = session?.items[index];
  const result = current ? results[current.session_item_id] : null;
  const complete = Boolean(session && index >= session.items.length);

  async function start() {
    setLoading(true);
    setError(null);
    try {
      const created = await postJson<SpellingSession>("/spelling/sessions", {
        session_type: "dictation",
        target_size: 10,
        exercise_type: "mixed"
      });
      setSession(created);
      setIndex(0);
      setAttempt("");
      setResults({});
      setPlayCount(0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start dictation.");
    } finally {
      setLoading(false);
    }
  }

  async function play(segment?: number) {
    if (!current?.audio_url) return;
    const path = segment == null ? current.audio_url : `${current.audio_url}?segment=${segment}`;
    try {
      await playAudioPath(path);
      setPlayCount((value) => value + 1);
      setAudioError(null);
    } catch (reason) {
      setAudioError(reason instanceof Error ? reason.message : "Unable to play dictation audio.");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!session || !current || !attempt.trim() || result) return;
    setSubmitting(true);
    setError(null);
    try {
      const submitted = await postJson<DictationSubmissionResult>("/spelling/dictation/submissions", {
        session_id: session.session_id,
        session_item_id: current.session_item_id,
        attempt_text: attempt,
        replay_count: playCount
      });
      setResults((existing) => ({ ...existing, [current.session_item_id]: submitted }));
      if (submitted.session_complete) await loadProgress();
      await onRefresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to check the dictation.");
    } finally {
      setSubmitting(false);
    }
  }

  function moveTo(nextIndex: number) {
    const nextItem = session?.items[nextIndex];
    const nextResult = nextItem ? results[nextItem.session_item_id] : null;
    setIndex(nextIndex);
    setAttempt(nextResult?.attempt_text ?? "");
    setPlayCount(0);
    setAudioError(null);
  }

  function next() {
    moveTo(index + 1);
  }

  if (loading && !session) {
    return <section className="workbench centered"><Loader2 className="spin" size={44} /></section>;
  }

  if (!session) {
    const currentLevel = progress?.current_level ?? "sentence";
    const currentIndex = levels.indexOf(currentLevel);
    return (
      <section className="workbench dictation-home">
        <div className="workbench-head">
          <div className="round-icon orange"><Mic /></div>
          <div>
            <p className="eyebrow">Dictation</p>
            <h1>{label(currentLevel)} level</h1>
          </div>
        </div>

        <div className="dictation-level-track" aria-label="Dictation progression">
          {levels.map((item, itemIndex) => (
            <div className={itemIndex === currentIndex ? "current" : itemIndex < currentIndex ? "complete" : "locked"} key={item}>
              <span>{itemIndex < currentIndex ? <CheckCircle2 size={18} /> : itemIndex + 1}</span>
              <strong>{label(item)}</strong>
            </div>
          ))}
        </div>

        {error ? <div className="banner error">{error}</div> : null}
        <div className="dictation-start-band">
          <div>
            <strong>{progress?.completed_sessions_at_level ?? 0} sessions at this level</strong>
            <span>Target spelling {percent(dashboard?.stats.dictation_accuracy ?? 0)}</span>
          </div>
          <button className="large-action" onClick={start}>
            <Headphones size={19} /> Start {currentLevel}
          </button>
        </div>

        <DictationLibrary />
      </section>
    );
  }

  if (complete || !current) {
    const levelChanged = Object.values(results).some((item) => item.level_changed);
    return (
      <section className="workbench centered dictation-complete">
        <CheckCircle2 size={54} />
        <h1>{levelChanged ? `${label(progress?.current_level ?? "sentence")} unlocked` : "Dictation complete"}</h1>
        <p>{session.items.length} texts completed at {label(session.dictation_level ?? "sentence")} level.</p>
        <div className="center-actions">
          <button onClick={start}><RotateCcw size={17} /> Start another</button>
          <button className="secondary" onClick={() => onNavigate("progress")}>View progress</button>
        </div>
      </section>
    );
  }

  const itemLevel = current.dictation_level ?? session.dictation_level ?? "sentence";
  return (
    <section className="dictation-session">
      <header className="practice-title-row">
        <div className="workbench-head compact">
          <div className="round-icon orange"><Mic /></div>
          <div>
            <p className="eyebrow">{label(itemLevel)} dictation</p>
            <h1>Text {index + 1} of {session.items.length}</h1>
          </div>
        </div>
        <button className="secondary" onClick={() => setSession(null)}><ChevronLeft size={17} /> Exit</button>
      </header>

      {error ? <div className="banner error">{error}</div> : null}
      <div className="dictation-workspace">
        <main className="dictation-editor">
          <div className="dictation-audio-controls">
            <button className="listen-button" onClick={() => play()}>
              <Volume2 size={21} /> Play complete text
            </button>
            {current.segment_count > 1 ? (
              <div className="dictation-segments" aria-label="Sentence audio segments">
                {Array.from({ length: current.segment_count }, (_, segment) => (
                  <button
                    className="secondary icon-button"
                    key={segment}
                    onClick={() => play(segment)}
                    aria-label={`Play segment ${segment + 1}`}
                    title={`Segment ${segment + 1}`}
                  >
                    {segment + 1}
                  </button>
                ))}
              </div>
            ) : null}
            <span>{playCount} plays</span>
          </div>
          {audioError ? <div className="banner warn">Audio unavailable: {audioError}</div> : null}

          <form className="dictation-entry" onSubmit={submit}>
            <textarea
              autoCapitalize="sentences"
              autoComplete="off"
              autoCorrect="off"
              disabled={Boolean(result) || submitting}
              placeholder="Type everything you hear..."
              spellCheck={false}
              value={attempt}
              onChange={(event) => setAttempt(event.target.value)}
            />
            {!result ? <button disabled={!attempt.trim() || submitting}>Check dictation</button> : null}
          </form>

          {result ? <DictationResult result={result} /> : null}

          <div className="practice-navigation">
            <button className="secondary" disabled={index === 0} onClick={() => moveTo(Math.max(0, index - 1))}>
              <ChevronLeft size={17} /> Previous
            </button>
            <button disabled={!result} onClick={next}>
              {index + 1 === session.items.length ? "Finish" : "Next text"} <ChevronRight size={17} />
            </button>
          </div>
        </main>

        <aside className="dictation-session-progress">
          <strong>{label(itemLevel)}</strong>
          <span>{Object.keys(results).length} of {session.items.length} checked</span>
          <div className="question-progress"><i style={{ "--bar": `${((index + 1) / session.items.length) * 100}%` } as CSSProperties} /></div>
          <span>{current.source_reason}</span>
        </aside>
      </div>
    </section>
  );
}

function DictationResult({ result }: { result: DictationSubmissionResult }) {
  const metrics = [
    ["Target spelling", result.target_accuracy],
    ["Words", result.word_accuracy],
    ["Capitalisation", result.capitalization_accuracy],
    ["Punctuation", result.punctuation_accuracy]
  ] as const;
  return (
    <section className="dictation-result" aria-label="Dictation result">
      {result.level_changed ? <div className="banner success">Your dictation level changed to {label(result.current_level)}.</div> : null}
      <div className="dictation-metrics">
        {metrics.map(([metric, value]) => (
          <div key={metric}><span>{metric}</span><strong>{percent(value)}</strong></div>
        ))}
      </div>
      <div className="dictation-error-counts">
        <span>WER <strong>{percent(result.word_error_rate)}</strong></span>
        <span>Omissions <strong>{result.omissions}</strong></span>
        <span>Additions <strong>{result.additions}</strong></span>
        <span>Substitutions <strong>{result.substitutions}</strong></span>
      </div>
      <div className="dictation-target-results">
        {result.targets.map((target) => (
          <div className={target.is_correct ? "correct" : "incorrect"} key={target.target}>
            {target.is_correct ? <CheckCircle2 size={17} /> : <XCircle size={17} />}
            <span>{target.actual ?? "Omitted"}</span>
            <strong>{target.target}</strong>
          </div>
        ))}
      </div>
      <div className="dictation-comparison">
        <div><span>Your text</span><p>{result.attempt_text}</p></div>
        <div><span>Expected text</span><p>{result.expected_text}</p></div>
      </div>
    </section>
  );
}
