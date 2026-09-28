import { test, expect } from '@playwright/test';

/**
 * The embeddable widget a procurement portal drops onto its own page.
 *
 * Run end to end: a real API key is minted the way an administrator would
 * (Settings -> API keys), the plain sample form loads the widget with it, and
 * typing a specification brings back the engine's recommendations, with the
 * certification requirement, and a citation that can be inserted.
 */

const API = process.env.E2E_API_URL || 'http://localhost:8000';

test('the widget recommends standards inside a portal form', async ({ page, request }) => {
  // The session the suite signed in with, read from where the app keeps it.
  await page.goto('/app');
  const token = await page.evaluate(() => localStorage.getItem('bis-session'));
  expect(token).toBeTruthy();

  const created = await request.post(`${API}/keys`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: `widget e2e ${Date.now()}` },
  });
  expect(created.ok()).toBeTruthy();
  const { secret, key } = await created.json();

  try {
    await page.goto(`/widget/demo.html?api=${encodeURIComponent(API)}&key=${encodeURIComponent(secret)}`);
    await page.fill('#item-specification', 'PVC insulated copper cable for indoor wiring, 1100 V');

    const panel = page.locator('.sew');
    await expect(panel).toContainText('IS 694', { timeout: 120_000 });
    await expect(panel).toContainText('ISI mark required');

    // Inserting a citation writes it into the portal's own field.
    await panel.locator('.sew-btn').first().click();
    await expect(page.locator('#item-specification')).toHaveValue(/IS \d+/);
  } finally {
    await request.delete(`${API}/keys/${key.id}`, { headers: { Authorization: `Bearer ${token}` } });
  }
});
