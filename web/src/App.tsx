import {
  AlertTriangle,
  Archive as ArchiveIcon,
  ArchiveRestore,
  ArrowUpDown,
  Award,
  BarChart3,
  BookOpen,
  CalendarCheck2,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Compass,
  Home,
  ListChecks,
  Loader2,
  Mic,
  Pencil,
  PenLine,
  Play,
  RefreshCcw,
  RotateCcw,
  Search,
  Settings as SettingsIcon,
  Sparkles,
  Target,
  TrendingUp,
  Trophy,
  Volume2,
  X,
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
  ManagedWord,
  OxfordLoadResult,
  OxfordLoadStatus,
  ReadinessReport,
  SessionItem,
  Settings,
  SpellingSuggestion,
  SpellingSession,
  ViewKey,
  Word,
  WordManagementCounts,
  WordManagementPage
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

type NextBestAction = {
  view: ViewKey;
  title: string;
  reason: string;
  actionLabel: string;
};

function nextBestAction(dashboard: Dashboard, readiness: ReadinessReport | null): NextBestAction {
  const requiredFailure = readiness?.checks.find((check) => check.required && check.status === "failed");
  if (requiredFailure) {
    return {
      view: "settings",
      title: `Restore ${requiredFailure.label.toLowerCase()}`,
      reason: requiredFailure.action ?? requiredFailure.detail,
      actionLabel: "Open Settings"
    };
  }

  const mode = dashboard.daily_plan.recommended_mode;
  if (mode === "exploration" && dashboard.stats.oxford_loaded_words === 0) {
    return {
      view: "settings",
      title: "Load your Oxford word library",
      reason: "Exploration needs source words. Load the first Oxford batch, then return to begin learning.",
      actionLabel: "Set Up Words"
    };
  }

  const actions: Record<string, Omit<NextBestAction, "reason">> = {
    diagnostic: { view: "diagnostic", title: "Run your diagnostic baseline", actionLabel: "Start Diagnostic" },
    practice: { view: "practice", title: "Repair your highest-risk spellings", actionLabel: "Start Practice" },
    review_due: { view: "practice", title: "Complete your scheduled reviews", actionLabel: "Review Now" },
    exploration: { view: "exploration", title: "Introduce a useful new word", actionLabel: "Explore Word" },
    dictation: { view: "dictation", title: "Strengthen recall through dictation", actionLabel: "Start Dictation" }
  };
  const action = actions[mode] ?? actions.diagnostic;
  return {
    ...action,
    reason: dashboard.daily_plan.recommended_reason
  };
}

export default function App() {
  const [view, setView] = useState<ViewKey>("dashboard");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [readiness, setReadiness] = useState<ReadinessReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [environmentError, setEnvironmentError] = useState<string | null>(null);
  const [wordPracticeSession, setWordPracticeSession] = useState<SpellingSession | null>(null);

  async function refreshDashboard() {
    const data = await getJson<Dashboard>("/dashboard");
    setDashboard(data);
    setError(null);
  }

  async function refreshReadiness(): Promise<ReadinessReport> {
    const data = await getJson<ReadinessReport>("/readiness");
    setReadiness(data);
    setEnvironmentError(null);
    return data;
  }

  async function startWordPractice(wordId: number): Promise<void> {
    const created = await postJson<SpellingSession>("/spelling/sessions", {
      session_type: "practice",
      target_size: 1,
      exercise_type: "mixed",
      word_ids: [wordId]
    });
    setWordPracticeSession(created);
    setView("practice");
  }

  useEffect(() => {
    async function bootstrap() {
      let report: ReadinessReport | null = null;
      try {
        report = await refreshReadiness();
      } catch {
        // Older or unreachable backends may not expose readiness; try the main route before failing.
      }

      if (report?.status === "unavailable") return;

      try {
        await refreshDashboard();
      } catch (err) {
        if (!report) {
          setEnvironmentError("The backend API is unavailable. Start the backend, then refresh this page.");
        } else {
          setError(err instanceof Error ? err.message : "Dashboard failed to load.");
        }
      }
    }

    bootstrap().finally(() => setLoading(false));
  }, []);

  const databaseFailure = readiness?.checks.find((check) => check.key === "database" && check.status === "failed");

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
        {readiness?.status === "unavailable" ? (
          <div className="environment-banner error" role="alert">
            <AlertTriangle size={20} />
            <div>
              <strong>Database unavailable</strong>
              <span>{databaseFailure?.detail ?? "The app cannot reach its configured database."}</span>
            </div>
            <button className="secondary" onClick={() => setView("settings")}>Open Settings</button>
          </div>
        ) : environmentError ? (
          <div className="environment-banner error" role="alert">
            <AlertTriangle size={20} />
            <div>
              <strong>Backend API unavailable</strong>
              <span>{environmentError}</span>
            </div>
          </div>
        ) : null}
        {error ? <div className="banner error">{error}</div> : null}
        {loading ? (
          <div className="loading">
            <Loader2 className="spin" />
            Loading spelling trainer
          </div>
        ) : (
          <>
            {view === "dashboard" && <DashboardView dashboard={dashboard} readiness={readiness} setView={setView} />}
            {view === "diagnostic" && <PracticeView mode="diagnostic" dashboard={dashboard} onRefresh={refreshDashboard} onNavigate={setView} />}
            {view === "exploration" && <ExplorationView dashboard={dashboard} onRefresh={refreshDashboard} onNavigate={setView} />}
            {view === "practice" && (
              <PracticeView
                mode="practice"
                dashboard={dashboard}
                onRefresh={refreshDashboard}
                onNavigate={setView}
                initialSession={wordPracticeSession}
                onInitialSessionConsumed={() => setWordPracticeSession(null)}
              />
            )}
            {view === "dictation" && <PracticeView mode="dictation" dashboard={dashboard} onRefresh={refreshDashboard} onNavigate={setView} />}
            {view === "wordLists" && (
              <WordListsView
                onPractice={startWordPractice}
                onRefresh={refreshDashboard}
              />
            )}
            {view === "progress" && <ProgressView dashboard={dashboard} onNavigate={setView} />}
            {view === "achievements" && <AchievementsView onNavigate={setView} />}
            {view === "settings" && (
              <SettingsView
                readiness={readiness}
                onRefresh={refreshDashboard}
                onRefreshReadiness={refreshReadiness}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}

function DashboardView({
  dashboard,
  readiness,
  setView
}: {
  dashboard: Dashboard | null;
  readiness: ReadinessReport | null;
  setView: (view: ViewKey) => void;
}) {
  if (!dashboard) return null;
  const stats = dashboard.stats;
  const nextAction = nextBestAction(dashboard, readiness);
  const hasLearningHistory = stats.first_try_accuracy > 0
    || stats.diagnostic_tested_words > 0
    || stats.practice_distinct_words > 0
    || stats.dictation_distinct_words > 0
    || stats.oxford_explored_words > 0;
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

      <section className="next-action-band span-2" aria-labelledby="next-action-title">
        <div className="next-action-icon"><Target size={26} /></div>
        <div className="next-action-copy">
          <div className="next-action-label">
            <span>Next best action</span>
            <strong>Daily plan</strong>
          </div>
          <h2 id="next-action-title">{nextAction.title}</h2>
          <p>{nextAction.reason}</p>
          <div className="next-action-signals">
            <span>{dashboard.daily_plan.due_reviews} reviews due</span>
            <span>{dashboard.daily_plan.mistake_words} mistake words</span>
            <span>{dashboard.daily_plan.new_words} new words</span>
          </div>
        </div>
        <button onClick={() => setView(nextAction.view)}>
          {nextAction.actionLabel} <ChevronRight size={17} />
        </button>
      </section>

      <div className="panel span-2 analytics-panel outcome-panel">
        <div className="section-head">
          <div>
            <span className="metric-kind outcome">Learning outcome</span>
            <h2>Learning Outcomes</h2>
          </div>
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
          <div>
            <span className="metric-kind setup">Setup health</span>
            <h2>Coverage And Cache Health</h2>
          </div>
          <span className="muted">Availability metrics, not learning success</span>
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
        <span className="metric-kind queue">Queue health</span>
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
        {dashboard.recent_activity.length ? (
          <ActivityList rows={dashboard.recent_activity} />
        ) : hasLearningHistory ? (
          <GuidedEmptyState
            icon={CalendarCheck2}
            title="No recent sessions"
            text="Return to your Daily Plan to keep reviews current and rebuild a consistent learning rhythm."
            actionLabel={nextAction.actionLabel}
            onAction={() => setView(nextAction.view)}
          />
        ) : (
          <GuidedEmptyState
            icon={ListChecks}
            title="Your learning history starts with a diagnostic"
            text="Test a short set of words so the trainer can identify misses and build your first practice queue."
            actionLabel="Start Diagnostic"
            onAction={() => setView("diagnostic")}
          />
        )}
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

function GuidedEmptyState({
  icon: Icon,
  title: emptyTitle,
  text,
  actionLabel,
  onAction
}: {
  icon: typeof BookOpen;
  title: string;
  text: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="guided-empty-state">
      <Icon size={26} />
      <div>
        <strong>{emptyTitle}</strong>
        <p>{text}</p>
      </div>
      <button onClick={onAction}>{actionLabel} <ChevronRight size={16} /></button>
    </div>
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
  const current = session?.items[index];
  const complete = session ? index >= session.items.length : false;
  const currentResult = current ? itemResults[current.session_item_id] : null;
  const isDictation = mode === "dictation";
  const isDiagnostic = mode === "diagnostic";

  useEffect(() => {
    if (initialSession) onInitialSessionConsumed?.();
  }, [initialSession, onInitialSessionConsumed]);

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

const emptyWordCounts: WordManagementCounts = {
  all: 0,
  oxford: 0,
  personal: 0,
  suggested: 0,
  trouble: 0,
  provisional: 0,
  stable: 0,
  seed: 0,
  archived: 0
};

const wordCategories: Array<{ key: keyof WordManagementCounts; label: string }> = [
  { key: "all", label: "All active" },
  { key: "oxford", label: "Oxford" },
  { key: "personal", label: "Personal" },
  { key: "suggested", label: "Suggested" },
  { key: "trouble", label: "Trouble" },
  { key: "provisional", label: "Provisional" },
  { key: "stable", label: "Stable" },
  { key: "seed", label: "Starter" },
  { key: "archived", label: "Archived" }
];

type WordActionResult = {
  word_id: number;
  term: string;
  action: string;
  message: string;
};

type WordEditDraft = {
  term: string;
  short_meaning: string;
  example_sentence: string;
  part_of_speech: string;
  cefr_level: string;
};

function displayDate(value?: string | null): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

function WordListsView({
  onPractice,
  onRefresh
}: {
  onPractice: (wordId: number) => Promise<void>;
  onRefresh: () => Promise<void>;
}) {
  const [category, setCategory] = useState<keyof WordManagementCounts>("all");
  const [page, setPage] = useState<WordManagementPage>({
    items: [],
    total: 0,
    counts: emptyWordCounts
  });
  const [suggestions, setSuggestions] = useState<SpellingSuggestion[]>([]);
  const [newWord, setNewWord] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [query, setQuery] = useState("");
  const [masteryState, setMasteryState] = useState("all");
  const [diagnosticStatus, setDiagnosticStatus] = useState("all");
  const [sort, setSort] = useState("term");
  const [direction, setDirection] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);
  const [loadingWords, setLoadingWords] = useState(true);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ManagedWord | null>(null);
  const [editDraft, setEditDraft] = useState<WordEditDraft | null>(null);
  const limit = 50;

  async function load() {
    const params = new URLSearchParams({
      category,
      sort,
      direction,
      limit: String(limit),
      offset: String(offset)
    });
    if (query) params.set("query", query);
    if (masteryState !== "all") params.set("mastery_state", masteryState);
    if (diagnosticStatus !== "all") params.set("diagnostic_status", diagnosticStatus);
    setLoadingWords(true);
    try {
      const [nextPage, pendingSuggestions] = await Promise.all([
        getJson<WordManagementPage>(`/spelling/word-management?${params.toString()}`),
        getJson<SpellingSuggestion[]>("/spelling/suggestions?status=pending")
      ]);
      setPage(nextPage);
      setSuggestions(pendingSuggestions);
      setListError(null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to load words.");
    } finally {
      setLoadingWords(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [category, query, masteryState, diagnosticStatus, sort, direction, offset]);

  async function addWord(event: FormEvent) {
    event.preventDefault();
    if (!newWord.trim()) return;
    try {
      const created = await postJson<Word>("/spelling/words", {
        term: newWord,
        level: "personal",
        source: "manual"
      });
      setNewWord("");
      setCategory("personal");
      setSearchDraft(created.term);
      setQuery(created.term);
      setOffset(0);
      setFeedback(`${title(created.term)} was added to Personal words.`);
      setListError(null);
      await onRefresh();
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to add this word.");
    }
  }

  function openEditor(word: ManagedWord) {
    setEditing(word);
    setEditDraft({
      term: word.term,
      short_meaning: word.short_meaning ?? "",
      example_sentence: word.example_sentence ?? "",
      part_of_speech: word.part_of_speech ?? "",
      cefr_level: word.cefr_level ?? ""
    });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing || !editDraft) return;
    try {
      const updated = await patchJson<Word>(`/spelling/words/${editing.id}`, editDraft);
      setEditing(null);
      setEditDraft(null);
      setFeedback(`${title(updated.term)} was updated.`);
      setListError(null);
      await load();
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to update this word.");
    }
  }

  async function applyWordAction(word: ManagedWord, action: WordActionResult["action"]) {
    if (action === "reset" && !window.confirm(`Reset all learning progress for "${word.term}"?`)) return;
    try {
      const result = await postJson<WordActionResult>(`/spelling/words/${word.id}/actions`, { action });
      setFeedback(result.message);
      setListError(null);
      if (action === "practice") {
        await onPractice(word.id);
        return;
      }
      await Promise.all([load(), onRefresh()]);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to update this word.");
    }
  }

  async function reviewSuggestion(suggestionId: number, status: "approved" | "rejected") {
    try {
      const updated = await patchJson<SpellingSuggestion>(`/spelling/suggestions/${suggestionId}`, { status });
      setFeedback(`${title(updated.term)} was ${status}.`);
      await Promise.all([load(), onRefresh()]);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to review this suggestion.");
    }
  }

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setQuery(searchDraft.trim());
    setOffset(0);
  }

  function resetFilters() {
    setSearchDraft("");
    setQuery("");
    setMasteryState("all");
    setDiagnosticStatus("all");
    setSort("term");
    setDirection("asc");
    setOffset(0);
  }

  const rangeStart = page.total ? offset + 1 : 0;
  const rangeEnd = Math.min(offset + limit, page.total);

  return (
    <section className="word-management">
      <div className="section-head word-management-head">
        <div>
          <p className="eyebrow">Library</p>
          <h1>Word Lists</h1>
          <p className="muted">Search your vocabulary, inspect its learning state, and decide what happens next.</p>
        </div>
        <form className="inline-form word-add-form" onSubmit={addWord}>
          <input
            aria-label="New personal word"
            value={newWord}
            onChange={(event) => setNewWord(event.target.value)}
            placeholder="Add personal word"
          />
          <button>Add word</button>
        </form>
      </div>

      {feedback ? (
        <div className="banner success word-feedback" role="status">
          <span>{feedback}</span>
          <button className="icon-button compact" aria-label="Dismiss message" title="Dismiss" onClick={() => setFeedback(null)}>
            <X size={16} />
          </button>
        </div>
      ) : null}
      {listError ? <div className="banner error" role="alert">{listError}</div> : null}

      <div className="word-category-tabs" role="tablist" aria-label="Word categories">
        {wordCategories.map((item) => (
          <button
            role="tab"
            aria-selected={category === item.key}
            className={category === item.key ? "active" : ""}
            key={item.key}
            onClick={() => {
              setCategory(item.key);
              setOffset(0);
            }}
          >
            <span>{item.label}</span>
            <strong>{page.counts[item.key]}</strong>
          </button>
        ))}
      </div>

      <div className="word-list-toolbar">
        <form className="word-search" onSubmit={applySearch}>
          <Search size={18} />
          <input
            aria-label="Search words"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search word or meaning"
          />
          <button aria-label="Run search" title="Search"><Search size={17} /></button>
        </form>
        <label>
          <span>Mastery</span>
          <select value={masteryState} onChange={(event) => {
            setMasteryState(event.target.value);
            setOffset(0);
          }}>
            <option value="all">All states</option>
            <option value="new">New</option>
            <option value="learning">Learning</option>
            <option value="review">Review</option>
            <option value="known_provisional">Provisional</option>
            <option value="stable_known">Stable</option>
            <option value="lapse">Lapse</option>
            <option value="known">Known</option>
          </select>
        </label>
        <label>
          <span>Diagnostic</span>
          <select value={diagnosticStatus} onChange={(event) => {
            setDiagnosticStatus(event.target.value);
            setOffset(0);
          }}>
            <option value="all">All results</option>
            <option value="untested">Untested</option>
            <option value="passed">Passed</option>
            <option value="missed">Missed</option>
          </select>
        </label>
        <label>
          <span>Sort</span>
          <select value={sort} onChange={(event) => {
            setSort(event.target.value);
            setOffset(0);
          }}>
            <option value="term">Word</option>
            <option value="frequency_rank">Frequency rank</option>
            <option value="due_date">Due date</option>
            <option value="last_attempt">Last attempt</option>
            <option value="priority">Practice priority</option>
          </select>
        </label>
        <button
          className="icon-button toolbar-icon"
          aria-label={`Sort ${direction === "asc" ? "descending" : "ascending"}`}
          title={`Sort ${direction === "asc" ? "descending" : "ascending"}`}
          onClick={() => setDirection((current) => current === "asc" ? "desc" : "asc")}
        >
          <ArrowUpDown size={18} />
        </button>
        <button className="secondary toolbar-reset" onClick={resetFilters}>
          <RotateCcw size={17} /> Reset
        </button>
      </div>

      {category === "suggested" && suggestions.length ? (
        <section className="suggestion-review" aria-labelledby="pending-suggestions-title">
          <div>
            <p className="eyebrow">Review queue</p>
            <h2 id="pending-suggestions-title">Pending suggestions</h2>
          </div>
          <div className="suggestion-rows">
            {suggestions.map((suggestion) => (
              <article key={suggestion.id}>
                <div>
                  <strong>{suggestion.term}</strong>
                  <span>{suggestion.reason}</span>
                </div>
                <div className="suggestion-actions">
                  <button onClick={() => reviewSuggestion(suggestion.id, "approved")}>
                    <Check size={17} /> Approve
                  </button>
                  <button className="secondary" onClick={() => reviewSuggestion(suggestion.id, "rejected")}>
                    <X size={17} /> Reject
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <div className="word-list-summary">
        <span>{loadingWords ? "Loading words..." : `Showing ${rangeStart}-${rangeEnd} of ${page.total}`}</span>
        {(query || masteryState !== "all" || diagnosticStatus !== "all") ? <strong>Filtered</strong> : null}
      </div>

      <div className="word-management-table-wrap">
        <table className="word-management-table">
          <thead>
            <tr>
              <th>Word</th>
              <th>Source</th>
              <th>Level</th>
              <th>Learning state</th>
              <th>Schedule</th>
              <th>Last attempt</th>
              <th><span className="visually-hidden">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {!loadingWords && !page.items.length ? (
              <tr>
                <td className="word-list-empty" colSpan={7}>
                  <Search size={26} />
                  <strong>No matching words</strong>
                  <span>Change the category or clear the filters.</span>
                </td>
              </tr>
            ) : page.items.map((word) => (
              <tr key={word.id}>
                <td data-label="Word">
                  <strong className="word-term">{word.term}</strong>
                  <span className="word-meaning">{word.short_meaning ?? word.example_sentence ?? "No meaning added"}</span>
                </td>
                <td data-label="Source">
                  <span className="status-pill neutral">{word.source_label}</span>
                  {word.source_list ? <small>{word.source_list.replace(/_/g, " ")}</small> : null}
                </td>
                <td data-label="Level">
                  <strong>{word.cefr_level ?? title(word.level)}</strong>
                  <small>{word.frequency_rank ? `Rank ${word.frequency_rank.toLocaleString()}` : "No rank"}</small>
                </td>
                <td data-label="Learning state">
                  <span className={`status-pill ${word.mastery_state === "lapse" || word.mastery_state === "trouble" ? "danger" : "learning"}`}>
                    {title(word.mastery_state)}
                  </span>
                  <small>Diagnostic: {title(word.diagnostic_status)}</small>
                </td>
                <td data-label="Schedule">
                  <strong>{word.due_date ? displayDate(word.due_date) : "Not scheduled"}</strong>
                  <small>{word.review_stage ? title(word.review_stage) : "No review stage"}</small>
                </td>
                <td data-label="Last attempt">
                  <strong>{displayDate(word.last_attempt_at)}</strong>
                  {word.last_attempt_correct === true ? <small className="correct-text">Correct</small> : null}
                  {word.last_attempt_correct === false ? <small className="incorrect-text">Missed</small> : null}
                </td>
                <td className="word-row-actions">
                  {word.is_active ? (
                    <>
                      <button className="icon-button compact" aria-label={`Practice ${word.term}`} title="Practice now" onClick={() => applyWordAction(word, "practice")}>
                        <Play size={16} />
                      </button>
                      <button className="icon-button compact" aria-label={`Mark ${word.term} known`} title="Mark known" onClick={() => applyWordAction(word, "mark_known")}>
                        <Check size={16} />
                      </button>
                      <button className="icon-button compact" aria-label={`Reset ${word.term}`} title="Reset learning progress" onClick={() => applyWordAction(word, "reset")}>
                        <RotateCcw size={16} />
                      </button>
                      {word.is_personal ? (
                        <button className="icon-button compact" aria-label={`Edit ${word.term}`} title="Edit personal word" onClick={() => openEditor(word)}>
                          <Pencil size={16} />
                        </button>
                      ) : null}
                      <button className="icon-button compact danger-button" aria-label={`Archive ${word.term}`} title="Archive" onClick={() => applyWordAction(word, "archive")}>
                        <ArchiveIcon size={16} />
                      </button>
                    </>
                  ) : (
                    <button className="secondary" onClick={() => applyWordAction(word, "restore")}>
                      <ArchiveRestore size={17} /> Restore
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="word-pagination">
        <button className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(offset - limit, 0))}>
          <ChevronLeft size={17} /> Previous
        </button>
        <span>{rangeStart}-{rangeEnd} of {page.total}</span>
        <button className="secondary" disabled={offset + limit >= page.total} onClick={() => setOffset(offset + limit)}>
          Next <ChevronRight size={17} />
        </button>
      </div>

      {editing && editDraft ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) {
            setEditing(null);
            setEditDraft(null);
          }
        }}>
          <section className="word-edit-modal" role="dialog" aria-modal="true" aria-labelledby="edit-word-title">
            <div className="section-head">
              <div>
                <p className="eyebrow">Personal word</p>
                <h2 id="edit-word-title">Edit {editing.term}</h2>
              </div>
              <button className="icon-button compact" aria-label="Close editor" title="Close" onClick={() => {
                setEditing(null);
                setEditDraft(null);
              }}>
                <X size={18} />
              </button>
            </div>
            <form className="word-edit-form" onSubmit={saveEdit}>
              <label>
                <span>Word</span>
                <input value={editDraft.term} onChange={(event) => setEditDraft({ ...editDraft, term: event.target.value })} required />
              </label>
              <div className="word-edit-grid">
                <label>
                  <span>Part of speech</span>
                  <input value={editDraft.part_of_speech} onChange={(event) => setEditDraft({ ...editDraft, part_of_speech: event.target.value })} />
                </label>
                <label>
                  <span>CEFR level</span>
                  <select value={editDraft.cefr_level} onChange={(event) => setEditDraft({ ...editDraft, cefr_level: event.target.value })}>
                    <option value="">Not set</option>
                    {["A1", "A2", "B1", "B2", "C1", "C2"].map((level) => <option key={level}>{level}</option>)}
                  </select>
                </label>
              </div>
              <label>
                <span>Meaning</span>
                <textarea value={editDraft.short_meaning} onChange={(event) => setEditDraft({ ...editDraft, short_meaning: event.target.value })} />
              </label>
              <label>
                <span>Example sentence</span>
                <textarea value={editDraft.example_sentence} onChange={(event) => setEditDraft({ ...editDraft, example_sentence: event.target.value })} />
              </label>
              <div className="modal-actions">
                <button type="button" className="secondary" onClick={() => {
                  setEditing(null);
                  setEditDraft(null);
                }}>Cancel</button>
                <button>Save changes</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function AccuracyTrend({ points }: { points: Dashboard["stats"]["accuracy_trend"] }) {
  const activeDays = points.filter((point) => point.total_attempts > 0);
  const maxAttempts = Math.max(...points.map((point) => point.total_attempts), 1);
  return (
    <div className="accuracy-trend" role="img" aria-label={`First-try accuracy over ${points.length} days; ${activeDays.length} active days`}>
      <div className="trend-scale"><span>100%</span><span>50%</span><span>0%</span></div>
      <div className="trend-bars">
        {points.map((point) => (
          <div className={point.total_attempts ? "trend-day active" : "trend-day"} key={point.day}>
            <i
              title={`${displayDate(point.day)}: ${Math.round(point.accuracy * 100)}% across ${point.total_attempts} attempts`}
              style={{
                "--accuracy": `${Math.max(point.accuracy * 100, point.total_attempts ? 4 : 1)}%`,
                "--volume": `${Math.max((point.total_attempts / maxAttempts) * 100, point.total_attempts ? 16 : 4)}%`
              } as CSSProperties}
            />
          </div>
        ))}
      </div>
      <div className="trend-dates">
        <span>{points[0] ? displayDate(points[0].day) : ""}</span>
        <span>{points.length ? displayDate(points[points.length - 1].day) : ""}</span>
      </div>
    </div>
  );
}

function ProgressView({ dashboard, onNavigate }: { dashboard: Dashboard | null; onNavigate: (view: ViewKey) => void }) {
  if (!dashboard) return null;
  const stats = dashboard.stats;
  const recommendedAction = nextBestAction(dashboard, null);
  const hasAttempts = stats.accuracy_trend.some((point) => point.total_attempts > 0);
  const hasLearningHistory = stats.first_try_accuracy > 0
    || stats.diagnostic_tested_words > 0
    || stats.practice_distinct_words > 0
    || stats.dictation_distinct_words > 0
    || stats.oxford_explored_words > 0;
  const recentModeRows = stats.recent_mode_accuracy.map((mode) => ({
    label: title(mode.mode),
    value: Math.round(mode.accuracy * 100),
    tone: mode.mode === "dictation" ? "orange" : mode.mode === "exploration" ? "green" : "blue",
    suffix: "%"
  }));
  const patternRows = stats.pattern_error_rates.map((pattern) => ({
    label: pattern.label,
    value: Math.round(pattern.recent_error_rate * 100),
    tone: "red",
    suffix: "%"
  }));

  return (
    <section className="progress-screen">
      <header className="progress-page-head">
        <div>
          <p className="eyebrow">Learning report</p>
          <h1>Progress</h1>
          <p>Use outcomes to judge learning, and queue health to decide what to do next.</p>
        </div>
        <button onClick={() => onNavigate(recommendedAction.view)}>
          Continue Learning <ChevronRight size={17} />
        </button>
      </header>

      {!hasAttempts ? (
        <GuidedEmptyState
          icon={TrendingUp}
          title={hasLearningHistory ? "No activity in the last 14 days" : "No learning trend yet"}
          text={hasLearningHistory
            ? "Resume your Daily Plan to refresh accuracy trends and keep reviews from becoming overdue."
            : "Complete your first Diagnostic session. Accuracy, retention, lapses, and pattern weaknesses will appear here as you practice."}
          actionLabel={hasLearningHistory ? recommendedAction.actionLabel : "Start Diagnostic"}
          onAction={() => onNavigate(hasLearningHistory ? recommendedAction.view : "diagnostic")}
        />
      ) : null}

      <div className="progress-kpis">
        <Metric icon={CheckCircle2} label="14-Day Retention" value={percent(stats.retention_accuracy_14d)} sub="Learning outcome: delayed first try" />
        <Metric icon={XCircle} label="Lapse Rate" value={percent(stats.lapse_rate)} sub="Learning outcome: stable words missed" />
        <Metric icon={CalendarCheck2} label="Actionable Queue" value={stats.practice_queue_words} sub="Queue health: ready for practice" />
        <Metric icon={Trophy} label="Stable Known" value={stats.stable_known_words} sub="Learning outcome: audited recall" />
      </div>

      <div className="page-grid progress-detail-grid">
        <section className="panel span-2">
          <div className="section-head">
            <div>
              <span className="metric-kind outcome">Learning outcome</span>
              <h2>14-Day First-Try Trend</h2>
            </div>
            <span className="muted">Accuracy and practice volume by day</span>
          </div>
          <AccuracyTrend points={stats.accuracy_trend} />
        </section>

        <section className="panel">
          <span className="metric-kind outcome">Learning outcome</span>
          <h2>Recent Mode Accuracy</h2>
          {recentModeRows.length ? <MiniBars rows={recentModeRows} max={100} /> : <p className="muted">Mode accuracy appears after your first session.</p>}
        </section>

        <section className="panel">
          <span className="metric-kind outcome">Learning outcome</span>
          <h2>Retention Windows</h2>
          <MiniBars
            rows={[
              { label: "7 days", value: Math.round(stats.retention_accuracy_7d * 100), tone: "green", suffix: "%" },
              { label: "14 days", value: Math.round(stats.retention_accuracy_14d * 100), tone: "blue", suffix: "%" },
              { label: "30 days", value: Math.round(stats.retention_accuracy_30d * 100), tone: "purple", suffix: "%" },
              { label: "60 days", value: Math.round(stats.retention_accuracy_60d * 100), tone: "orange", suffix: "%" }
            ]}
            max={100}
          />
        </section>

        <section className="panel">
          <span className="metric-kind outcome">Learning outcome</span>
          <h2>Pattern Weaknesses</h2>
          {patternRows.length ? <MiniBars rows={patternRows} max={100} /> : <p className="muted">Missed spellings will reveal which letter patterns need attention.</p>}
        </section>

        <section className="panel">
          <span className="metric-kind queue">Queue health</span>
          <h2>What Needs Attention</h2>
          <MiniBars
            rows={[
              { label: "Reviews due", value: stats.due_today_words, tone: "blue" },
              { label: "Review debt", value: stats.review_debt_words, tone: "red" },
              { label: "Trouble words", value: stats.trouble_words, tone: "orange" },
              { label: "Delayed audits", value: stats.due_audit_words, tone: "purple" }
            ]}
          />
        </section>

        <section className="panel">
          <span className="metric-kind setup">Setup health</span>
          <h2>Library Coverage</h2>
          <MiniBars
            rows={[
              { label: "Oxford loaded", value: Math.round((stats.oxford_loaded_words / Math.max(stats.oxford_target_words, 1)) * 100), tone: "blue", suffix: "%" },
              { label: "Explored", value: Math.round((stats.oxford_explored_words / Math.max(stats.oxford_loaded_words, 1)) * 100), tone: "green", suffix: "%" },
              { label: "Content ready", value: Math.round((stats.content_generated_words / Math.max(stats.oxford_loaded_words, 1)) * 100), tone: "purple", suffix: "%" },
              { label: "Audio ready", value: Math.round((stats.audio_generated_words / Math.max(stats.oxford_loaded_words, 1)) * 100), tone: "orange", suffix: "%" }
            ]}
            max={100}
          />
        </section>

        <section className="panel">
          <div className="section-head">
            <div>
              <span className="metric-kind outcome">Learning behavior</span>
              <h2>Recent Activity</h2>
            </div>
          </div>
          {dashboard.recent_activity.length ? (
            <ActivityList rows={dashboard.recent_activity} />
          ) : (
            <p className="muted">Your completed sessions will appear here.</p>
          )}
        </section>
      </div>
    </section>
  );
}

const achievementCategoryDetails: Record<string, { label: string; description: string; view: ViewKey }> = {
  exploration: { label: "Exploration", description: "Build breadth by meeting useful new words.", view: "exploration" },
  practice: { label: "Practice", description: "Build consistency through focused repair sessions.", view: "practice" },
  dictation: { label: "Listening", description: "Connect spoken language with accurate spelling.", view: "dictation" },
  accuracy: { label: "Accuracy", description: "Improve reliable first-try recall.", view: "diagnostic" },
  streak: { label: "Consistency", description: "Return regularly enough for spacing to work.", view: "practice" }
};

function AchievementsView({ onNavigate }: { onNavigate: (view: ViewKey) => void }) {
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  useEffect(() => {
    getJson<Achievement[]>("/achievements").then(setAchievements).catch(() => undefined);
  }, []);
  const locked = achievements
    .filter((achievement) => !achievement.unlocked_at)
    .sort((left, right) => (right.progress / right.target) - (left.progress / left.target));
  const nextMilestone = locked[0] ?? null;
  const groups = Object.entries(achievementCategoryDetails)
    .map(([category, details]) => ({
      category,
      details,
      achievements: achievements.filter((achievement) => achievement.category === category)
    }))
    .filter((group) => group.achievements.length);

  return (
    <section className="achievements-screen">
      <header className="progress-page-head">
        <div>
          <p className="eyebrow">Milestones</p>
          <h1>Achievements</h1>
          <p>Milestones reflect the learning behaviors that build durable spelling recall.</p>
        </div>
      </header>

      {nextMilestone ? (
        <section className="next-milestone-band" aria-labelledby="next-milestone-title">
          <Target size={28} />
          <div>
            <span>Next achievable milestone</span>
            <h2 id="next-milestone-title">{nextMilestone.title}</h2>
            <p>{Math.max(nextMilestone.target - nextMilestone.progress, 0)} more to complete. {nextMilestone.description}</p>
            <div className="progress-line"><i style={{ width: `${Math.min((nextMilestone.progress / nextMilestone.target) * 100, 100)}%` }} /></div>
          </div>
          <button onClick={() => onNavigate(achievementCategoryDetails[nextMilestone.category]?.view ?? "practice")}>
            Make Progress <ChevronRight size={17} />
          </button>
        </section>
      ) : achievements.length ? (
        <section className="next-milestone-band complete">
          <Award size={28} />
          <div><span>Milestones complete</span><h2>All current achievements unlocked</h2></div>
          <button onClick={() => onNavigate("progress")}>View Progress</button>
        </section>
      ) : null}

      {groups.map((group) => (
        <section className="achievement-group" key={group.category}>
          <div className="achievement-group-head">
            <div>
              <h2>{group.details.label}</h2>
              <p>{group.details.description}</p>
            </div>
            <button className="ghost" onClick={() => onNavigate(group.details.view)}>Open {group.details.label}</button>
          </div>
          <div className="achievement-grid">
            {group.achievements.map((achievement) => (
              <article className={achievement.unlocked_at ? "achievement unlocked" : "achievement"} key={achievement.code}>
                {achievement.unlocked_at ? <Award /> : <Trophy />}
                <div>
                  <h3>{achievement.title}</h3>
                  <p>{achievement.description}</p>
                </div>
                <div className="progress-line"><i style={{ width: `${Math.min((achievement.progress / achievement.target) * 100, 100)}%` }} /></div>
                <span>{achievement.unlocked_at ? "Unlocked" : `${achievement.progress} / ${achievement.target}`}</span>
              </article>
            ))}
          </div>
        </section>
      ))}
    </section>
  );
}

function SettingsView({
  readiness,
  onRefresh,
  onRefreshReadiness
}: {
  readiness: ReadinessReport | null;
  onRefresh: () => Promise<void>;
  onRefreshReadiness: () => Promise<ReadinessReport>;
}) {
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
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [checkingReadiness, setCheckingReadiness] = useState(false);

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
    setSettingsError(null);
  }

  async function refreshEnvironment() {
    setCheckingReadiness(true);
    try {
      const report = await onRefreshReadiness();
      if (report.status === "unavailable") {
        setSettings(null);
        setSettingsError("Database-backed settings are unavailable until the required database checks pass.");
      } else if (!settings) {
        await load();
      }
    } catch (err) {
      setSettingsError(err instanceof Error ? err.message : "Environment readiness could not be checked.");
    } finally {
      setCheckingReadiness(false);
    }
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
    refreshEnvironment().catch(() => undefined);
  }, []);

  if (!settings) {
    return (
      <section className="panel full">
        <h1>Settings</h1>
        <EnvironmentReadiness
          report={readiness}
          refreshing={checkingReadiness}
          onRefresh={refreshEnvironment}
        />
        {settingsError ? <div className="banner error">{settingsError}</div> : null}
      </section>
    );
  }
  return (
    <section className="panel full">
      <h1>Settings</h1>
      <EnvironmentReadiness
        report={readiness}
        refreshing={checkingReadiness}
        onRefresh={refreshEnvironment}
      />
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

function EnvironmentReadiness({
  report,
  refreshing,
  onRefresh
}: {
  report: ReadinessReport | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const summary = report?.status === "ready"
    ? "Environment ready"
    : report?.status === "degraded"
      ? "Optional setup needs attention"
      : report?.status === "unavailable"
        ? "Required service unavailable"
        : "Readiness not checked";

  return (
    <section className="readiness-section" aria-labelledby="readiness-heading">
      <div className="readiness-head">
        <div>
          <p className="eyebrow">Environment</p>
          <h2 id="readiness-heading">System Readiness</h2>
          <p>
            {summary}
            {report ? ` · ${report.database_target}` : ""}
          </p>
        </div>
        <button className="secondary" disabled={refreshing} onClick={onRefresh}>
          <RefreshCcw className={refreshing ? "spin" : undefined} size={16} />
          {refreshing ? "Checking" : "Refresh"}
        </button>
      </div>
      {report ? (
        <div className="readiness-list">
          {report.checks.map((check) => {
            const Icon = check.status === "ready" ? CheckCircle2 : check.status === "warning" ? AlertTriangle : XCircle;
            return (
              <div className={`readiness-row ${check.status}`} key={check.key}>
                <Icon size={20} />
                <div>
                  <strong>{check.label}</strong>
                  <p>{check.detail}</p>
                  {check.action ? <small><b>Next:</b> {check.action}</small> : null}
                </div>
                <span>{title(check.status)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="readiness-empty">The backend readiness report is unavailable.</div>
      )}
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
