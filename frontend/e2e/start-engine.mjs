/**
 * Start the standards engine for the end-to-end suite: npm run e2e:engine
 *
 * The suite searches, accepts and dismisses standards, and signs up its own
 * administrator. Against the everyday engine those clicks would land in the
 * real usage logs, which feed the dashboard and the ranker's training data,
 * and the account in the real accounts database. This starts the engine on
 * the full corpus with both in a throwaway folder, and without the background
 * BIS refresh. global-setup.js refuses to run against an engine that writes
 * to the real logs.
 *
 * E2E_ENGINE_PORT (default 8000) runs it beside an engine already on 8000; then
 * start the dev server against it (VITE_API_URL=http://localhost:<port> npm run
 * dev -- --port 5174), list that page in E2E_ALLOWED_ORIGIN, and point the
 * suite at both (E2E_API_URL, E2E_BASE_URL).
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const python = [
  path.join(repo, '.venv', 'Scripts', 'python.exe'),
  path.join(repo, '.venv', 'bin', 'python'),
].find((p) => fs.existsSync(p));
if (!python) {
  console.error('No Python environment at .venv; see the README for setup.');
  process.exit(1);
}

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'standeng-e2e-'));
console.log(`Test engine: usage logs and accounts in ${scratch}`);

const port = process.env.E2E_ENGINE_PORT || '8000';
const engine = spawn(python, [
  '-m', 'uvicorn', 'main:app', '--port', port, '--app-dir', path.join(repo, 'standards-retrieval'),
], {
  cwd: repo,
  stdio: 'inherit',
  env: {
    ...process.env,
    STANDARDS_CORPUS: process.env.STANDARDS_CORPUS || 'full',
    USAGE_LOG_DIR: scratch,
    ACCOUNTS_DB: path.join(scratch, 'accounts.db'),
    BIS_AUTO_REFRESH: '0',
    ...(process.env.E2E_ALLOWED_ORIGIN ? { ALLOWED_ORIGINS: process.env.E2E_ALLOWED_ORIGIN } : {}),
    EXPLANATION_WARMUP: '0',
    SPEECH_WARMUP: '0',
    PYTHONIOENCODING: 'utf-8',
  },
});
engine.on('exit', (code) => process.exit(code ?? 0));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => engine.kill(signal));
