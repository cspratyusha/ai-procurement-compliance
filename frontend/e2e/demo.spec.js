import { test, expect } from '@playwright/test';
import { E2E_EMAIL, E2E_PASSWORD, SIGNED_OUT } from './auth.js';

/**
 * Demo Mode, driven through the real application.
 *
 * These tests exist because the demo's failure mode is subtle: it can look
 * like it is working while actually clicking nothing, or drift a step ahead of
 * a slow backend and record a cursor pressing a button that is not there yet.
 * So the assertions are about consequences, text really typed, a file really
 * uploaded, results really rendered, not about the overlay's own appearance.
 *
 * Run against a live backend on :8000 and the dev server on :5173.
 */

/**
 * A full pass takes about 225 seconds: two real retrieval calls plus the
 * deliberate reading pauses on twelve screens. The budget clears that with
 * room for a cold model load on a slower machine.
 */
const FULL_RUN = 480_000;

/** The demo dims and locks the app; this is how a test asserts that. */
const demoRunning = (page) =>
  page.locator('html[data-demo="running"]');

/** Start the tour from inside the workbench, via the profile menu. */
async function startInApp(page, route = '/app/query') {
  await page.goto(route);
  await page.click('.profile-trigger');
  await page.click('button:has-text("Start guided demo")');
  await expect(demoRunning(page)).toHaveCount(1);
}

test.describe('Demo Mode, signed out', () => {
  test.use({ storageState: SIGNED_OUT });

  test('the idle application carries no demo layer at all', async ({ page }) => {
    await page.goto('/');

    // Nothing rendered, no attribute on <html>, and the app is interactive.
    await expect(page.locator('.demo-layer')).toHaveCount(0);
    await expect(page.locator('.demo-cursor')).toHaveCount(0);
    await expect(page.locator('html[data-demo]')).toHaveCount(0);

    // The normal path still works: the CTA navigates, nothing intercepts it.
    await page.click('[data-demo-target="landing-cta"]');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator('#email')).toBeEditable();
  });

  test('the tour waits for the viewer to sign in, then carries on', async ({ page }) => {
    await page.goto('/');
    await page.click('button:has-text("Start Demo")');

    // The indicator, the cursor, and the interaction lock.
    await expect(page.locator('.demo-badge')).toContainText('Recording');
    await expect(page.locator('.demo-cursor')).toBeVisible();
    await expect(demoRunning(page)).toHaveCount(1);

    // It reaches the sign-in screen on its own...
    await expect(page).toHaveURL(/\/login$/, { timeout: 30_000 });
    await expect(page.locator('.demo-caption')).toContainText('Sign in with your account', { timeout: 30_000 });

    // ...and never types a password itself: there is no shared demo account.
    await page.waitForTimeout(4000);
    await expect(page.locator('#email')).toHaveValue('');
    await expect(page.locator('#password')).toHaveValue('');

    // The form stays usable under the tour, and signing in resumes it.
    await page.fill('#email', E2E_EMAIL);
    await page.fill('#password', E2E_PASSWORD);
    await page.click('[data-demo-target="sign-in"]');
    await expect(page).toHaveURL(/\/app/, { timeout: 30_000 });
    await expect(page.locator('.demo-caption')).toContainText('workbench', { timeout: 30_000 });
    await expect(demoRunning(page)).toHaveCount(1);
  });
});

