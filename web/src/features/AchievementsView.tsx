import {
  Award,
  ChevronRight,
  Target,
  Trophy
} from "lucide-react";
import { useEffect, useState } from "react";

import { getJson } from "../api";
import type { Achievement, ViewKey } from "../types";

const achievementCategoryDetails: Record<string, { label: string; description: string; view: ViewKey }> = {
  exploration: { label: "Exploration", description: "Build breadth by meeting useful new words.", view: "exploration" },
  practice: { label: "Practice", description: "Build consistency through focused repair sessions.", view: "practice" },
  dictation: { label: "Listening", description: "Connect spoken language with accurate spelling.", view: "dictation" },
  accuracy: { label: "Accuracy", description: "Improve reliable first-try recall.", view: "diagnostic" },
  streak: { label: "Consistency", description: "Return regularly enough for spacing to work.", view: "practice" }
};

export function AchievementsView({ onNavigate }: { onNavigate: (view: ViewKey) => void }) {
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
