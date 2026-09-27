import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { SIGNED_OUT } from './auth.js';

/**
 * WCAG 2.1 A and AA checks (axe-core) on every screen.
 *
 * Each screen is checked once it has rendered its content, not its loading
 * skeleton, since the skeleton is not what anyone reads.
 */

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function check(page, route, ready) {
  await page.goto(route);
  if (ready) await expect(page.locator(ready).first()).toBeVisible({ timeout: 120_000 });
  await page.waitForLoadState('networkidle');
  const result = await new AxeBuilder({ page })
    .withTags(WCAG)
    // The homepage call-to-action pills are white on #524083 (8:1), drawn
    // above a blurred decorative blob with mix-blend-mode: screen. axe cannot
    // model a blended, blurred backdrop and measures the blend (#987cd3)
    // instead of the pill, a false 3.4:1. Checked on the rendered page.
    .exclude('.cta-glass > span')
    .analyze();
  // For contrast failures, say what was measured, not just where.
  const describe = (n) => {
    const data = n.any?.[0]?.data;
    const colours = data?.fgColor ? ` [${data.fgColor} on ${data.bgColor}, ${data.contrastRatio}:1]` : '';
    return n.target.join(' ') + colours;
  };
  const summary = result.violations.map((v) =>
    `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.slice(0, 3).map(describe).join('\n  ')}`);
  expect(summary, `${route}\n${summary.join('\n')}`).toEqual([]);
}

test.describe('Accessibility, signed out', () => {
  test.use({ storageState: SIGNED_OUT });
  test('homepage', async ({ page }) => check(page, '/', 'h1'));
  test('sign in', async ({ page }) => check(page, '/login', '#email'));
});

test.describe('Accessibility', () => {
  const screens = [
    ['/app', 'h1'],
    ['/app/query', '#spec'],
    ['/app/catalogue', 'h1'],
    [`/app/standard/${encodeURIComponent('IS 694:2010')}`, '[data-demo-target="detail-title"]'],
    ['/app/map', 'h1'],
    ['/app/certification', '.alert-mini'],
    ['/app/boq', 'h1'],
    ['/app/audit', 'h1'],
    ['/app/builder', 'h1'],
    ['/app/tender', 'h1'],
    ['/app/projects', 'h1'],
    ['/app/alerts', 'article.alert-card'],
    ['/app/simulator', 'h1'],
    ['/app/settings', 'h1'],
    ['/app/compliance', 'h1'],
    ['/app/admin', 'h1'],
  ];
  for (const [route, ready] of screens) {
    test(route, async ({ page }) => check(page, route, ready));
  }
});
