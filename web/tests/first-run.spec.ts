import { expect, test } from "@playwright/test";

const firstRunDashboard = {
  profile: {
    id: 1,
    name: "Learner",
    avatar: "default",
    level_label: "Starter",
    current_streak: 0,
    best_streak: 0,
    points: 0,
    practice_time_seconds: 0,
    daily_goal: 10
  },
  overview: {
    due_today: 0,
    hard_words: 0,
    attempts_today: 0,
    points_today: 0
  },
  core5k: {
    total_words: 5000,
    attempted_words: 0,
    mastered_words: 0,
    in_learning_words: 0,
    due_today_words: 0,
    coverage_percent: 0
  },
  stats: {
    oxford_target_words: 5000,
    oxford_loaded_words: 0,
    oxford_explored_words: 0,
    practice_distinct_words: 0,
    dictation_distinct_words: 0,
    mastered_words: 0,
    learning_words: 19,
    trouble_words: 0,
    due_today_words: 19,
    forced_correction_words: 0,
    practice_queue_words: 0,
    dictation_ready_words: 0,
    diagnostic_ready_words: 19,
    diagnostic_tested_words: 0,
    diagnostic_missed_words: 0,
    diagnostic_accuracy: 0,
    first_try_accuracy: 0,
    exploration_accuracy: 0,
    practice_accuracy: 0,
    dictation_accuracy: 0,
    retention_accuracy_7d: 0,
    retention_accuracy_14d: 0,
    retention_accuracy_30d: 0,
    retention_accuracy_60d: 0,
    lapse_rate: 0,
    review_debt_words: 19,
    known_provisional_words: 0,
    stable_known_words: 0,
    due_audit_words: 0,
    llm_suggested_words: 0,
    llm_pending_suggestions: 0,
    content_generated_words: 0,
    audio_generated_words: 0,
    pattern_error_rates: []
  },
  words_learned: 0,
  accuracy: 0,
  practice_time_seconds: 0,
  recent_activity: [],
  achievements: []
};

const diagnosticSession = {
  session_id: 1,
  session_type: "diagnostic",
  total_items: 1,
  completed_items: 0,
  items: [
    {
      session_item_id: 1,
      word_id: 1,
      term: "definitely",
      item_type: "review_word",
      mode: "diagnostic",
      prompt_text: "Listen to the word and type its spelling.",
      source_reason: "starter diagnostic",
      queue_reason: "starter diagnostic",
      status: "pending",
      audio_ready: true,
      choices: null,
      short_meaning: "Without doubt; clearly and certainly.",
      part_of_speech: "adverb",
      chunked_form: "de-fin-ite-ly",
      phonetic_hint: null,
      difficulty_score: 0.5
    }
  ]
};

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
  await expect(page.getByRole("heading", { name: "Choose a Mode" })).toBeVisible();
  await expect(page.getByText("19 ready")).toBeVisible();

  await page.getByRole("navigation").getByRole("button", { name: "Diagnostic" }).click();
  await page.getByRole("button", { name: /Start Diagnostic/ }).click();

  await expect(page.getByText("Question 1 of 1")).toBeVisible();
  await expect(page.getByText("Starter Diagnostic")).toBeVisible();
  await expect(page.getByPlaceholder("Type the spelling here...")).toBeFocused();
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
