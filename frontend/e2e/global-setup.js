import fs from 'node:fs';
import path from 'node:path';
import { API_URL, BASE_URL, E2E_EMAIL, E2E_PASSWORD, E2E_NAME, STATE_FILE } from './auth.js';

/**
 * Sign in once and hand every test the session.
 *
 * The workbench needs an account, so each test would otherwise begin with a
 * sign-in. Instead this gets a session token from the engine and writes it
 * where the app keeps it (localStorage `bis-session`), as Playwright storage
 * state. Tests about signing in opt out with SIGNED_OUT.
 */
export default async function globalSetup() {
  const post = (route, body) => fetch(`${API_URL}${route}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const status = await (await fetch(`${API_URL}/auth/status`)).json();
  const res = status.setup_required
    ? await post('/auth/setup', {
      org_name: 'End-to-end tests', org_type: 'ministry',
      name: E2E_NAME, email: E2E_EMAIL, password: E2E_PASSWORD,
    })
    : await post('/auth/login', { email: E2E_EMAIL, password: E2E_PASSWORD });

  if (!res.ok) {
    throw new Error(
      `Could not sign in as ${E2E_EMAIL} (${res.status}: ${await res.text()}). `
      + 'Set E2E_EMAIL and E2E_PASSWORD to an administrator account on this installation, '
      + 'or run the engine with ACCOUNTS_DB pointing at an empty database.',
    );
  }
  const { token } = await res.json();

  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify({
    cookies: [],
    origins: [{
      origin: BASE_URL,
      localStorage: [{ name: 'bis-session', value: token }],
    }],
  }));
}
