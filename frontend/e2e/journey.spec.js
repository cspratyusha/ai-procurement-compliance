import { test, expect } from '@playwright/test';

/**
 * The full user journey, against a live backend.
 *
 * These cover what unit tests cannot: that the frontend and backend agree on
 * the response shape, that CORS permits the call at all, and that the honesty
 * guarantees survive the round trip — an out-of-scope query must not produce a
 * recommendation in the browser, whatever the API returned.
 */

test.describe('Search', () => {
  test('an in-scope query returns recommendations with certification flags', async ({ page }) => {
    await page.goto('/app/query');

    await page.fill('#spec', 'PVC insulated copper cable for indoor panel wiring');
    await page.click('button[type=submit]');

    const cards = page.locator('article.rec');
    await expect(cards.first()).toBeVisible({ timeout: 120_000 });
    expect(await cards.count()).toBeGreaterThan(0);

    await expect(page.locator('h2', { hasText: 'Recommended standards' })).toBeVisible();

    // IS 694 is under a real Quality Control Order; the flag must survive.
    await expect(page.locator('.badge-accent').first()).toBeVisible();
  });

  test('an out-of-scope query refuses to recommend', async ({ page }) => {
    await page.goto('/app/query');

    await page.fill('#spec', 'banana fruit crates for the canteen');
    await page.click('button[type=submit]');

    await expect(page.locator('.notice-crit')).toBeVisible({ timeout: 120_000 });
    await expect(page.locator('h2', { hasText: 'Nearest text matches' })).toBeVisible();

    // The load-bearing assertion: nothing is presented as a recommendation.
    expect(await page.locator('article.rec').count()).toBe(0);
    // The phrase appears in both the banner and the reference-list heading;
    // both are correct, so assert presence rather than uniqueness.
    expect(await page.locator('text=not recommendations').count()).toBeGreaterThan(0);
  });

  test('the submit button is disabled until something is typed', async ({ page }) => {
    await page.goto('/app/query');
    await expect(page.locator('button[type=submit]')).toBeDisabled();
    await page.fill('#spec', 'cement');
    await expect(page.locator('button[type=submit]')).toBeEnabled();
  });
});

test.describe('Multilingual', () => {
  test('a Hindi query is translated and shows what was searched', async ({ page }) => {
    await page.goto('/app/query');

    await expect(page.locator('#q-lang')).toBeVisible();
    await page.locator('.example-chip', { hasText: 'हिन्दी' }).click();

    await expect(page.locator('article.rec').first()).toBeVisible({ timeout: 180_000 });

    // The translation must be shown, not applied silently.
    const panel = page.locator('.notice', { hasText: 'Translated from Hindi' });
    await expect(panel).toBeVisible();
    await expect(panel).toContainText('You typed');
    await expect(panel).toContainText('Searched for');
  });
});

test.describe('Catalogue and detail', () => {
  test('the catalogue lists the corpus grouped by sector', async ({ page }) => {
    await page.goto('/app/catalogue');
    await expect(page.locator('.card-link').first()).toBeVisible({ timeout: 60_000 });
    expect(await page.locator('.card-link').count()).toBeGreaterThan(10);
  });

  test('searching the catalogue narrows it', async ({ page }) => {
    await page.goto('/app/catalogue');
    await expect(page.locator('.card-link').first()).toBeVisible({ timeout: 60_000 });

    const before = await page.locator('.card-link').count();
    await page.fill('#cat-search', 'cement');
    await page.waitForTimeout(500);
    const after = await page.locator('.card-link').count();

    expect(after).toBeLessThan(before);
    expect(after).toBeGreaterThan(0);
  });

  test('a standard detail page shows its allied cluster', async ({ page }) => {
    await page.goto(`/app/standard/${encodeURIComponent('IS 456:2000')}`);

    await expect(page.locator('h1.mono')).toContainText('IS 456:2000', { timeout: 60_000 });
    await expect(page.locator('text=Allied standards')).toBeVisible();
    await expect(page.locator('.ref-row').first()).toBeVisible({ timeout: 30_000 });
  });

  test('a standard outside the corpus says so honestly', async ({ page }) => {
    await page.goto(`/app/standard/${encodeURIComponent('IS 9999:1900')}`);
    await expect(page.locator('text=Not in the current corpus')).toBeVisible({ timeout: 60_000 });
  });
});

test.describe('Tender builder', () => {
  test('typing a spec yields live recommendations and a clause', async ({ page }) => {
    await page.goto('/app/tender');

    // The demo must never imply a live GeM connection.
    await expect(page.locator('text=not connected to GeM')).toBeVisible();

    await page.fill(
      '#t-desc',
      'PVC insulated single core copper conductor cable 1.5 sq mm 1100 V for concealed conduit wiring',
    );

    await expect(page.locator('.rec-mini').first()).toBeVisible({ timeout: 120_000 });

    await page.fill('#t-qty', '500');
    await page.locator('.rec-mini button').first().click();

    const clause = page.locator('blockquote.clause');
    await expect(clause).toBeVisible();
    await expect(clause).toContainText('CONFORMANCE');
    await expect(clause).toContainText('500 metres');
  });
});

test.describe('Honesty guarantees', () => {
  test('fixture screens are labelled, live screens are not', async ({ page }) => {
    for (const route of ['/app', '/app/audit', '/app/compliance']) {
      await page.goto(route);
      await expect(
        page.locator('text=Illustrative screen'),
        `${route} must be labelled as fixture data`,
      ).toBeVisible();
    }

    for (const route of ['/app/query', '/app/catalogue', '/app/tender']) {
      await page.goto(route);
      expect(
        await page.locator('text=Illustrative screen').count(),
        `${route} is live and must not carry the fixture label`,
      ).toBe(0);
    }
  });

  test('no route renders a console error or overflows horizontally', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

    const routes = [
      '/', '/app', '/app/query', '/app/catalogue', '/app/tender',
      '/app/builder', '/app/audit', '/app/settings',
    ];

    for (const route of routes) {
      await page.goto(route, { waitUntil: 'networkidle' });
      const [scrollWidth, clientWidth] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scrollWidth, `${route} scrolls horizontally`).toBeLessThanOrEqual(clientWidth + 1);
    }

    expect(errors).toEqual([]);
  });
});
