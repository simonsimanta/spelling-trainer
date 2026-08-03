import {
  Award,
  BarChart3,
  BookOpen,
  CalendarCheck2,
  CheckCircle2,
  ChevronRight,
  Compass,
  ListChecks,
  Mic,
  PenLine,
  Sparkles,
  Target,
  Trophy,
  XCircle
} from "lucide-react";



import type { Dashboard, ReadinessReport, ViewKey } from "../types";
import {
  ActivityList,
  FunnelChart,
  GuidedEmptyState,
  Metric,
  MiniBars,
  MiniStat,
  SegmentedBar
} from "../components/LearningMetrics";
import { percent } from "../utils/format";
import { modeAvailability, modeCards, nextBestAction } from "./guidance";


export function DashboardView({
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
