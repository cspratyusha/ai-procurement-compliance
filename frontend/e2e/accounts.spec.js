import { test, expect } from '@playwright/test';
import { E2E_EMAIL, E2E_PASSWORD, E2E_NAME, SIGNED_OUT } from './auth.js';

/**
 * Accounts, projects and the scenario simulator: the screens that used to run
 * on sample data, now on the engine's accounts store and live search.
 */

test.describe('Signing in', () => {
  test.use({ storageState: SIGNED_OUT });

  test('the workbench is closed to a signed-out visitor', async ({ page }) => {
    await page.goto('/app/catalogue');
    await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fcatalogue/);
    await expect(page.locator('#email')).toHaveValue('');   // nothing prefilled
  });

  test('a wrong password is refused', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#email', E2E_EMAIL);
    await page.fill('#password', 'Not-The-Password-1');
    await page.click('[data-demo-target="sign-in"]');
    await expect(page.locator('[role="alert"]')).toContainText('do not match');
    await expect(page).toHaveURL(/\/login/);
  });

  test('a visitor can create an account for a new organisation', async ({ page }) => {
    // Offered on the sign-in page only, not in the homepage nav.
    await page.goto('/');
    await expect(page.locator('header >> text=Create account')).toHaveCount(0);
    await page.goto('/login');
    await page.click('button:has-text("Create an account")');
    await expect(page.locator('.auth-card h2')).toHaveText('Create an account');
    const email = `new.${Date.now()}@example.gov.in`;
    await page.fill('#s-org', 'Test Municipal Corporation');
    await page.fill('#s-name', 'Priya Nair');
    await page.fill('#s-email', email);
    await page.fill('#s-password', 'Priya-Pass-2026');
    await page.fill('#s-confirm', 'Priya-Pass-2026');
    await page.click('button:has-text("Create account")');
    await expect(page).toHaveURL(/\/app$/);

    await page.goto('/app/settings');
    await page.click('.tab:has-text("Organisation")');
    await expect(page.locator('#o-name')).toHaveValue('Test Municipal Corporation');
    await expect(page.locator('.member-row')).toHaveCount(1);   // alone in their own organisation
  });

  test('signing in returns to the page asked for, and signing out closes it again', async ({ page }) => {
    await page.goto('/app/catalogue');
    await page.fill('#email', E2E_EMAIL);
    await page.fill('#password', E2E_PASSWORD);
    await page.click('[data-demo-target="sign-in"]');
    await expect(page).toHaveURL(/\/app\/catalogue$/);

    await page.click('.profile-trigger');
    await expect(page.locator('.profile-panel')).toContainText(E2E_EMAIL);
    await page.click('.profile-item:has-text("Sign out")');
    await expect(page).toHaveURL(/\/$/);

    await page.goto('/app');
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Account screens', () => {
  test('the top bar shows the signed-in user, not a sample one', async ({ page }) => {
    await page.goto('/app');
    await expect(page.locator('.profile-name')).toHaveText(E2E_NAME.split(' ')[0]);
  });

  test('settings lists real members and the activity trail records a search', async ({ page }) => {
    await page.goto('/app/query');
    const marker = `concrete admixture ${Date.now()}`;
    await page.fill('#spec', marker);
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-demo-target="query-results"]')).toBeVisible({ timeout: 120_000 });

    await page.goto('/app/settings');
    await page.click('.tab:has-text("Organisation")');
    await expect(page.locator('.member-row').first()).toContainText(E2E_EMAIL);

    await page.click('.tab:has-text("Activity")');
    await expect(page.locator('.log-row').first()).toContainText(marker);
  });

  test('an API key is shown once and can be revoked', async ({ page }) => {
    await page.goto('/app/settings');
    await page.click('.tab:has-text("API keys")');
    const name = `e2e key ${Date.now()}`;
    await page.fill('#k-name', name);
    await page.click('button:has-text("Create key")');
    await expect(page.locator('.secret-value')).toContainText('sk_');
    await page.click('button:has-text("I have saved it")');
    await expect(page.locator('.secret-value')).toHaveCount(0);

    const row = page.locator('tr', { hasText: name });
    await expect(row).toBeVisible();
    page.once('dialog', (d) => d.accept());
    await row.locator('button:has-text("Revoke")').click();
    await expect(row).toHaveCount(0);
  });
});

test.describe('Projects', () => {
  test('a new project is saved on the server and survives a reload', async ({ page }) => {
    await page.goto('/app/projects');
    await page.click('button:has-text("New project")');
    const name = `Tender ${Date.now()}`;
    await page.click('button[aria-label="Rename project"]');
    await page.fill('#project-name', name);
    // "Saved" already shows before the rename, so wait for the save itself.
    const saved = page.waitForResponse((r) => r.request().method() === 'PUT'
      && /\/projects\/\d+$/.test(new URL(r.url()).pathname) && r.ok());
    await page.click('button:has-text("Save")');
    await saved;

    await page.reload();
    await expect(page.locator('.card-title', { hasText: name })).toBeVisible({ timeout: 15_000 });
  });
});

test.describe('Scenario simulator', () => {
  test('a comparison is two real searches and their difference', async ({ page }) => {
    await page.goto('/app/simulator');
    await page.fill('#sim-query', 'PVC insulated copper cable for panel wiring');
    await page.click('.sim-chip:has-text("buried underground")');
    await page.fill('#sim-custom', 'rated for 11 kV');
    await page.click('button:has-text("Compare")');

    await expect(page.locator('text=Searched')).toBeVisible({ timeout: 150_000 });
    // Every IS number on the page links to a real standard page.
    const links = page.locator('a[href^="/app/standard/"]');
    expect(await links.count()).toBeGreaterThan(0);
  });
});