test.describe('Demo Mode', () => {
  test('the cursor moves progressively rather than teleporting', async ({ page }) => {
    await startInApp(page);

    const cursor = page.locator('.demo-cursor');
    await expect(cursor).toBeVisible();

    // Sample continuously across the opening acts, which contain several moves.
    // The opening caption holds the cursor still for a few seconds, so a
    // short window at the very start would see one position and prove nothing.
    const seen = new Set();
    const deadline = Date.now() + 30_000;

    while (Date.now() < deadline && seen.size <= 12) {
      const box = await cursor.boundingBox().catch(() => null);
      if (box) seen.add(`${Math.round(box.x)},${Math.round(box.y)}`);
      await page.waitForTimeout(45);
    }

    // A teleporting cursor visits one position per target. A real animation
    // passes through many intermediate ones.
    expect(seen.size).toBeGreaterThan(12);
  });

  test('Pause holds the demo and Resume continues it', async ({ page }) => {
    await startInApp(page);

    // Let it get as far as typing the query, then pause mid-word.
    const input = page.locator('#spec');
    await expect.poll(async () => (await input.inputValue()).length, { timeout: 60_000 }).toBeGreaterThan(3);
    await page.click('.demo-btn:has-text("Pause")');
    await expect(page.locator('.demo-badge')).toContainText('Recording Paused');

    const frozen = await input.inputValue();
    await page.waitForTimeout(1500);
    expect(await input.inputValue()).toBe(frozen);

    // Resume and confirm it moves again.
    await page.click('.demo-btn:has-text("Resume")');
    await expect(page.locator('.demo-badge')).toContainText('Recording');
    await expect.poll(async () => (await input.inputValue()).length, { timeout: 30_000 })
      .toBeGreaterThan(frozen.length);
  });

  test('Stop returns control to the user immediately', async ({ page }) => {
    await page.goto('/');
    await page.click('button:has-text("Start Demo")');
    await expect(demoRunning(page)).toHaveCount(1);

    await page.click('.demo-btn:has-text("Stop")');

    // The lock, the dimming, the cursor and the HUD all go away at once.
    await expect(page.locator('html[data-demo]')).toHaveCount(0);
    await expect(page.locator('.demo-hud')).toHaveCount(0);
    await expect(page.locator('.demo-cursor')).toHaveCount(0);

    // And the app takes real input again.
    await page.goto('/app/query');
    await page.fill('#spec', 'typed by a human');
    await expect(page.locator('#spec')).toHaveValue('typed by a human');
  });

  test('login is skipped when the demo starts from inside the app', async ({ page }) => {
    await page.goto('/app/query');
    // Inside the app the demo starts from the profile menu, not the top bar.
    await page.click('.profile-trigger');
    await page.click('button:has-text("Start guided demo")');

    // It must not bounce out to /login, the skipIf condition should hold.
    await page.waitForTimeout(6000);
    expect(page.url()).not.toContain('/login');
    await expect(demoRunning(page)).toHaveCount(1);
  });

  test('screens change by clicking the sidebar, not by silent route changes', async ({ page }) => {
    // A route that changes with no cursor near it reads as the demo
    // glitching: the viewer cannot tell what caused the page to change. So
    // the later acts must navigate by pressing the nav link.
    await page.goto('/app/alerts');
    await page.click('.profile-trigger');
    await page.click('button:has-text("Start guided demo")');

    // Wait for the spotlight to land on the sidebar, a ring inside the rail's
    // width, which page content never produces.
    const onRail = async () => {
      const box = await page.locator('.demo-spotlight').boundingBox().catch(() => null);
      return Boolean(box && box.x < 250 && box.width < 260);
    };

    const deadline = Date.now() + 90_000;
    let seen = false;
    while (Date.now() < deadline && !seen) {
      seen = await onRail();
      if (!seen) await page.waitForTimeout(120);
    }

    expect(seen, 'the demo never highlighted a sidebar link').toBe(true);
  });

  test('the full sequence runs start to finish with no user interaction', async ({ page }) => {
    test.setTimeout(FULL_RUN);

    // Surface any step failure as a test failure rather than a silent stop.
    const problems = [];
    page.on('console', (m) => {
      if (m.type() === 'error' && m.text().includes('[demo]')) problems.push(m.text());
    });

    // Every screen the demo opens, in order.
    //
    // Polled rather than event-driven: react-router changes the URL through
    // the History API, which raises no navigation event for Playwright to
    // hook. A short interval is enough, the demo dwells on each screen for
    // seconds to let a viewer read it.
    const visited = [];
    let watching = true;
    const watcher = (async () => {
      while (watching) {
        const url = await page.url();
        if (visited[visited.length - 1] !== url) visited.push(url);
        await new Promise((r) => setTimeout(r, 120));
      }
    })();

    await page.goto('/');
    await page.click('button:has-text("Start Demo")');

    // ── Act 3: the engine query, waited for rather than guessed at ──────────
    await expect(page.locator('[data-demo-target="query-results"]'))
      .toBeVisible({ timeout: 150_000 });
    await expect(page.locator('article.rec').first()).toBeVisible();

    // ── Act 5: everyday words, shown for real ──────────────────────────────
    // A second search, "laptop", must show the standards' added term and
    // BIS's listing, not just move on.
    await expect(page.locator('[data-demo-target="query-expansion"]'))
      .toContainText('information technology equipment', { timeout: 200_000 });
    await expect(page.locator('[data-demo-target="query-bis-products"]')).toContainText('Laptop');

    // ── Act 6: the file is visibly chosen, then reaches the real component ─
    await expect(page).toHaveURL(/\/app\/boq/, { timeout: 60_000 });

    // The demo's own chooser appears, names the file, and gets selected,
    // without this the upload would have no visible cause on camera.
    const picker = page.locator('.demo-picker');
    await expect(picker).toBeVisible({ timeout: 90_000 });
    await expect(picker).toContainText('Tender-BOQ-Substation-Works');
    await expect(page.locator('.demo-picker-row.is-selected')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.demo-picker-open.is-ready')).toBeVisible();
    // ...and it is dismissed before the app starts reading the document.
    await expect(picker).toBeHidden({ timeout: 30_000 });

    // The filename the app itself renders, proof the upload was genuine and
    // went through the page's own handler, not a faked state.
    await expect(page.locator('[data-demo-target="boq-results"]'))
      .toBeVisible({ timeout: 180_000 });
    await expect(page.locator('[data-demo-target="boq-results"]'))
      .toContainText('Tender-BOQ-Substation-Works', { timeout: 10_000 });

    // Line items were matched individually, each with its own verdict, the
    // claim the BOQ screen exists to make. Counted rather than asserted
    // on-screen, since the demo scrolls the list while it narrates.
    const items = page.locator('[data-demo-target="boq-results"] article.card');
    expect(await items.count()).toBeGreaterThan(1);
    await expect(
      page.locator('[data-demo-target="boq-results"] .badge-ok').first(),
    ).toHaveCount(1);

    // ── Act 8: the audit act uploads a real document too ───────────────────
    // This act used to only point at the Select file button, leaving the
    // screen's whole purpose undemonstrated. It must now show a second file
    // pick and produce real findings from it.
    await expect(page).toHaveURL(/\/app\/audit/, { timeout: 150_000 });
    await expect(page.locator('.demo-picker'))
      .toContainText('Tender-Spec-Section-7-Standards', { timeout: 90_000 });

    const audit = page.locator('[data-demo-target="audit-results"]');
    await expect(audit).toBeVisible({ timeout: 120_000 });
    await expect(audit).toContainText('standards cited');
    // A finding that names both the fault and the correction.
    await expect(page.locator('[data-demo-target="audit-findings"] article.card').first())
      .toBeVisible();
    // And what the cited standards depend on, which the tender leaves out.
    await expect(page.locator('[data-demo-target="audit-dependencies"]')).toBeVisible({ timeout: 30_000 });

    // ── The rest of the tour, screen by screen ─────────────────────────────
    // Recorded by watching navigation rather than asserting one URL at a
    // time: the demo moves between some screens faster than a sequential
    // toHaveURL can poll, and `/app` is a prefix of every other route, so
    // ordered assertions produce false passes and false failures both.
    await expect(page.locator('.demo-toast.is-done'))
      .toBeVisible({ timeout: 420_000 });

    watching = false;
    await watcher;

    // Every act of the tour must have been visited.
    for (const path of [
      '/app/query',       // search
      '/app/standard/',   // one standard in full
      '/app/map',         // the related cluster
      '/app/certification',
      '/app/boq',         // upload
      '/app/builder',     // assemble and freeze
      '/app/audit',
      '/app/alerts',      // standards hygiene
      '/app/catalogue',   // coverage
      '/app/compliance',  // corpus health
      '/app/admin',       // engine status
    ]) {
      expect(visited.some((u) => u.includes(path)), `never visited ${path}`).toBe(true);
    }

    // ── Completion, and control handed back ────────────────────────────────
    await expect(page.locator('.demo-toast.is-done')).toContainText('Demo complete');

    // The interaction lock is lifted once the demo finishes.
    await expect(page.locator('html[data-demo="running"]')).toHaveCount(0);

    expect(problems, `demo logged errors:\n${problems.join('\n')}`).toEqual([]);
  });

  test('a broken step is skipped and the demo carries on to the end', async ({ page }) => {
    // The contract changed deliberately: a demo is usually being recorded, and
    // losing a four-minute take to one late-rendering element is far worse
    // than one skipped beat nobody watching would notice. So a failed step is
    // logged and stepped over, and the run still reaches 'finish'.
    await page.goto('/app/query');

    const result = await page.evaluate(async () => {
      const { DemoEngine } = await import('/src/demo/demoEngine.js');

      let last = null;
      const engine = new DemoEngine({
        steps: [
          { action: 'caption', act: 'Test', text: 'before' },
          // Not a key in DEMO_TARGETS at all.
          { action: 'click', target: 'no-such-target' },
          { action: 'caption', act: 'Test', text: 'after' },
          { action: 'finish' },
        ],
        navigate: () => {},
        onState: (st) => { last = st; },
      });

      await engine.start();
      return { error: last?.error ?? null, finished: Boolean(last?.finished), skipped: last?.skipped ?? 0 };
    });

    // It did not stop, it reached the end, and it reported the skip.
    expect(result.error).toBeNull();
    expect(result.finished).toBe(true);
    expect(result.skipped).toBeGreaterThan(0);

    // Control is back and the application still takes real input.
    await expect(page.locator('html[data-demo="running"]')).toHaveCount(0);
    await page.fill('#spec', 'still working');
    await expect(page.locator('#spec')).toHaveValue('still working');
  });

  test('a step marked resilient:false still stops the demo', async ({ page }) => {
    // The escape hatch for a step where carrying on would be incoherent.
    await page.goto('/app/query');

    const message = await page.evaluate(async () => {
      const { DemoEngine } = await import('/src/demo/demoEngine.js');
      let last = null;
      const engine = new DemoEngine({
        steps: [
          { action: 'click', target: 'no-such-target', resilient: false },
          { action: 'finish' },
        ],
        navigate: () => {},
        onState: (st) => { last = st; },
      });
      await engine.start();
      return last?.error ?? null;
    });

    expect(message).toBeTruthy();
    expect(message).toContain('no-such-target');
    await expect(page.locator('html[data-demo="running"]')).toHaveCount(0);
  });
});
