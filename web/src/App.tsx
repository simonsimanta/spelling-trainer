import {
  Award,
  BarChart3,
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Compass,
  Home,
  ListChecks,
  Loader2,
  Mic,
  PenLine,
  RefreshCcw,
  Settings as SettingsIcon,
  Sparkles,
  Trophy,
  Volume2,
  XCircle
} from "lucide-react";
import { CSSProperties, FormEvent, useEffect, useState } from "react";

import { getJson, patchJson, playAudio, postJson } from "./api";
import type {
  Achievement,
  BulkGenerateResult,
  BulkPreview,
  AttemptResult,
  BulkStatus,
  Dashboard,
  Exploration,
  OxfordLoadResult,
  OxfordLoadStatus,
  SessionItem,
  Settings,
  SpellingSession,
  ViewKey,
  Word
} from "./types";

const navItems: Array<{ key: ViewKey; label: string; icon: typeof Home }> = [
  { key: "dashboard", label: "Dashboard", icon: Home },
  { key: "diagnostic", label: "Diagnostic", icon: ListChecks },
  { key: "exploration", label: "Exploration", icon: Compass },
  { key: "practice", label: "Practice", icon: PenLine },
  { key: "dictation", label: "Dictation", icon: Mic },
  { key: "wordLists", label: "Word Lists", icon: ListChecks },
  { key: "progress", label: "Progress", icon: BarChart3 },
  { key: "achievements", label: "Achievements", icon: Trophy },
  { key: "settings", label: "Settings", icon: SettingsIcon }
];

type ModeCard = { view: ViewKey; title: string; text: string; cta: string; tone: string; icon: typeof Compass };

type ModeAvailability = {
  countLabel: string;
  detail: string;
  actionLabel: string;
  actionView: ViewKey;
  ready: boolean;
};

type EmptyStateAction = {
  title: string;
  text: string;
  primaryLabel: string;
  primaryView: ViewKey;
  secondaryLabel?: string;
  secondaryView?: ViewKey;
};

const modeCards: ModeCard[] = [
  {
    view: "diagnostic",
    title: "Diagnostic",
    text: "Find weak spellings first and build a personal queue.",
    cta: "Start Diagnostic",
    tone: "purple",
    icon: ListChecks
  },
  {
    view: "exploration",
    title: "Exploration",
    text: "Explore new words, meanings, pronunciation, and examples.",
    cta: "Explore",
    tone: "green",
    icon: Compass
  },
  {
    view: "practice",
    title: "Practice",
    text: "Repair mistakes with focused spelling exercises.",
    cta: "Practice",
    tone: "blue",
    icon: PenLine
  },
  {
    view: "dictation",
    title: "Dictation",
    text: "Listen carefully and type the words you hear.",
    cta: "Start Dictation",
    tone: "orange",
    icon: Mic
  }
];

