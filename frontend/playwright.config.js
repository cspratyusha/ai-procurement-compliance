import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests run against the real stack: a live backend on :8000 and
 * the Vite dev server on :5173. They are deliberately not mocked — the whole
 * point is to catch the integration failures that unit tests cannot, such as
 * missing CORS, a stale server, or a response shape the UI cannot render.
 *
 * Start both servers, then: npm run test:e2e
 */
export default defineConfig({
  testDir: './e2e',
  // Model loading on a cold backend is slow; individual waits are explicit.
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});
