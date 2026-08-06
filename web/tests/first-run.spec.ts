import { expect, test } from "@playwright/test";

import {
  diagnosticSession,
  dictationProgress,
  firstRunDashboard,
  paragraphDictationSession,
  readyEnvironment
} from "./fixtures/app-data";

test("first-run dashboard exposes Diagnostic and starts a diagnostic session", async ({ page }) => {
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: firstRunDashboard });
  });

  await page.route("**/spelling/sessions", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: diagnosticSession });
      return;
    }
    await route.continue();
  });

  await page.goto("/");

  await expect(page.getByRole("navigation").getByRole("button", { name: "Diagnostic" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Run your diagnostic baseline" })).toBeVisible();
  await expect(page.getByText("Next best action")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose a Mode" })).toBeVisible();
  await expect(page.getByText("19 ready")).toBeVisible();

  await page.getByRole("button", { name: "Start Diagnostic" }).first().click();
  await page.getByRole("button", { name: /Start Diagnostic/ }).click();

  await expect(page.getByText("Question 1 of 1")).toBeVisible();
  await expect(page.getByText("Starter Diagnostic")).toBeVisible();
  await expect(page.getByPlaceholder("Type the spelling here...")).toBeFocused();
});

test("progress guides a first-session learner instead of showing empty analytics", async ({ page }) => {
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: firstRunDashboard });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Progress" }).click();

  await expect(page.getByRole("heading", { name: "Progress" })).toBeVisible();
  await expect(page.getByText("No learning trend yet")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Diagnostic" })).toBeVisible();
  await expect(page.getByText("Learning outcome", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Queue health", { exact: true })).toBeVisible();
  await expect(page.getByText("Setup health", { exact: true })).toBeVisible();
});

test("achievements group learning behaviors and recommend the nearest milestone", async ({ page }) => {
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: firstRunDashboard });
  });
  await page.route("**/achievements", async (route) => {
    await route.fulfill({
      json: [
        {
          code: "explore_10",
          title: "Curious Starter",
          description: "Explore 10 new words.",
          category: "exploration",
          target: 10,
          progress: 4,
          unlocked_at: null
        },
        {
          code: "practice_5",
          title: "Focused Practice",
          description: "Complete 5 practice sessions.",
          category: "practice",
          target: 5,
          progress: 4,
          unlocked_at: null
        },
        {
          code: "accuracy_80",
          title: "Accurate Recall",
          description: "Reach 80 percent first-try accuracy.",
          category: "accuracy",
          target: 80,
          progress: 20,
          unlocked_at: null
        }
      ]
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Achievements" }).click();

  await expect(page.getByText("Next achievable milestone")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Focused Practice", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Exploration" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Practice", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Accuracy", exact: true })).toBeVisible();
});

test("settings shows cache status for the selected TTS variant", async ({ page }) => {
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: firstRunDashboard });
  });
  await page.route("**/settings", async (route) => {
    await route.fulfill({
      json: {
        id: 1,
        theme: "light",
        tts_voice: "alloy",
        tts_model: "gpt-4o-mini-tts",
        ai_model: "gpt-4o-mini",
        ai_generation_enabled: true,
        content_bulk_limit: 100
      }
    });
  });
  await page.route("**/readiness", async (route) => {
    await route.fulfill({ json: readyEnvironment });
  });
  await page.route("**/spelling/oxford/load-status", async (route) => {
    await route.fulfill({
      json: {
        target_words: 5000,
        loaded_words: 4,
        remaining_words: 4996,
        next_batch_size: 100,
        source_available: true
      }
    });
  });
  await page.route("**/spelling/content/bulk-status", async (route) => {
    await route.fulfill({ json: { total_words: 4, generated: 0, pending: 4, failed: 0 } });
  });
  await page.route("**/spelling/audio/bulk-status?*", async (route) => {
    const url = new URL(route.request().url());
    const voice = url.searchParams.get("voice") ?? "alloy";
    const model = url.searchParams.get("model") ?? "gpt-4o-mini-tts";
    await route.fulfill({
      json: {
        total_words: 4,
        generated: voice === "coral" ? 1 : 2,
        pending: voice === "coral" ? 3 : 2,
        failed: 0,
        voice,
        model
      }
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Settings" }).click();

  const audioCard = page.getByRole("heading", { name: "Word Audio Cache" }).locator("..");
  await expect(audioCard).toContainText("Alloy");
  await expect(audioCard).toContainText("gpt-4o-mini-tts");
  await expect(audioCard).toContainText("Cache checked");
  await expect(audioCard).toContainText("2 / 4");

  await page.getByLabel("TTS Voice").selectOption("coral");
  await expect(audioCard).toContainText("Coral");
  await expect(audioCard).toContainText("1 / 4");
});

test("database outage shows readiness actions instead of an empty app", async ({ page }) => {
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ status: 503, json: { detail: "Database unavailable." } });
  });
  await page.route("**/settings", async (route) => {
    await route.fulfill({ status: 503, json: { detail: "Database unavailable." } });
  });
  await page.route("**/readiness", async (route) => {
    await route.fulfill({
      json: {
        status: "unavailable",
        database_backend: "postgresql",
        database_target: "Supabase PostgreSQL",
        checks: [
          ...readyEnvironment.checks.filter((check) => !["database", "schema"].includes(check.key)),
          {
            key: "database",
            label: "Database connection",
            status: "failed",
            required: true,
            detail: "Supabase PostgreSQL could not be reached.",
            action: "Confirm the database is running and refresh DATABASE_URL, then restart the backend."
          },
          {
            key: "schema",
            label: "Database schema",
            status: "failed",
            required: true,
            detail: "The schema cannot be inspected until the database connection works.",
            action: "Restore the database connection first, then refresh this check."
          }
        ]
      }
    });
  });

  await page.goto("/");

  await expect(page.getByRole("alert").getByText("Database unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("Supabase PostgreSQL could not be reached.")).toBeVisible();
  await page.getByRole("button", { name: "Open Settings" }).click();

  await expect(page.getByRole("heading", { name: "System Readiness" })).toBeVisible();
  await expect(page.getByText("Required service unavailable · Supabase PostgreSQL")).toBeVisible();
  await expect(page.getByText(/Confirm the database is running and refresh DATABASE_URL/)).toBeVisible();
  await expect(page.getByText(/Database-backed settings are unavailable/)).toBeVisible();
});

