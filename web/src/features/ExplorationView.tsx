import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Compass,
  Loader2,
  RefreshCcw,
  Volume2,
  XCircle
} from "lucide-react";
import {
  CSSProperties,
  FormEvent,
  useEffect,
  useState
} from "react";

import { getJson, playAudio, postJson } from "../api";
import type {
  AttemptResult,
  Dashboard,
  Exploration,
  ViewKey
} from "../types";

import { title } from "../utils/format";
import { explorationEmptyState } from "./guidance";
import type { ExplorationPool } from "./guidance";
import { Feedback } from "./PracticeView";

const explorationPools: Array<{ key: ExplorationPool; label: string; description: string }> = [
  { key: "oxford", label: "Oxford 5K", description: "Explore the core list in order." },
  { key: "suggested", label: "AI Difficult Words", description: "Words added from your error patterns." },
  { key: "mixed", label: "Mixed", description: "Blend suggested words with Oxford words." }
];

export function ExplorationView({
  dashboard,
  onRefresh,
  onNavigate
}: {
  dashboard: Dashboard | null;
  onRefresh: () => Promise<void>;
  onNavigate: (view: ViewKey) => void;
}) {
  const [data, setData] = useState<Exploration | null>(null);
  const [loading, setLoading] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [pool, setPool] = useState<ExplorationPool>("oxford");
  const [attempt, setAttempt] = useState("");
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [correction, setCorrection] = useState("");
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);

  async function load(wordId?: number | null, direction = "next", nextPool = pool) {
    setLoading(true);
    const params = new URLSearchParams({ pool: nextPool, direction });
    if (wordId) params.set("word_id", String(wordId));
    try {
      const next = await getJson<Exploration>(`/spelling/exploration/next?${params.toString()}`);
      setData(next);
      setEmptyMessage(null);
      setAudioError(null);
      setAttempt("");
      setResult(null);
      setCorrection("");
      await onRefresh();
    } catch (err) {
      setData(null);
      setEmptyMessage(nextPool === "suggested" ? "No AI difficult words are ready yet." : "No exploration words are available in this pool.");
    } finally {
      setLoading(false);
    }
  }

  async function playCurrentWord() {
    if (!data) return;
    try {
      await playAudio(data.word.term, { wordId: data.word.id, mode: "word" });
      setAudioError(null);
    } catch (err) {
      setAudioError(err instanceof Error ? err.message : "Unable to play audio");
    }
  }

  async function submitTrySpelling(event: FormEvent) {
    event.preventDefault();
    if (!data || result || !attempt.trim()) return;
    const submitted = await postJson<AttemptResult>("/spelling/attempts", {
      word_id: data.word.id,
      attempt_text: attempt,
      mode: "exploration",
      response_ms: 1000,
      used_hint: false,
      used_reveal: false
    });
    setResult(submitted);
    setAttempt("");
    await onRefresh();
  }

  async function submitExplorationCorrection(event: FormEvent) {
    event.preventDefault();
    if (!result?.attempt_id || !correction.trim()) return;
    await postJson(`/spelling/attempts/${result.attempt_id}/correct`, { correction_text: correction });
    setCorrection("");
    setResult({ ...result, forced_correction_required: false, allow_next: true });
    await onRefresh();
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [pool]);

  if (!data) {
    const emptyState = explorationEmptyState(pool, dashboard, emptyMessage);
    return (
      <section className="workbench centered">
        {loading ? <Loader2 className="spin" size={48} /> : <Compass size={54} />}
        <h1>{loading ? "Loading exploration" : emptyState?.title ?? "Exploration pool is empty"}</h1>
        <p>{emptyState?.text || "Choose a pool to continue exploring words."}</p>
        <div className="exploration-pool-tabs">
          {explorationPools.map((item) => (
            <button
              className={pool === item.key ? "active" : "secondary"}
              key={item.key}
              onClick={() => setPool(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        {!loading && emptyState ? (
          <div className="center-actions">
            <button onClick={() => onNavigate(emptyState.primaryView)}>{emptyState.primaryLabel}</button>
            {emptyState.secondaryView ? (
              <button className="secondary" onClick={() => onNavigate(emptyState.secondaryView as ViewKey)}>
                {emptyState.secondaryLabel}
              </button>
            ) : null}
          </div>
        ) : null}
      </section>
    );
  }

  const blocked = Boolean(result?.forced_correction_required && !result.allow_next);
  const revealed = Boolean(result);
  const stats = dashboard?.stats;
  const poolDescription = explorationPools.find((item) => item.key === pool)?.description;
  const progressTotal =
    pool === "oxford" ? stats?.oxford_target_words ?? 5000 : pool === "suggested" ? stats?.llm_suggested_words ?? data.total_words : data.total_words;
  const progressExplored = pool === "oxford" ? stats?.oxford_explored_words ?? 0 : data.progress_index - 1;
  const progressPercent = Math.round((progressExplored / Math.max(progressTotal, 1)) * 100);
  const recentRows = dashboard?.recent_activity.slice(0, 5) ?? [];

  return (
    <section className="exploration-screen">
      <div className="practice-title-row">
        <div className="workbench-head compact">
          <div className="round-icon green"><Compass /></div>
          <div>
            <h1>Exploration Mode</h1>
            <p>Listen, use the meaning for context, and test if you can spell the word.</p>
          </div>
        </div>
        <div>
          <button className="secondary" disabled={loading} onClick={() => load(null, "next")}>
            <RefreshCcw size={16} /> Refresh
          </button>
        </div>
      </div>

      <div className="exploration-pool-tabs">
        {explorationPools.map((item) => (
          <button
            className={pool === item.key ? "active" : "secondary"}
            key={item.key}
            onClick={() => setPool(item.key)}
          >
            <b>{item.label}</b>
            <span>{item.description}</span>
          </button>
        ))}
      </div>

      <div className="exploration-grid">
        <div className="workbench exploration-main">
          <form className="exploration-test-card" onSubmit={submitTrySpelling}>
            <div className="practice-audio-stage">
              <div className="waveform green-wave"><i /><i /><i /><i /><i /></div>
              <button className="audio-orb green-orb" type="button" onClick={playCurrentWord} aria-label="Play word audio">
                <Volume2 size={34} />
              </button>
              <div className="waveform green-wave"><i /><i /><i /><i /><i /></div>
            </div>
            <div>
              <h2>{revealed ? result?.term : "What word do you hear?"}</h2>
              <p>{revealed ? "Review the spelling and learning details before moving on." : poolDescription}</p>
            </div>
            <div className="meaning-strip">
              <span>Meaning</span>
              <p>{data.content.meaning}</p>
              {data.content.part_of_speech || data.word.part_of_speech ? <b>{title(data.content.part_of_speech || data.word.part_of_speech || "word")}</b> : null}
            </div>
            {!revealed ? (
              <>
                <input
                  autoFocus
                  autoCapitalize="off"
                  autoComplete="off"
                  autoCorrect="off"
                  placeholder="Type the spelling you hear..."
                  spellCheck={false}
                  value={attempt}
                  onChange={(event) => setAttempt(event.target.value)}
                />
                <div className="practice-card-actions">
                  <button className="secondary" type="button" onClick={playCurrentWord}>
                    <Volume2 size={18} /> Hear Again
                  </button>
                  <button disabled={!attempt.trim()} type="submit">Check Spelling</button>
                </div>
              </>
            ) : null}
            {audioError ? <div className="banner warn">Audio unavailable: {audioError}</div> : null}
          </form>

          {revealed ? (
            <article className={result?.is_correct ? "exploration-reveal correct" : "exploration-reveal wrong"}>
              <div className="word-title-row">
                <div>
                  <span className="eyebrow">{result?.is_correct ? "Known on first try" : "Added to Practice"}</span>
                  <h2>{result?.term}</h2>
                </div>
                <button className="icon-button" onClick={playCurrentWord}>
                  <Volume2 size={20} />
                </button>
              </div>
              <div className="pronunciation">
                <span>{data.content.ipa || data.word.ipa || "/ pronunciation /"}</span>
                <b>{data.content.part_of_speech || data.word.part_of_speech || "Word"}</b>
              </div>
              {result ? <Feedback result={result} /> : null}
              {result?.forced_correction_required && !result.allow_next ? (
                <form className="correction-form" onSubmit={submitExplorationCorrection}>
                  <label>Type the correct spelling once</label>
                  <input
                    autoCapitalize="off"
                    autoComplete="off"
                    autoCorrect="off"
                    spellCheck={false}
                    value={correction}
                    onChange={(event) => setCorrection(event.target.value)}
                  />
                  <button>Submit correction</button>
                </form>
              ) : null}
              <div className="learning-panel">
                <section>
                  <h3>Examples</h3>
                  {(data.content.examples.length ? data.content.examples : [data.word.example_sentence]).filter(Boolean).slice(0, 2).map((example) => (
                    <p key={example}>{example}</p>
                  ))}
                </section>
                <section>
                  <h3>Word Family</h3>
                  <div className="family-box compact">
                    <div>
                      {data.content.word_family.map((item) => (
                        <span key={`${item.term}-${item.label}`}>{item.term} ({item.label})</span>
                      ))}
                    </div>
                  </div>
                </section>
              </div>
            </article>
          ) : null}

          <div className="practice-navigation">
            <button className="secondary" disabled={!data.previous_word_id || blocked || revealed} onClick={() => load(data.word.id, "previous")}>
              <ChevronLeft size={18} /> Previous
            </button>
            <button disabled={blocked || !revealed} onClick={() => load(data.word.id, "next")}>
              Next Word <ChevronRight size={16} />
            </button>
          </div>
        </div>

        <aside className="practice-side">
          <section>
            <h2>Your Exploration Progress</h2>
            <div className="progress-summary">
              <div className="progress-ring green-ring" style={{ "--progress": `${progressPercent}%` } as CSSProperties}>
                <span>{progressPercent}%</span>
              </div>
              <div className="progress-legend">
                <span><b className="dot green-dot" /> Explored <strong>{progressExplored}</strong></span>
                <span><b className="dot blue-dot" /> Oxford 5K <strong>{stats?.oxford_explored_words ?? 0}/{stats?.oxford_target_words ?? 5000}</strong></span>
                <span><b className="dot gray-dot" /> AI Suggested <strong>{stats?.llm_suggested_words ?? 0}</strong></span>
              </div>
            </div>
          </section>
          <section>
            <h2>Queue Impact</h2>
            <div className="exploration-impact">
              <span>Needs Practice <strong>{stats?.practice_queue_words ?? 0}</strong></span>
              <span>Pending AI Words <strong>{stats?.llm_pending_suggestions ?? 0}</strong></span>
              <span>Due Today <strong>{stats?.due_today_words ?? 0}</strong></span>
            </div>
          </section>
          <section>
            <h2>Recent Activity</h2>
            <div className="recent-words">
              {recentRows.length ? recentRows.map((row) => (
                <span key={row.id}>{row.accuracy === 1 ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {row.title}</span>
              )) : <span>No activity yet</span>}
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}
