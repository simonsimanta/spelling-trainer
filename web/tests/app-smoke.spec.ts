import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import {
  dashboardWithStats,
  dictationProgress,
  dictationResult,
  dictationSession,
  firstRunDashboard,
  oxfordLoadStatus,
  pendingBulkStatus,
  practiceSession,
  readyEnvironment,
  readySettings
} from "./fixtures/app-data";

function captureBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().toLowerCase().includes("favicon")) {
      errors.push(`console: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => errors.push(`page: ${error.message}`));
  return errors;
}

async function mockAppShell(page: Page, dashboard = firstRunDashboard) {
  await page.route("**/readiness", (route) => route.fulfill({ json: readyEnvironment }));
  await page.route("**/dashboard", (route) => route.fulfill({ json: dashboard }));
  await page.route("**/spelling/dictation/progress", (route) => route.fulfill({ json: dictationProgress }));
  await page.route("**/spelling/audio/assets/**", (route) => {
    route.fulfill({ body: "audio", contentType: "audio/mpeg" });
  });
  await page.route("**/spelling/dictation/texts**", (route) => {
    const personalText = {
      id: 16,
      title: "Concert preparation",
      content: "The careful musician checked every instrument before tonight's important concert.",
      source_type: "personal",
      level: "sentence",
      locale: "en-GB",
      status: "reviewed",
      word_count: 10,
      sentence_count: 1,
      quality_warnings: [],
      allow_ai_adaptation: true,
      adapted_from_id: null,
      targets: [{ word_id: null, term: "instrument", order_index: 0 }],
      target_count: 1,
      use_count: 0,
      last_used_at: null,
      created_at: "2026-08-06T12:00:00Z"
    };
    if (route.request().method() === "POST") {
      route.fulfill({ json: personalText });
      return;
    }
    route.fulfill({
      json: {
        items: [
          {
            ...personalText,
            id: 1,
            title: "Posting the letter",
            content: null,
            source_type: "curated",
            allow_ai_adaptation: false,
            targets: [],
            target_count: 1
          }
        ],
        total: 1,
        counts: { sentence: 1, passage: 0, paragraph: 0, personal: 0 }
      }
    });
  });
}

test("Dashboard renders without browser errors", async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  await mockAppShell(page);

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Run your diagnostic baseline" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose a Mode" })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test("Exploration explains an empty source pool and offers a recovery action", async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  await mockAppShell(page);
  await page.route("**/spelling/exploration/next?*", (route) => {
    route.fulfill({ json: null });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Exploration" }).click();

  await expect(page.getByRole("heading", { name: "Exploration pool is empty" })).toBeVisible();
  await expect(page.getByText("Oxford words are not loaded yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load Oxford Words" })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test("Practice covers empty and populated queues with deterministic sessions", async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  let useEmptySession = true;
  const dashboard = dashboardWithStats({ diagnostic_ready_words: 19, practice_queue_words: 1 });
  await mockAppShell(page, dashboard);
  await page.route("**/spelling/sessions", (route) => {
    route.fulfill({
      json: useEmptySession
        ? { ...practiceSession, total_items: 0, items: [] }
        : practiceSession
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Practice" }).click();
  await page.getByRole("button", { name: "Start Practice" }).click();
  await expect(page.getByRole("heading", { name: "No practice words yet" })).toBeVisible();
  await expect(page.getByText("19 diagnostic words are ready.")).toBeVisible();

  await page.getByRole("button", { name: "Back" }).click();
  useEmptySession = false;
  await page.getByRole("button", { name: "Start Practice" }).click();
  await expect(page.getByText("Question 1 of 1")).toBeVisible();
  await expect(page.getByPlaceholder("Type the spelling here...")).toBeFocused();
  expect(browserErrors).toEqual([]);
});

test("Practice prefetches the current audio item and the next two", async ({ page }) => {
  await mockAppShell(page, dashboardWithStats({ diagnostic_ready_words: 19, practice_queue_words: 4 }));
  const prefetched = new Set<string>();
  await page.route("**/spelling/audio/assets/**", (route) => {
    prefetched.add(new URL(route.request().url()).pathname);
    route.fulfill({ body: "audio", contentType: "audio/mpeg" });
  });
  await page.route("**/spelling/sessions", (route) => {
    route.fulfill({
      json: {
        ...practiceSession,
        total_items: 4,
        items: Array.from({ length: 4 }, (_, index) => ({
          ...practiceSession.items[0],
          session_item_id: index + 1,
          audio_asset_id: index + 1,
          audio_url: `/spelling/audio/assets/${index + 1}`
        }))
      }
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Practice" }).click();
  await page.getByRole("button", { name: "Start Practice" }).click();
  await expect(page.getByText("Question 1 of 4")).toBeVisible();
  await expect.poll(() => [...prefetched].sort()).toEqual([
    "/spelling/audio/assets/1",
    "/spelling/audio/assets/2",
    "/spelling/audio/assets/3"
  ]);
});

test("Adaptive dictation hides the answer until layered grading is returned", async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  const dashboard = dashboardWithStats({ diagnostic_ready_words: 19, dictation_ready_words: 1 });
  await mockAppShell(page, dashboard);
  await page.route("**/spelling/sessions", (route) => {
    route.fulfill({ json: dictationSession });
  });
  await page.route("**/spelling/dictation/submissions", (route) => {
    route.fulfill({ json: dictationResult });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Dictation" }).click();
  await expect(page.getByRole("heading", { name: "Sentence level" })).toBeVisible();
  await page.getByRole("button", { name: "Start sentence" }).click();
  await expect(page.getByRole("heading", { name: "Text 1 of 1" })).toBeVisible();
  await expect(page.getByText(dictationResult.expected_text)).toHaveCount(0);

  await page.getByPlaceholder("Type everything you hear...").fill(dictationResult.attempt_text);
  await page.getByRole("button", { name: "Check dictation" }).click();

  const result = page.getByLabel("Dictation result");
  await expect(result).toContainText("Target spelling");
  await expect(result).toContainText("Words");
  await expect(result).toContainText("Capitalisation");
  await expect(result).toContainText("Punctuation");
  await expect(result).toContainText(dictationResult.expected_text);
  expect(browserErrors).toEqual([]);
});

test("Dictation library imports personal text", async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  await mockAppShell(page);

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Dictation" }).click();
  await expect(page.getByRole("heading", { name: "Text library" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Posting the letter" })).toBeVisible();

  await page.getByRole("button", { name: "Add personal text" }).click();
  await page.getByLabel("Title").fill("Concert preparation");
  await page.getByRole("textbox", { name: "Text", exact: true }).fill("The careful musician checked every instrument before tonight's important concert.");
  await page.getByLabel("Target spellings").fill("instrument");
  await page.getByRole("button", { name: "Add text" }).click();

  await expect(page.getByText("Personal text added.")).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test("Settings previews a content batch before generation", async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  await mockAppShell(page);
  await page.route("**/settings", (route) => route.fulfill({ json: readySettings }));
  await page.route("**/spelling/oxford/load-status", (route) => route.fulfill({ json: oxfordLoadStatus }));
  await page.route("**/spelling/content/bulk-status", (route) => route.fulfill({ json: pendingBulkStatus }));
  await page.route("**/spelling/audio/bulk-status?*", (route) => {
    route.fulfill({ json: { ...pendingBulkStatus, voice: "alloy", model: "gpt-4o-mini-tts" } });
  });
  await page.route("**/spelling/content/bulk-preview?*", (route) => {
    route.fulfill({
      json: {
        total_words: 4,
        generated: 0,
        pending: 4,
        failed: 0,
        will_process: 4,
        limit: 100,
        estimated_api_calls: 4,
        model: "gpt-4o-mini",
        voice: null
      }
    });
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Preview Content Batch" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Generate word learning content" })).toBeVisible();
  await expect(dialog).toContainText("This may use OpenAI API quota.");
  await expect(dialog.getByRole("button", { name: "Generate batch" })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test("mobile navigation remains usable across the full tab list", async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAppShell(page);
  await page.route("**/settings", (route) => route.fulfill({ json: readySettings }));
  await page.route("**/spelling/oxford/load-status", (route) => route.fulfill({ json: oxfordLoadStatus }));
  await page.route("**/spelling/content/bulk-status", (route) => route.fulfill({ json: pendingBulkStatus }));
  await page.route("**/spelling/audio/bulk-status?*", (route) => route.fulfill({ json: pendingBulkStatus }));

  await page.goto("/");
  const navigation = page.getByRole("navigation");
  await expect(navigation.getByRole("button", { name: "Dashboard" })).toBeVisible();
  await navigation.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
  await expect(navigation).toHaveCSS("overflow-x", "auto");
  expect(browserErrors).toEqual([]);
});