function minutes(seconds: number): string {
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function title(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function explorationReadyWords(stats: Dashboard["stats"]): number {
  const oxfordRemaining = Math.max(stats.oxford_loaded_words - stats.oxford_explored_words, 0);
  return oxfordRemaining + stats.llm_suggested_words;
}

function modeAvailability(card: ModeCard, dashboard: Dashboard | null): ModeAvailability {
  if (!dashboard) {
    return {
      countLabel: "Checking",
      detail: "Loading current availability.",
      actionLabel: card.cta,
      actionView: card.view,
      ready: true
    };
  }

  const stats = dashboard.stats;
  const diagnosticReady = stats.diagnostic_ready_words;
  const explorationReady = explorationReadyWords(stats);

  if (card.view === "diagnostic") {
    return {
      countLabel: diagnosticReady ? `${diagnosticReady} ready` : "0 ready",
      detail: diagnosticReady ? "Best first step for finding weak spellings." : "All current diagnostic words have been tested.",
      actionLabel: diagnosticReady ? "Start Diagnostic" : stats.oxford_loaded_words ? "Explore Words" : "Load Words",
      actionView: diagnosticReady ? "diagnostic" : stats.oxford_loaded_words ? "exploration" : "settings",
      ready: diagnosticReady > 0
    };
  }

  if (card.view === "exploration") {
    if (!stats.oxford_loaded_words && !stats.llm_suggested_words) {
      return {
        countLabel: "Setup needed",
        detail: "Load Oxford words before exploring the core list.",
        actionLabel: "Load Words",
        actionView: "settings",
        ready: false
      };
    }
    return {
      countLabel: explorationReady ? `${explorationReady} new` : "0 new",
      detail: explorationReady ? "New Oxford or suggested words are available." : "All loaded exploration words are complete.",
      actionLabel: explorationReady ? "Explore" : "Load More",
      actionView: explorationReady ? "exploration" : "settings",
      ready: explorationReady > 0
    };
  }

  if (card.view === "practice") {
    if (stats.practice_queue_words) {
      return {
        countLabel: `${stats.practice_queue_words} queued`,
        detail: "Missed or due words are ready for repair.",
        actionLabel: "Practice",
        actionView: "practice",
        ready: true
      };
    }
    return {
      countLabel: "0 queued",
      detail: diagnosticReady ? "Run Diagnostic first to build your practice queue." : "No missed spellings are waiting.",
      actionLabel: diagnosticReady ? "Start Diagnostic" : explorationReady ? "Explore Words" : "Load Words",
      actionView: diagnosticReady ? "diagnostic" : explorationReady ? "exploration" : "settings",
      ready: false
    };
  }

  if (card.view === "dictation") {
    if (stats.dictation_ready_words) {
      return {
        countLabel: `${stats.dictation_ready_words} ready`,
        detail: "Trouble words are ready for sentence dictation.",
        actionLabel: "Start Dictation",
        actionView: "dictation",
        ready: true
      };
    }
    return {
      countLabel: "0 ready",
      detail: diagnosticReady ? "Run Diagnostic first; misses will unlock Dictation." : "No trouble words are ready for sentences.",
      actionLabel: diagnosticReady ? "Start Diagnostic" : explorationReady ? "Explore Words" : "Load Words",
      actionView: diagnosticReady ? "diagnostic" : explorationReady ? "exploration" : "settings",
      ready: false
    };
  }

  return {
    countLabel: "Ready",
    detail: card.text,
    actionLabel: card.cta,
    actionView: card.view,
    ready: true
  };
}

function practiceEmptyState(mode: "diagnostic" | "practice" | "dictation", dashboard: Dashboard | null): EmptyStateAction {
  const stats = dashboard?.stats;
  const diagnosticReady = stats?.diagnostic_ready_words ?? 0;
  const explorationReady = stats ? explorationReadyWords(stats) : 0;
  const hasOxfordWords = Boolean(stats?.oxford_loaded_words);
  const isDictation = mode === "dictation";

  if (mode === "diagnostic") {
    if (!hasOxfordWords) {
      return {
        title: "No diagnostic words left",
        text: "The starter diagnostic words are complete. Load Oxford words to expand the diagnostic pool.",
        primaryLabel: "Load Oxford Words",
        primaryView: "settings"
      };
    }
    return {
      title: "No diagnostic words left",
      text: "All available diagnostic words have already been tested. Explore loaded words or add suggested words to expand the pool.",
      primaryLabel: explorationReady ? "Go to Exploration" : "Go to Settings",
      primaryView: explorationReady ? "exploration" : "settings"
    };
  }

  if (diagnosticReady > 0) {
    return {
      title: isDictation ? "No dictation words yet" : "No practice words yet",
      text: `${diagnosticReady} diagnostic words are ready. Run Diagnostic first so missed spellings can enter ${isDictation ? "Dictation" : "Practice"}.`,
      primaryLabel: "Start Diagnostic",
      primaryView: "diagnostic",
      secondaryLabel: hasOxfordWords ? undefined : "Load Oxford Words",
      secondaryView: hasOxfordWords ? undefined : "settings"
    };
  }

  if (!hasOxfordWords) {
    return {
      title: isDictation ? "No dictation words yet" : "No practice words yet",
      text: "No Oxford words are loaded yet. Load the core list in Settings to create more learning paths.",
      primaryLabel: "Load Oxford Words",
      primaryView: "settings"
    };
  }

  if (explorationReady > 0) {
    return {
      title: isDictation ? "No dictation words yet" : "No practice words yet",
      text: `Explore new words first. Misses will enter ${isDictation ? "Dictation" : "Practice"} when they need repair.`,
      primaryLabel: "Go to Exploration",
      primaryView: "exploration"
    };
  }

  return {
    title: isDictation ? "No dictation words yet" : "No practice words yet",
    text: "There are no missed or due words waiting right now.",
    primaryLabel: "Go to Settings",
    primaryView: "settings"
  };
}

function explorationEmptyState(pool: ExplorationPool, dashboard: Dashboard | null, fallback?: string | null): EmptyStateAction | null {
  const stats = dashboard?.stats;
  const diagnosticReady = stats?.diagnostic_ready_words ?? 0;

  if (pool === "oxford" && stats && !stats.oxford_loaded_words) {
    return {
      title: "Exploration pool is empty",
      text: "Oxford words are not loaded yet. Load the core list in Settings, or run Diagnostic with the starter words.",
      primaryLabel: "Load Oxford Words",
      primaryView: "settings",
      secondaryLabel: diagnosticReady ? "Start Diagnostic" : undefined,
      secondaryView: diagnosticReady ? "diagnostic" : undefined
    };
  }

  if (pool === "suggested" && !(stats?.llm_suggested_words ?? 0)) {
    return {
      title: "Exploration pool is empty",
      text: "No AI difficult words are ready yet. Practice misses will create suggestions over time.",
      primaryLabel: diagnosticReady ? "Start Diagnostic" : "Go to Settings",
      primaryView: diagnosticReady ? "diagnostic" : "settings"
    };
  }

  if (fallback) {
    return {
      title: "Exploration pool is empty",
      text: fallback,
      primaryLabel: diagnosticReady ? "Start Diagnostic" : "Go to Settings",
      primaryView: diagnosticReady ? "diagnostic" : "settings"
    };
  }

  return null;
}

export default function App() {
  const [view, setView] = useState<ViewKey>("dashboard");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refreshDashboard() {
    const data = await getJson<Dashboard>("/dashboard");
    setDashboard(data);
  }

  useEffect(() => {
    refreshDashboard()
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <BookOpen size={30} />
          </div>
          <div>
            <strong>Spelling</strong>
            <span>Trainer</span>
          </div>
        </div>

        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={view === item.key ? "nav-item active" : "nav-item"}
                onClick={() => setView(item.key)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

      </aside>

      <main className="content">
        {error ? <div className="banner error">{error}</div> : null}
        {loading ? (
          <div className="loading">
            <Loader2 className="spin" />
            Loading spelling trainer
          </div>
        ) : (
          <>
            {view === "dashboard" && <DashboardView dashboard={dashboard} setView={setView} />}
            {view === "diagnostic" && <PracticeView mode="diagnostic" dashboard={dashboard} onRefresh={refreshDashboard} onNavigate={setView} />}
            {view === "exploration" && <ExplorationView dashboard={dashboard} onRefresh={refreshDashboard} onNavigate={setView} />}
            {view === "practice" && <PracticeView mode="practice" dashboard={dashboard} onRefresh={refreshDashboard} onNavigate={setView} />}
            {view === "dictation" && <PracticeView mode="dictation" dashboard={dashboard} onRefresh={refreshDashboard} onNavigate={setView} />}
            {view === "wordLists" && <WordListsView />}
            {view === "progress" && <ProgressView dashboard={dashboard} />}
            {view === "achievements" && <AchievementsView />}
            {view === "settings" && <SettingsView onRefresh={refreshDashboard} />}
          </>
        )}
      </main>
    </div>
  );
}

function DashboardView({ dashboard, setView }: { dashboard: Dashboard | null; setView: (view: ViewKey) => void }) {
  if (!dashboard) return null;
  const stats = dashboard.stats;
  const oxfordLoadedPercent = stats.oxford_target_words ? stats.oxford_loaded_words / stats.oxford_target_words : 0;
  const oxfordExploredPercent = stats.oxford_loaded_words ? stats.oxford_explored_words / stats.oxford_loaded_words : 0;
  const contentPercent = stats.oxford_loaded_words ? stats.content_generated_words / stats.oxford_loaded_words : 0;
  const audioPercent = stats.oxford_loaded_words ? stats.audio_generated_words / stats.oxford_loaded_words : 0;
  const activeLearningWords = Math.max(stats.learning_words - stats.known_provisional_words, 0);
  const trackedMasteryWords = Math.max(
    stats.oxford_loaded_words,
    activeLearningWords + stats.trouble_words + stats.stable_known_words + stats.known_provisional_words,
    1
  );
  const newWords = Math.max(
    trackedMasteryWords - activeLearningWords - stats.trouble_words - stats.stable_known_words - stats.known_provisional_words,
    0
  );
  const patternRows = stats.pattern_error_rates.map((pattern) => ({
    label: pattern.label,
    value: Math.round(pattern.recent_error_rate * 100),
    tone: "red",
    suffix: "%"
  }));
  return (
    <section className="page-grid dashboard-grid">
      <div className="panel span-2 hero-panel">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>Spelling Trainer</h1>
          <p>Build spelling recall with focused audio practice.</p>
        </div>
        <div className="hero-stats">
          <MiniStat icon={Sparkles} value={dashboard.profile.current_streak} label="Day Streak" />
          <MiniStat icon={Trophy} value={dashboard.profile.points} label="Points" />
        </div>
      </div>

      <div className="panel span-2 analytics-panel outcome-panel">
        <div className="section-head">
          <h2>Learning Outcomes</h2>
          <button className="ghost" onClick={() => setView("progress")}>
            View Progress <ChevronRight size={16} />
          </button>
        </div>
        <div className="analytics-grid">
          <Metric icon={Trophy} label="Exploration Accuracy" value={percent(stats.exploration_accuracy)} sub="First try in Exploration" />
          <Metric icon={ListChecks} label="Diagnostic Tested" value={stats.diagnostic_tested_words} sub={`${percent(stats.diagnostic_accuracy)} placement accuracy`} />
          <Metric icon={CheckCircle2} label="14-Day Retention" value={percent(stats.retention_accuracy_14d)} sub={`${stats.due_audit_words} audits due`} />
          <Metric icon={Award} label="30-Day Retention" value={percent(stats.retention_accuracy_30d)} sub="Delayed first try" />
          <Metric icon={XCircle} label="Lapse Rate" value={percent(stats.lapse_rate)} sub="Stable words missed later" />
          <Metric icon={ListChecks} label="Review Debt" value={stats.review_debt_words} sub="Overdue reviews" />
          <Metric icon={Compass} label="Known Provisional" value={stats.known_provisional_words} sub="Needs delayed audit" />
          <Metric icon={CheckCircle2} label="Stable Known" value={stats.stable_known_words} sub="Passed delayed audit" />
          <Metric icon={PenLine} label="Needs Practice" value={stats.practice_queue_words} sub={`${stats.diagnostic_missed_words} diagnostic misses`} />
          <Metric icon={Mic} label="Dictation Accuracy" value={percent(stats.dictation_accuracy)} sub={`${stats.dictation_distinct_words} words tried`} />
          <Metric icon={Trophy} label="First Try Overall" value={percent(stats.first_try_accuracy)} sub="All modes" />
        </div>
      </div>

      <div className="panel span-2 analytics-panel">
        <div className="section-head">
          <h2>Coverage And Cache Health</h2>
          <span className="muted">Setup status, not learning success</span>
        </div>
        <div className="analytics-grid">
          <Metric icon={BookOpen} label="Oxford Loaded" value={`${stats.oxford_loaded_words} / ${stats.oxford_target_words}`} sub={`${percent(oxfordLoadedPercent)} setup coverage`} />
          <Metric icon={Compass} label="Explored" value={stats.oxford_explored_words} sub={`${percent(oxfordExploredPercent)} of loaded`} />
          <Metric icon={Sparkles} label="Suggested by AI" value={stats.llm_suggested_words} sub={`${stats.llm_pending_suggestions} pending`} />
          <Metric icon={Award} label="Audio Cache" value={stats.audio_generated_words} sub={`${percent(audioPercent)} of loaded`} />
          <Metric icon={BarChart3} label="Content Cache" value={stats.content_generated_words} sub={`${percent(contentPercent)} of loaded`} />
        </div>
      </div>

      <div className="panel span-2">
        <div className="section-head">
          <h2>Learning Funnel</h2>
          <span className="muted">Loaded / explored / practiced / mastered</span>
        </div>
        <FunnelChart
          rows={[
            { label: "Oxford Loaded", value: stats.oxford_loaded_words, tone: "blue" },
            { label: "Explored", value: stats.oxford_explored_words, tone: "green" },
            { label: "Practiced", value: stats.practice_distinct_words, tone: "orange" },
            { label: "Stable Known", value: stats.stable_known_words, tone: "purple" }
          ]}
        />
      </div>

      <div className="panel">
        <h2>Mastery Breakdown</h2>
        <SegmentedBar
          total={trackedMasteryWords}
          segments={[
            { label: "New", value: newWords, tone: "slate" },
            { label: "Learning", value: activeLearningWords, tone: "blue" },
            { label: "Provisional", value: stats.known_provisional_words, tone: "purple" },
            { label: "Trouble", value: stats.trouble_words, tone: "orange" },
            { label: "Stable", value: stats.stable_known_words, tone: "green" }
          ]}
        />
      </div>

      <div className="panel">
        <h2>Queue Health</h2>
        <MiniBars
          rows={[
            { label: "Due Today", value: stats.due_today_words, tone: "blue" },
            { label: "Due Audit", value: stats.due_audit_words, tone: "purple" },
            { label: "Trouble", value: stats.trouble_words, tone: "orange" },
            { label: "Forced Correction", value: stats.forced_correction_words, tone: "red" },
            { label: "Review Debt", value: stats.review_debt_words, tone: "red" },
            { label: "Dictation Ready", value: stats.dictation_ready_words, tone: "green" }
          ]}
        />
      </div>

      <div className="panel">
        <h2>Top Error Patterns</h2>
        {patternRows.length ? (
          <MiniBars rows={patternRows} max={100} />
        ) : (
          <p className="muted">Pattern rates appear after missed spellings.</p>
        )}
      </div>

      <div className="panel">
        <div className="section-head">
          <h2>Mode Accuracy</h2>
          <span className="muted">First-try accuracy by training mode</span>
        </div>
        <MiniBars
          rows={[
            { label: "Exploration", value: Math.round(stats.exploration_accuracy * 100), tone: "green", suffix: "%" },
            { label: "Practice", value: Math.round(stats.practice_accuracy * 100), tone: "blue", suffix: "%" },
            { label: "Dictation", value: Math.round(stats.dictation_accuracy * 100), tone: "orange", suffix: "%" }
          ]}
          max={100}
        />
      </div>

      <div className="panel span-2">
        <h2>Choose a Mode</h2>
        <div className="mode-grid">
          {modeCards.map((card) => {
            const Icon = card.icon;
            const availability = modeAvailability(card, dashboard);
            return (
              <article className={`mode-card ${card.tone}`} key={card.view}>
                <Icon size={38} />
                <h3>{card.title}</h3>
                <p>{card.text}</p>
                <div className={availability.ready ? "mode-status ready" : "mode-status"}>
                  <strong>{availability.countLabel}</strong>
                  <span>{availability.detail}</span>
                </div>
                <button onClick={() => setView(availability.actionView)}>
                  {availability.actionLabel} <ChevronRight size={16} />
                </button>
              </article>
            );
          })}
        </div>
      </div>

      <div className="panel span-2">
        <div className="section-head">
          <h2>Recent Activity</h2>
          <button className="ghost" onClick={() => setView("progress")}>
            View All <ChevronRight size={16} />
          </button>
        </div>
        <ActivityList rows={dashboard.recent_activity} />
      </div>
    </section>
  );
}

function FunnelChart({ rows }: { rows: Array<{ label: string; value: number; tone: string }> }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="funnel-chart">
      {rows.map((row) => (
        <div className="funnel-row" key={row.label}>
          <div>
            <strong>{row.label}</strong>
            <span>{row.value}</span>
          </div>
          <i className={row.tone} style={{ "--bar": `${Math.max((row.value / max) * 100, row.value ? 6 : 0)}%` } as CSSProperties} />
        </div>
      ))}
    </div>
  );
}

function SegmentedBar({ total, segments }: { total: number; segments: Array<{ label: string; value: number; tone: string }> }) {
  return (
    <div className="segmented-wrap">
      <div className="segmented-bar">
        {segments.map((segment) => (
          <i
            className={segment.tone}
            key={segment.label}
            style={{ "--segment": `${Math.max((segment.value / total) * 100, segment.value ? 5 : 0)}%` } as CSSProperties}
          />
        ))}
      </div>
      <div className="segment-legend">
        {segments.map((segment) => (
          <span key={segment.label}><b className={segment.tone} /> {segment.label}: {segment.value}</span>
        ))}
      </div>
    </div>
  );
}

function MiniBars({
  rows,
  max
}: {
  rows: Array<{ label: string; value: number; tone: string; suffix?: string }>;
  max?: number;
}) {
  const ceiling = max ?? Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="mini-bars">
      {rows.map((row) => (
        <div className="mini-bar-row" key={row.label}>
          <span>{row.label}</span>
          <div><i className={row.tone} style={{ "--bar": `${Math.max((row.value / ceiling) * 100, row.value ? 6 : 0)}%` } as CSSProperties} /></div>
          <strong>{row.value}{row.suffix ?? ""}</strong>
        </div>
      ))}
    </div>
  );
}

function MiniStat({ icon: Icon, value, label }: { icon: typeof Sparkles; value: number; label: string }) {
  return (
    <div className="mini-stat">
      <Icon size={19} />
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Metric({ icon: Icon, label, value, sub }: { icon: typeof BookOpen; label: string; value: string | number; sub: string }) {
  return (
    <article className="metric-card">
      <div className="metric-icon">
        <Icon size={24} />
      </div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{sub}</small>
      </div>
    </article>
  );
}

type ExplorationPool = "oxford" | "suggested" | "mixed";

const explorationPools: Array<{ key: ExplorationPool; label: string; description: string }> = [
  { key: "oxford", label: "Oxford 5K", description: "Explore the core list in order." },
  { key: "suggested", label: "AI Difficult Words", description: "Words added from your error patterns." },
  { key: "mixed", label: "Mixed", description: "Blend suggested words with Oxford words." }
];

function ExplorationView({
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
      await playAudio(data.word.term);
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

function PracticeView({
  mode,
  dashboard,
  onRefresh,
  onNavigate
}: {
  mode: "diagnostic" | "practice" | "dictation";
  dashboard: Dashboard | null;
  onRefresh: () => Promise<void>;
  onNavigate: (view: ViewKey) => void;
}) {
  const [session, setSession] = useState<SpellingSession | null>(null);
  const [index, setIndex] = useState(0);
  const [attempt, setAttempt] = useState("");
  const [itemResults, setItemResults] = useState<Record<number, AttemptResult>>({});
  const [correction, setCorrection] = useState("");
  const [audioError, setAudioError] = useState<string | null>(null);
  const current = session?.items[index];
  const complete = session ? index >= session.items.length : false;
  const currentResult = current ? itemResults[current.session_item_id] : null;
  const isDictation = mode === "dictation";
  const isDiagnostic = mode === "diagnostic";

  async function start() {
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
  }

  async function submit(value?: string) {
    if (!current?.word_id) return;
    if (currentResult) return;
    const text = value ?? attempt;
    if (!text.trim()) return;
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
    await onRefresh();
  }

  async function submitCorrection(event: FormEvent) {
    event.preventDefault();
    if (!current || !currentResult?.attempt_id || !correction.trim()) return;
    await postJson(`/spelling/attempts/${currentResult.attempt_id}/correct`, { correction_text: correction });
    setCorrection("");
    setItemResults((existing) => ({
      ...existing,
      [current.session_item_id]: { ...currentResult, forced_correction_required: false, allow_next: true }
    }));
    await onRefresh();
  }

  function next() {
    if (blocked) return;
    setAttempt("");
    setCorrection("");
    setAudioError(null);
    setIndex((value) => value + 1);
  }

  function previous() {
    if (index === 0 || blocked) return;
    setAttempt("");
    setCorrection("");
    setAudioError(null);
    setIndex((value) => Math.max(value - 1, 0));
  }

  async function playCurrentAudio() {
    if (!current) return;
    try {
      await playAudio(isDictation ? current.prompt_text : current.term);
      setAudioError(null);
    } catch (err) {
      setAudioError(err instanceof Error ? err.message : "Unable to play audio");
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
          <button className="large-action" onClick={start}>
            {isDictation ? "Start Dictation" : isDiagnostic ? "Start Diagnostic" : "Start Practice"} <ChevronRight size={18} />
          </button>
        </div>
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
        <button onClick={start}>Start another session</button>
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
              disabled={Boolean(currentResult)}
              playAudio={playCurrentAudio}
              setAttempt={setAttempt}
              submit={submit}
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
                <button>Submit correction</button>
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

        <Exercise item={current} attempt={attempt} disabled={Boolean(currentResult)} setAttempt={setAttempt} submit={submit} />

        <div className="audio-row">
          <button className="listen-button" onClick={playCurrentAudio}>
            <Volume2 size={24} /> Listen
          </button>
        </div>
        {audioError ? <div className="banner warn">Audio unavailable: {audioError}</div> : null}

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
            <button>Submit correction</button>
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
  item,
  attempt,
  disabled,
  setAttempt,
  submit
}: {
  item: SessionItem;
  attempt: string;
  disabled: boolean;
  setAttempt: (value: string) => void;
  submit: (value?: string) => Promise<void>;
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
      <button disabled={disabled} onClick={() => submit()}>Submit</button>
    </div>
  );
}

function PracticeExercise({
  item,
  attempt,
  audioError,
  disabled,
  playAudio,
  setAttempt,
  submit
}: {
  item: SessionItem;
  attempt: string;
  audioError: string | null;
  disabled: boolean;
  playAudio: () => Promise<void>;
  setAttempt: (value: string) => void;
  submit: (value?: string) => Promise<void>;
}) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  return (
    <form className="practice-card" onSubmit={handleSubmit}>
      <div className="practice-audio-stage">
        <div className="waveform blue"><i /><i /><i /><i /><i /></div>
        <button className="audio-orb" type="button" onClick={playAudio} aria-label="Play word audio">
          <Volume2 size={34} />
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

      <div className="practice-card-actions">
        <button className="secondary" type="button" onClick={playAudio}>
          <Volume2 size={18} /> Hear Again
        </button>
        <button disabled={disabled || !attempt.trim()} type="submit">
          Check Answer
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

function Feedback({ result }: { result: AttemptResult }) {
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

function WordListsView() {
  const [tab, setTab] = useState("core5k");
  const [words, setWords] = useState<Word[]>([]);
  const [newWord, setNewWord] = useState("");

  async function load(nextTab = tab) {
    const list = await getJson<Word[]>(`/spelling/words?level=${nextTab}`);
    setWords(list);
  }

  async function addWord(event: FormEvent) {
    event.preventDefault();
    if (!newWord.trim()) return;
    await postJson("/spelling/words", { term: newWord, level: "personal", source: "manual" });
    setNewWord("");
    await load("personal");
    setTab("personal");
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [tab]);

  return (
    <section className="panel full">
      <div className="section-head">
        <h1>Word Lists</h1>
        <form className="inline-form" onSubmit={addWord}>
          <input value={newWord} onChange={(event) => setNewWord(event.target.value)} placeholder="Add personal word" />
          <button>Add</button>
        </form>
      </div>
      <div className="tabs">
        {["core5k", "personal", "trouble", "mastered"].map((item) => (
          <button
            className={tab === item ? "active" : ""}
            key={item}
            onClick={() => {
              setTab(item);
              load(item).catch(() => undefined);
            }}
          >
            {title(item)}
          </button>
        ))}
      </div>
      <div className="word-table">
        {words.map((word) => (
          <article key={word.id}>
            <strong>{word.term}</strong>
            <span>{word.mastery_state}</span>
            <small>{word.short_meaning ?? word.example_sentence ?? word.source}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ProgressView({ dashboard }: { dashboard: Dashboard | null }) {
  if (!dashboard) return null;
  return (
    <section className="page-grid">
      <div className="panel">
        <h1>Progress</h1>
        <div className="metric-grid vertical">
          <Metric icon={BookOpen} label="Core 5K Coverage" value={`${dashboard.core5k.coverage_percent}%`} sub={`${dashboard.core5k.attempted_words} attempted`} />
          <Metric icon={CheckCircle2} label="Mastered" value={dashboard.core5k.mastered_words} sub={`${dashboard.core5k.due_today_words} due today`} />
          <Metric icon={Trophy} label="Best Streak" value={dashboard.profile.best_streak} sub="days" />
        </div>
      </div>
      <div className="panel">
        <h2>Recent Activity</h2>
        <ActivityList rows={dashboard.recent_activity} />
      </div>
    </section>
  );
}

function AchievementsView() {
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  useEffect(() => {
    getJson<Achievement[]>("/achievements").then(setAchievements).catch(() => undefined);
  }, []);
  return (
    <section className="panel full">
      <h1>Achievements</h1>
      <div className="achievement-grid">
        {achievements.map((achievement) => (
          <article className={achievement.unlocked_at ? "achievement unlocked" : "achievement"} key={achievement.code}>
            {achievement.unlocked_at ? <Award /> : <Trophy />}
            <h3>{achievement.title}</h3>
            <p>{achievement.description}</p>
            <div className="progress-line"><i style={{ width: `${Math.min((achievement.progress / achievement.target) * 100, 100)}%` }} /></div>
            <span>{achievement.progress} / {achievement.target}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function SettingsView({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [oxfordStatus, setOxfordStatus] = useState<OxfordLoadStatus | null>(null);
  const [contentStatus, setContentStatus] = useState<BulkStatus | null>(null);
  const [audioStatus, setAudioStatus] = useState<BulkStatus | null>(null);
  const [preview, setPreview] = useState<{ kind: "content" | "audio"; data: BulkPreview } | null>(null);
  const [running, setRunning] = useState<"content" | "audio" | null>(null);
  const [loadingOxford, setLoadingOxford] = useState(false);
  const [oxfordResult, setOxfordResult] = useState<OxfordLoadResult | null>(null);
  const [results, setResults] = useState<Partial<Record<"content" | "audio", BulkGenerateResult>>>({});
  const [message, setMessage] = useState<string | null>(null);

  async function load(selectedSettings?: Settings) {
    const activeSettings = selectedSettings ?? await getJson<Settings>("/settings");
    if (!selectedSettings) {
      setSettings(activeSettings);
    }
    setOxfordStatus(await getJson<OxfordLoadStatus>("/spelling/oxford/load-status"));
    setContentStatus(await getJson<BulkStatus>("/spelling/content/bulk-status"));
    const audioParams = new URLSearchParams({
      voice: activeSettings.tts_voice,
      model: activeSettings.tts_model
    });
    setAudioStatus(await getJson<BulkStatus>(`/spelling/audio/bulk-status?${audioParams.toString()}`));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    const updated = await patchJson<Settings>("/settings", settings);
    setSettings(updated);
    await load(updated);
    await onRefresh();
    setMessage("Settings saved.");
  }

  async function openPreview(kind: "content" | "audio") {
    if (!settings) return;
    const limit = Math.max(1, Math.min(settings.content_bulk_limit, 5000));
    const params = new URLSearchParams({ limit: String(limit) });
    if (kind === "audio") {
      params.set("voice", settings.tts_voice);
      params.set("model", settings.tts_model);
    }
    const path = kind === "content" ? "/spelling/content/bulk-preview" : "/spelling/audio/bulk-preview";
    const data = await getJson<BulkPreview>(`${path}?${params.toString()}`);
    setPreview({ kind, data });
    setMessage(null);
  }

  async function generate(kind: "content" | "audio") {
    if (!settings) return;
    const path = kind === "content" ? "/spelling/content/bulk-generate" : "/spelling/audio/bulk-generate";
    setRunning(kind);
    setMessage(null);
    try {
      const result = await postJson<BulkGenerateResult>(path, {
        limit: settings.content_bulk_limit,
        voice: settings.tts_voice,
        model: settings.tts_model
      });
      setResults((existing) => ({ ...existing, [kind]: result }));
      await load(settings);
      setPreview(null);
      setMessage(`${kind === "content" ? "Word learning content" : "Word audio"} batch finished.`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Generation failed.");
    } finally {
      setRunning(null);
    }
  }

  async function loadOxfordBatch() {
    if (!settings) return;
    setLoadingOxford(true);
    setMessage(null);
    try {
      const result = await postJson<OxfordLoadResult>("/spelling/oxford/load-batch", {
        limit: settings.content_bulk_limit
      });
      setOxfordResult(result);
      await load(settings);
      await onRefresh();
      setMessage(`Oxford import finished: ${result.created} loaded, ${result.updated} already existed.`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Oxford import failed.");
    } finally {
      setLoadingOxford(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  if (!settings) return null;
  return (
    <section className="panel full">
      <h1>Settings</h1>
      <form className="settings-form" onSubmit={save}>
        <label>Theme
          <select value={settings.theme} onChange={(event) => setSettings({ ...settings, theme: event.target.value })}>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        <label>TTS Voice
          <select
            value={settings.tts_voice}
            onChange={(event) => {
              const updated = { ...settings, tts_voice: event.target.value };
              setSettings(updated);
              load(updated).catch(() => setAudioStatus(null));
            }}
          >
            {[
              "alloy",
              "ash",
              "ballad",
              "cedar",
              "coral",
              "echo",
              "fable",
              "marin",
              "nova",
              "onyx",
              "sage",
              "shimmer",
              "verse"
            ].map((voice) => (
              <option value={voice} key={voice}>{title(voice)}</option>
            ))}
          </select>
        </label>
        <label>Batch size
          <input type="number" min={1} max={5000} value={settings.content_bulk_limit} onChange={(event) => setSettings({ ...settings, content_bulk_limit: Number(event.target.value) })} />
          <small>Used for loading Oxford words, generating content, and generating audio. Development default is 100 words per run.</small>
        </label>
        <label>AI generation
          <select value={settings.ai_generation_enabled ? "enabled" : "disabled"} onChange={(event) => setSettings({ ...settings, ai_generation_enabled: event.target.value === "enabled" })}>
            <option value="enabled">Enabled</option>
            <option value="disabled">Disabled</option>
          </select>
        </label>
        <label className="advanced-field">TTS Model
          <input
            value={settings.tts_model}
            onBlur={() => load(settings).catch(() => setAudioStatus(null))}
            onChange={(event) => {
              setAudioStatus(null);
              setSettings({ ...settings, tts_model: event.target.value });
            }}
          />
        </label>
        <label className="advanced-field">AI Model<input value={settings.ai_model} onChange={(event) => setSettings({ ...settings, ai_model: event.target.value })} /></label>
        <button>Save Settings</button>
      </form>

      <OxfordLoader
        status={oxfordStatus}
        batchSize={settings.content_bulk_limit}
        running={loadingOxford}
        result={oxfordResult}
        onLoad={loadOxfordBatch}
      />

      <div className="settings-section-head">
        <div>
          <p className="eyebrow">Advanced</p>
          <h2>Content & Audio Cache</h2>
          <p>Optional pre-generation for Oxford words. The app still works with on-demand content and audio.</p>
        </div>
      </div>
      <div className="bulk-grid">
        <BulkCard
          title="Word Learning Content"
          text="Generates cached meanings, IPA, examples, word family, and spelling help for Oxford words."
          status={contentStatus}
          result={results.content}
          running={running === "content"}
          oxfordStatus={oxfordStatus}
          onPreview={() => openPreview("content")}
        />
        <BulkCard
          title="Word Audio Cache"
          text="Generates cached OpenAI TTS files so Listen buttons are faster and more reliable."
          status={audioStatus}
          result={results.audio}
          running={running === "audio"}
          oxfordStatus={oxfordStatus}
          variant={{ voice: settings.tts_voice, model: settings.tts_model }}
          onPreview={() => openPreview("audio")}
        />
      </div>
      {message ? <div className="banner success">{message}</div> : null}
      {preview ? (
        <BulkPreviewPanel
          kind={preview.kind}
          preview={preview.data}
          running={running === preview.kind}
          onCancel={() => setPreview(null)}
          onConfirm={() => generate(preview.kind)}
        />
      ) : null}
    </section>
  );
}

function OxfordLoader({
  status,
  batchSize,
  running,
  result,
  onLoad
}: {
  status: OxfordLoadStatus | null;
  batchSize: number;
  running: boolean;
  result: OxfordLoadResult | null;
  onLoad: () => void;
}) {
  const loaded = status?.loaded_words ?? 0;
  const target = status?.target_words ?? 5000;
  const remaining = status?.remaining_words ?? Math.max(target - loaded, 0);
  const canLoad = Boolean(status?.source_available && remaining > 0);

  return (
    <article className="oxford-loader">
      <div>
        <p className="eyebrow">Oxford 5K Loader</p>
        <h2>Load words before generating content or audio</h2>
        <p>
          Import the next batch from the local Oxford PDFs. This only loads word records and source ranks; AI content and audio stay manual.
        </p>
      </div>
      <div className="oxford-loader-grid">
        <span><b>{loaded}</b> loaded</span>
        <span><b>{target}</b> target</span>
        <span><b>{remaining}</b> remaining</span>
        <span><b>{status?.source_available ? "Ready" : "Missing"}</b> source PDFs</span>
      </div>
      {result ? (
        <div className="bulk-result">
          Last import: {result.created} loaded, {result.updated} already existed, {result.skipped} skipped, {result.remaining_words} remaining.
        </div>
      ) : null}
      <button disabled={running || !canLoad} onClick={onLoad}>
        {running ? <Loader2 className="spin" size={16} /> : null}
        {running ? "Loading Oxford words..." : `Load Next ${Math.max(1, Math.min(batchSize, 5000))} Oxford Words`}
      </button>
      {!status?.source_available ? <div className="banner warn">Oxford PDFs are missing from the data folder.</div> : null}
    </article>
  );
}

function BulkCard({
  title: cardTitle,
  text,
  status,
  result,
  running,
  oxfordStatus,
  variant,
  onPreview
}: {
  title: string;
  text: string;
  status: BulkStatus | null;
  result?: BulkGenerateResult;
  running: boolean;
  oxfordStatus: OxfordLoadStatus | null;
  variant?: { voice: string; model: string };
  onPreview: () => void;
}) {
  const pending = status?.pending ?? 0;
  const loaded = oxfordStatus?.loaded_words ?? status?.total_words ?? 0;
  const target = oxfordStatus?.target_words ?? 5000;
  let buttonLabel = cardTitle.includes("Audio") ? "Preview Audio Batch" : "Preview Content Batch";
  if (!status) {
    buttonLabel = "Checking cache";
  } else if (pending === 0) {
    buttonLabel = loaded < target ? "Load More Oxford Words First" : "All Loaded Words Cached";
  }

  return (
    <article className="bulk-card">
      <h3>{cardTitle}</h3>
      <p>{text}</p>
      {variant ? (
        <div className="audio-cache-variant">
          <span><b>Voice</b>{title(variant.voice)}</span>
          <span><b>Model</b>{variant.model}</span>
          <span><b>Status</b>{status ? "Cache checked" : "Checking cache"}</span>
        </div>
      ) : null}
      <div className="bulk-status-row">
        <span><b>{status?.generated ?? 0} / {loaded}</b> generated / loaded</span>
        <span><b>{pending}</b> pending among loaded</span>
        <span><b>{status?.failed ?? 0}</b> failed</span>
      </div>
      {result ? (
        <div className={result.failed ? "bulk-result warn" : "bulk-result"}>
          Last run: {result.generated} generated, {result.cached} cached, {result.failed} failed, {result.remaining} remaining.
        </div>
      ) : null}
      <button disabled={running || !status || pending === 0} onClick={onPreview}>
        {running ? <Loader2 className="spin" size={16} /> : null}
        {running ? "Generating..." : buttonLabel}
      </button>
    </article>
  );
}

function BulkPreviewPanel({
  kind,
  preview,
  running,
  onCancel,
  onConfirm
}: {
  kind: "content" | "audio";
  preview: BulkPreview;
  running: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <article className="bulk-preview-modal">
        <div className="section-head">
          <div>
            <p className="eyebrow">Confirm Batch</p>
            <h2>{kind === "content" ? "Generate word learning content" : "Generate word audio cache"}</h2>
          </div>
          <button className="secondary" disabled={running} onClick={onCancel}>Cancel</button>
        </div>
        <p>
          This will process up to {preview.will_process} words from a batch size of {preview.limit}. This may use OpenAI API quota.
        </p>
        <div className="preview-grid">
          <span><b>{preview.total_words}</b>Total words</span>
          <span><b>{preview.generated}</b>Generated</span>
          <span><b>{preview.pending}</b>Pending</span>
          <span><b>{preview.failed}</b>Failed</span>
          <span><b>{preview.will_process}</b>Will process</span>
          <span><b>{preview.estimated_api_calls}</b>Est. API calls</span>
        </div>
        <div className="model-note">
          <strong>Model</strong>
          <span>{preview.model}</span>
          {preview.voice ? <><strong>Voice</strong><span>{preview.voice}</span></> : null}
        </div>
        {preview.failed ? <div className="banner warn">{preview.failed} previous failures are recorded. Retry after checking model, voice, and API key settings.</div> : null}
        <div className="action-row">
          <button className="secondary" disabled={running} onClick={onCancel}>Cancel</button>
          <button disabled={running || preview.will_process === 0} onClick={onConfirm}>
            {running ? <Loader2 className="spin" size={16} /> : null}
            {running ? "Generating..." : "Generate batch"}
          </button>
        </div>
      </article>
    </div>
  );
}

function ActivityList({ rows }: { rows: Dashboard["recent_activity"] }) {
  if (!rows.length) return <p className="muted">No activity yet.</p>;
  return (
    <div className="activity-list">
      {rows.map((row) => (
        <article key={row.id}>
          <span>{row.event_type === "dictation" ? <Mic size={16} /> : row.event_type === "achievement" ? <Award size={16} /> : <PenLine size={16} />}</span>
          <strong>{row.title}</strong>
          <small>{new Date(row.created_at).toLocaleString()}</small>
          {row.accuracy === 1 ? <CheckCircle2 size={16} /> : row.accuracy === 0 ? <XCircle size={16} /> : null}
        </article>
      ))}
    </div>
  );
}