test("word lists supports management, empty search, duplicates, and practice now", async ({ page }) => {
  const managedWord = {
    id: 41,
    term: "meticulous",
    level: "personal",
    source: "manual",
    source_label: "Personal",
    is_active: true,
    is_personal: true,
    source_list: null,
    short_meaning: "Very careful and precise.",
    example_sentence: "She kept meticulous notes.",
    part_of_speech: "adjective",
    cefr_level: "C1",
    frequency_rank: null,
    mastery_state: "lapse",
    diagnostic_status: "missed",
    known_skipped: false,
    priority_score: 3,
    review_stage: "trouble",
    due_date: "2026-07-30",
    last_attempt_at: "2026-07-30T12:00:00",
    last_attempt_correct: false
  };
  const counts = {
    all: 20,
    oxford: 4,
    personal: 1,
    suggested: 0,
    trouble: 1,
    provisional: 0,
    stable: 0,
    seed: 15,
    archived: 0
  };

  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: firstRunDashboard });
  });
  await page.route("**/readiness", async (route) => {
    await route.fulfill({ json: readyEnvironment });
  });
  await page.route("**/spelling/word-management?*", async (route) => {
    const url = new URL(route.request().url());
    const empty = url.searchParams.get("query") === "zzz";
    await route.fulfill({
      json: {
        items: empty ? [] : [managedWord],
        total: empty ? 0 : 1,
        counts
      }
    });
  });
  await page.route("**/spelling/suggestions?*", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/spelling/words", async (route) => {
    await route.fulfill({
      status: 409,
      json: { detail: "\"meticulous\" already exists in Personal." }
    });
  });
  await page.route("**/spelling/words/41/actions", async (route) => {
    await route.fulfill({
      json: {
        word_id: 41,
        term: "meticulous",
        action: "practice",
        message: "Meticulous is ready for practice."
      }
    });
  });
  await page.route("**/spelling/word-content/41", async (route) => {
    const reviewed = route.request().method() === "PATCH";
    await route.fulfill({
      json: {
        word_id: 41,
        term: "meticulous",
        meaning: "Very careful and precise.",
        ipa: "/məˈtɪkjələs/",
        part_of_speech: "adjective",
        examples: ["She kept meticulous notes."],
        word_family: [{ term: "meticulous", label: "adjective" }],
        chunked_form: "me-tic-u-lous",
        mnemonic: "Check each chunk in order.",
        phonetic_hint: reviewed ? "Stress the second syllable" : null,
        generation_source: reviewed ? "manual" : "fallback",
        quality_warnings: reviewed ? [] : ["AI content generation is disabled in Settings."],
        fallback_reason: reviewed ? null : "AI content generation is disabled in Settings.",
        review_notes: null,
        status: reviewed ? "reviewed" : "fallback"
      }
    });
  });
  await page.route("**/spelling/sessions", async (route) => {
    await route.fulfill({
      json: {
        session_id: 9,
        session_type: "practice",
        total_items: 1,
        completed_items: 0,
        items: [
          {
            session_item_id: 91,
            word_id: 41,
            term: "meticulous",
            item_type: "review_word",
            mode: "practice",
            prompt_text: "Listen to the word and type its spelling.",
            source_reason: "selected from Word Lists",
            queue_reason: "selected from Word Lists",
            selection_score: 3,
            score_breakdown: { manual_selection: 3 },
            status: "pending",
            audio_ready: true,
            choices: null,
            short_meaning: "Very careful and precise.",
            part_of_speech: "adjective"
          }
        ]
      }
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Word Lists" }).click();

  await expect(page.getByRole("heading", { name: "Word Lists" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Personal 1" })).toBeVisible();
  await expect(page.getByText("Very careful and precise.")).toBeVisible();
  await expect(page.getByText("Diagnostic: Missed")).toBeVisible();

  await page.getByRole("button", { name: "Review content for meticulous" }).click();
  const contentDialog = page.getByRole("dialog", { name: "Review meticulous" });
  await expect(contentDialog.getByText("Deterministic fallback")).toBeVisible();
  await contentDialog.getByLabel("Pronunciation hint").fill("Stress the second syllable");
  await contentDialog.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByText("Meticulous content was reviewed and saved.")).toBeVisible();

  await page.getByLabel("New personal word").fill("meticulous");
  await page.getByRole("button", { name: "Add word" }).click();
  await expect(page.getByRole("alert")).toContainText("already exists in Personal");

  await page.getByLabel("Search words").fill("zzz");
  await page.getByRole("button", { name: "Run search" }).click();
  await expect(page.getByText("No matching words")).toBeVisible();

  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByText("Very careful and precise.")).toBeVisible();
  await page.getByRole("button", { name: "Practice meticulous" }).click();

  await expect(page.getByText("Question 1 of 1")).toBeVisible();
  await expect(page.getByText("Selected From Word Lists")).toBeVisible();
});

test("audio failures show an actionable learner message", async ({ page }) => {
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: firstRunDashboard });
  });
  await page.route("**/spelling/sessions", async (route) => {
    await route.fulfill({ json: diagnosticSession });
  });
  await page.route("**/spelling/audio?*", async (route) => {
    await route.fulfill({
      status: 503,
      json: {
        detail: "Audio generation could not reach OpenAI. Check the network connection and try again."
      }
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Diagnostic" }).click();
  await page.getByRole("button", { name: "Start Diagnostic" }).click();
  await page.getByRole("button", { name: "Hear Again" }).click();

  await expect(
    page.getByText(
      "Audio unavailable: Audio generation could not reach OpenAI. Check the network connection and try again."
    )
  ).toBeVisible();
});

test("paragraph dictation supports segment replay and layered results", async ({ page }) => {
  await page.addInitScript(() => {
    class MockAudio {
      onended: (() => void) | null = null;
      play() { return Promise.resolve(); }
    }
    Object.defineProperty(window, "Audio", { configurable: true, value: MockAudio });
  });
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: firstRunDashboard });
  });
  await page.route("**/spelling/dictation/progress", async (route) => {
    await route.fulfill({ json: { ...dictationProgress, current_level: "paragraph" } });
  });
  await page.route("**/spelling/dictation/texts**", async (route) => {
    await route.fulfill({ json: { items: [], total: 0, counts: { sentence: 0, passage: 0, paragraph: 0, personal: 0 } } });
  });
  await page.route("**/spelling/sessions", async (route) => {
    await route.fulfill({ json: paragraphDictationSession });
  });
  await page.route("**/spelling/dictation/items/4/audio**", async (route) => {
    await route.fulfill({ body: "audio", contentType: "audio/mpeg" });
  });
  const expected = "Every Monday, I write a clear schedule. This discipline helps me stay focused. I record progress in a journal.";
  await page.route("**/spelling/dictation/submissions", async (route) => {
    await route.fulfill({
      json: {
        submission_id: 11,
        session_id: 4,
        session_item_id: 4,
        level: "paragraph",
        expected_text: expected,
        attempt_text: expected,
        sentence_segments: expected.split(". "),
        word_error_rate: 0,
        word_accuracy: 1,
        target_accuracy: 1,
        capitalization_accuracy: 1,
        punctuation_accuracy: 1,
        omissions: 0,
        additions: 0,
        substitutions: 0,
        replay_count: 2,
        word_operations: [],
        targets: [
          { word_id: 1, target: "schedule", actual: "schedule", is_correct: true, error_type: null, confidence: 1, feeds_practice: false },
          { word_id: 2, target: "discipline", actual: "discipline", is_correct: true, error_type: null, confidence: 1, feeds_practice: false }
        ],
        session_complete: true,
        current_level: "paragraph",
        level_changed: false
      }
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Dictation" }).click();
  await page.getByRole("button", { name: "Start paragraph" }).click();
  await expect(page.getByText(expected)).toHaveCount(0);
  await page.getByRole("button", { name: "Play complete text" }).click();
  await page.getByRole("button", { name: "Play segment 1" }).click();
  await expect(page.getByText("2 plays")).toBeVisible();
  await page.getByPlaceholder("Type everything you hear...").fill(expected);
  await page.getByRole("button", { name: "Check dictation" }).click();

  const outcomes = page.getByLabel("Dictation result");
  await expect(outcomes).toContainText("Target spelling");
  await expect(outcomes).toContainText("Capitalisation");
  await expect(outcomes).toContainText("Punctuation");
  await expect(outcomes).toContainText(expected);
});
