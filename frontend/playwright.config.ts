import { defineConfig, devices } from "@playwright/test"

/**
 * Uçtan uca testler az ve demo odaklı. Backend gerektiren testler `BACKEND=1` ile açılır
 * (backend :8000'de açık olmalı); geri kalanı yalnızca Next.js ile çalışır.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3100",
    viewport: { width: 1600, height: 900 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 900 } } }],
  webServer: {
    command: "npm run dev -- --port 3100",
    url: "http://localhost:3100",
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
