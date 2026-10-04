import { defineConfig, devices } from '@playwright/test';
import { BASE_URL } from './e2e/auth.js';

/**
 * End-to-end tests run against the real stack: a live backend on :8000 and
 * the Vite dev server on :5173. They are deliberately not mocked, the whole
 * point is to catch the integration failures that unit tests cannot, such as
 * missing CORS, a stale server, or a response shape the UI cannot render.
 *
 * Start the test engine (npm run e2e:engine, which keeps the suite's clicks
 * out of the real usage logs and accounts) and the dev server (npm run dev),
 * then: npm run test:e2e
 *
 * The workbench requires an account: global-setup signs in once (see
 * e2e/auth.js for which account) and every test starts with that session.
 */
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.js',
  // Model loading on a cold backend is slow; individual waits are explicit.
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    storageState: 'e2e/.auth/state.json',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});
