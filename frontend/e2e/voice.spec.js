import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

/**
 * A spoken query, end to end: Chromium's fake microphone plays a recording
 * (Windows' English voice saying a tender line), the page records it, the
 * engine transcribes it with its local speech model, and the text lands in
 * the query box for the official to check. It is not searched until they
 * press search.
 */

const recording = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'spoken_query_en.wav');

test.use({
  permissions: ['microphone'],
  launchOptions: {
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      `--use-file-for-fake-audio-capture=${recording}`,
    ],
  },
});

test('a spoken query is transcribed into the box, then searched', async ({ page }) => {
  await page.goto('/app/query');

  const mic = page.getByRole('button', { name: /Speak the query/ });
  await expect(mic).toBeVisible({ timeout: 30_000 });
  await mic.click();
  await expect(page.getByRole('status').filter({ hasText: 'Listening' })).toBeVisible();

  // The recording is 5.5 s long; the words at its start must survive, which
  // they did not while the microphone opened before the capture was ready.
  await page.waitForTimeout(7_000);
  await page.getByRole('button', { name: /Stop recording/ }).click();

  // The first transcription loads the speech model (about 20 s from disk).
  await expect(page.locator('#spec')).toHaveValue(/ceiling fan/i, { timeout: 150_000 });
  await expect(page.locator('article.rec')).toHaveCount(0);   // not searched by itself

  await page.click('button[type=submit]');
  await expect(page.locator('article.rec').first()).toContainText('IS 374', { timeout: 120_000 });
});
