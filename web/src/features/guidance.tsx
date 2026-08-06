import {
  Compass,
  ListChecks,
  Mic,
  PenLine
} from "lucide-react";
import type { Dashboard, ReadinessReport, ViewKey } from "../types";

export type ExplorationPool = "oxford" | "suggested" | "mixed";

export type ModeCard = { view: ViewKey; title: string; text: string; cta: string; tone: string; icon: typeof Compass };

export type ModeAvailability = {
  countLabel: string;
  detail: string;
  actionLabel: string;
  actionView: ViewKey;
  ready: boolean;
};

export type EmptyStateAction = {
  title: string;
  text: string;
  primaryLabel: string;
  primaryView: ViewKey;
  secondaryLabel?: string;
  secondaryView?: ViewKey;
};

export const modeCards: ModeCard[] = [
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

export function explorationReadyWords(stats: Dashboard["stats"]): number {
  const oxfordRemaining = Math.max(stats.oxford_loaded_words - stats.oxford_explored_words, 0);
  return oxfordRemaining + stats.llm_suggested_words;
}

export function modeAvailability(card: ModeCard, dashboard: Dashboard | null): ModeAvailability {
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
        countLabel: `${stats.dictation_ready_words} texts`,
        detail: "Reviewed texts are ready at your adaptive level.",
        actionLabel: "Start Dictation",
        actionView: "dictation",
        ready: true
      };
    }
    return {
      countLabel: "0 texts",
      detail: "No reviewed dictation texts are available at this level.",
      actionLabel: "Open Dictation",
      actionView: "dictation",
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

export function practiceEmptyState(mode: "diagnostic" | "practice" | "dictation", dashboard: Dashboard | null): EmptyStateAction {
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

export function explorationEmptyState(pool: ExplorationPool, dashboard: Dashboard | null, fallback?: string | null): EmptyStateAction | null {
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

export type NextBestAction = {
  view: ViewKey;
  title: string;
  reason: string;
  actionLabel: string;
};

export function nextBestAction(dashboard: Dashboard, readiness: ReadinessReport | null): NextBestAction {
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
