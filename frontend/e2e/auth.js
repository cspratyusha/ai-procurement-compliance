/**
 * The account the end-to-end suite signs in with.
 *
 * Point these at a test account on the installation under test. On a fresh
 * installation (no accounts yet) global-setup creates it as the first
 * administrator, so run the suite against a throwaway accounts database
 * (ACCOUNTS_DB) rather than a deployment's real one.
 */
export const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';
export const E2E_EMAIL = process.env.E2E_EMAIL ?? 'e2e.admin@standeng.test';
export const E2E_PASSWORD = process.env.E2E_PASSWORD ?? 'E2e-Test-Pass-2026';
export const E2E_NAME = 'E2E Administrator';
export const STATE_FILE = 'e2e/.auth/state.json';

/** For tests that must start signed out. */
export const SIGNED_OUT = { cookies: [], origins: [] };
