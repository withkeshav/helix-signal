import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3080';

export default defineConfig({
  testDir: './e2e',
  timeout: 120000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  retries: 1,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    actionTimeout: 10000,
    launchOptions: {
      // Full Chromium supports import maps; the headless shell does not.
      args: ['--no-sandbox'],
    },
    // NOTE: Tab panels no longer rely on CSS x-transition for visibility
    // (x-show alone toggles display), so we deliberately do NOT force
    // reducedMotion: 'reduce' here. Forcing reduced motion suppressed the
    // browser transitions Alpine's x-transition machinery waits on, wedging
    // panels in the leave-end (opacity-0/hidden) state.
  },
  projects: [
    {
      name: 'chromium',
      // Force the downloaded full Chromium instead of the headless shell.
      use: { ...devices['Desktop Chrome'], channel: 'chromium' },
    },
  ],
  webServer: process.env.CI
    ? {
        command:
          'cd .. && FRONTEND_PORT=3080 docker compose up -d --wait backend frontend && sleep 3 && curl -sf http://localhost:3080/ > /dev/null',
        url: BASE_URL,
        timeout: 180000,
        reuseExistingServer: true,
      }
    : undefined,
});
