import {
  CalendarCheck2,
  CheckCircle2,
  ChevronRight,
  TrendingUp,
  Trophy,
  XCircle
} from "lucide-react";
import { CSSProperties } from "react";


import type { Dashboard, ViewKey } from "../types";
import {
  ActivityList,
  GuidedEmptyState,
  Metric,
  MiniBars
} from "../components/LearningMetrics";
import { displayDate, percent, title } from "../utils/format";
import { nextBestAction } from "./guidance";


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

export function ProgressView({ dashboard, onNavigate }: { dashboard: Dashboard | null; onNavigate: (view: ViewKey) => void }) {
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
