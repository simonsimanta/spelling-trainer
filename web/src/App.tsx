import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Compass,
  Home,
  ListChecks,
  Loader2,
  Mic,
  PenLine,
  Settings as SettingsIcon,
  Trophy
} from "lucide-react";
import { useEffect, useState } from "react";

import { getJson, postJson } from "./api";
import { AchievementsView } from "./features/AchievementsView";
import { DashboardView } from "./features/DashboardView";
import { ExplorationView } from "./features/ExplorationView";
import { PracticeView } from "./features/PracticeView";
import { ProgressView } from "./features/ProgressView";
import { SettingsView } from "./features/SettingsView";
import { WordListsView } from "./features/WordListsView";
import type {
  Dashboard,
  ReadinessReport,
  SpellingSession,
  ViewKey
} from "./types";

const navItems: Array<{ key: ViewKey; label: string; icon: typeof BookOpen }> = [
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
