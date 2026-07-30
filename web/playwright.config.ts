import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: "chrome",
    trace: "retain-on-failure"
  },
  webServer: {
    command: "npm run dev",
    reuseExistingServer: true,
    timeout: 120000,
    url: "http://127.0.0.1:5173"
  }
});
