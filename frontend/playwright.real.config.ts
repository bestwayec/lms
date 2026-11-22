import { defineConfig } from '@playwright/test';

/**
 * Real Django → React journeys (no API mocks). Needs Django on 127.0.0.1:8000
 * with config.settings.e2e and `manage.py seed_e2e_journey`; see
 * docs/GRANDEC_NEXT_PROGRESS.md "Real E2E" for the exact commands.
 */
export default defineConfig({
  testDir: './e2e/real',
  workers: 1,
  fullyParallel: false,
  expect: { timeout: 15_000 },
  timeout: 180_000,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'off',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {},
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
  },
});
