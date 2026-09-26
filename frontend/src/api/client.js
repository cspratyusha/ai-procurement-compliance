/**
 * Client for the standards-retrieval backend.
 *
 * Everything the UI knows about the live service goes through here, so the
 * rest of the app never deals with fetch, timeouts or error shapes.
 *
 * The backend is optional: if it is not running the UI stays usable and says
 * so, rather than showing a dead screen. It must never silently substitute
 * canned results for live ones — a demo that looks identical whether or not
 * the engine is running is worse than one that admits the engine is down.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/** Cold start loads two transformer models; first call is slow. */
const TIMEOUT_MS = 45000;

export class ApiError extends Error {
  constructor(message, { kind = 'unknown', status = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind; // 'offline' | 'timeout' | 'http' | 'unknown'
    this.status = status;
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  // Abort if either the caller or our own timeout fires.
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      try {
        const payload = await res.json();
        if (payload?.detail) detail = payload.detail;
      } catch {
        /* non-JSON error body — keep the status-code message */
      }
      throw new ApiError(detail, { kind: 'http', status: res.status });
    }

    return await res.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;

    if (err.name === 'AbortError') {
      // Caller-initiated aborts are not failures; let them propagate.
      if (signal?.aborted) throw err;
      throw new ApiError(
        'The engine took too long to respond. The first search after starting the backend loads the ranking models and can take up to a minute.',
        { kind: 'timeout' },
      );
    }

    // fetch() rejects with TypeError when it cannot reach the host at all.
    throw new ApiError(
      `Cannot reach the standards engine at ${BASE_URL}. Start the backend, then try again.`,
      { kind: 'offline' },
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Liveness plus what the engine is actually serving.
 * Returns null instead of throwing: callers poll this to show a status dot.
 */
export async function getHealth({ signal } = {}) {
  try {
    return await request('/health', { signal });
  } catch {
    return null;
  }
}

/**
 * Rank standards for a natural-language procurement query.
 *
 * Resolves to `{ query, results, confidence, confidence_reason, corpus_size }`
 * where `confidence` is 'strong' | 'uncertain' | 'none'. A 'none' verdict
 * means the corpus does not cover this query: results are nearest text
 * matches, not recommendations, and the UI must present them that way.
 */
export function retrieve(query, { topK = 10, language, explain = false, signal } = {}) {
  return request('/retrieve', {
    method: 'POST',
    body: { query, top_k: topK, language: language ?? null, explain },
    signal,
  });
}

/**
 * Languages the engine accepts queries in.
 *
 * Served by the backend rather than hardcoded here, so the list cannot drift
 * from what the translator actually supports. Falls back to English-only if
 * the backend is unreachable — the selector should not break the page.
 */
export async function listLanguages({ signal } = {}) {
  try {
    const data = await request('/languages', { signal });
    return data.languages ?? [];
  } catch {
    return [{ code: 'en', name: 'English', native: 'English' }];
  }
}

/** Files the backend can read. Mirrors SUPPORTED_EXTENSIONS in extraction.py. */
export const SUPPORTED_UPLOAD_TYPES = ['.pdf', '.docx', '.txt'];
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/**
 * Upload a tender document, extract its specification, and search on it.
 *
 * Resolves to the extraction result with a nested `retrieval` holding the same
 * shape `retrieve()` returns. The extracted text comes back too, so the user
 * can check what was actually read rather than trusting an invisible step.
 */
export async function extractAndSearch(file, { topK = 10, signal } = {}) {
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new ApiError(
      `That file is ${(file.size / 1048576).toFixed(1)} MB. The limit is ${MAX_UPLOAD_BYTES / 1048576} MB.`,
      { kind: 'http', status: 413 },
    );
  }

  const form = new FormData();
  form.append('file', file);

  // Deliberately not using request(): FormData must not get a JSON
  // Content-Type, and a large upload plus a cold model load needs longer.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    const res = await fetch(`${BASE_URL}/extract?top_k=${topK}`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = `Upload failed (${res.status})`;
      try {
        const payload = await res.json();
        if (payload?.detail) detail = payload.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail, { kind: 'http', status: res.status });
    }

    return await res.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err.name === 'AbortError') {
      if (signal?.aborted) throw err;
      throw new ApiError('Reading the document took too long.', { kind: 'timeout' });
    }
    throw new ApiError(
      `Cannot reach the standards engine at ${BASE_URL}. Start the backend, then try again.`,
      { kind: 'offline' },
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Every standard in the corpus, optionally filtered by sector.
 * The corpus is small enough to fetch whole; the catalogue filters client-side.
 */
export function listStandards({ category, signal } = {}) {
  const query = category ? `?category=${encodeURIComponent(category)}` : '';
  return request(`/standards${query}`, { signal });
}

/**
 * One standard, by internal id (`IS-ELEC-009`) or IS number (`IS 694:2010`).
 * Throws an ApiError with `status === 404` when there is no such standard.
 */
export function getStandard(idOrNumber, { signal } = {}) {
  return request(`/standards/${encodeURIComponent(idOrNumber)}`, { signal });
}

/**
 * The allied-standards cluster around one standard.
 *
 * `researched: false` means no relationships have been recorded for it — not
 * that it has none. Entries flagged `outside_corpus` are real citations to
 * standards the pilot corpus does not hold; they are shown so the cluster is
 * not silently truncated, but they cannot be opened.
 */
export function getRelated(idOrNumber, { signal } = {}) {
  return request(`/standards/${encodeURIComponent(idOrNumber)}/related`, { signal });
}

/**
 * Published amendments for one standard.
 *
 * `checked: false` means the standard has not been researched — which is not
 * a statement that it has no amendments.
 */
export function getAmendments(idOrNumber, { signal } = {}) {
  return request(`/standards/${encodeURIComponent(idOrNumber)}/amendments`, { signal });
}

/**
 * Usage figures for the dashboard, counted from the engine's own logs.
 *
 * Resolves to `{ has_live_data, queries_total, no_match_queries, match_rate,
 * median_latency_ms, categories, recent_queries, feedback_*, acceptance_rate,
 * synthetic_interactions }`.
 *
 * Two fields decide how the dashboard must render:
 *
 * - `has_live_data: false` means the engine has served no searches. The UI
 *   must show an empty state, not tiles reading zero, which look like a
 *   failed fetch.
 * - Null rates (`match_rate`, `acceptance_rate`) mean "not calculable yet",
 *   which is not the same as 0%. Render them as an absence.
 *
 * `synthetic_interactions` counts the seed records that bootstrapped the
 * ranker. They are deliberately excluded from every live figure, and the UI
 * must not add them back in.
 *
 * Throws like every other call here, so the dashboard can distinguish a
 * stopped engine from a genuinely empty log — showing "no queries yet" when
 * the backend is simply down would be a lie of exactly the kind this
 * screen exists to avoid.
 */
export function getStats({ signal } = {}) {
  return request('/stats', { signal });
}

/**
 * Record what an official did with a result set.
 *
 * Feeds both the dashboard's acceptance rate and the LTR retraining loop, so
 * the ranker learns from real decisions rather than only from synthetic seed
 * data.
 *
 * `action` is 'accept' (the official used this standard), 'reject' (they
 * dismissed it) or 'correct' (they replaced it with `correctedId`).
 *
 * Deliberately never throws. Feedback is a side effect of an action the user
 * already completed: adding a standard to the basket must not surface an
 * error, or undo itself, because the logging call failed. Resolves to true
 * when the record was stored and false otherwise.
 */
export async function sendFeedback({ query, candidatesShown, chosenId, action, correctedId } = {}) {
  try {
    await request('/feedback', {
      method: 'POST',
      body: {
        query,
        candidates_shown: candidatesShown,
        chosen_id: chosenId ?? null,
        action,
        corrected_id: correctedId ?? null,
      },
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Standards-hygiene findings: superseded editions and standards with
 * published amendments in force.
 *
 * Resolves to `{ findings, critical_count, coverage }`. A finding is a
 * computed fact about the corpus, not a notification someone sent — so none
 * carries a timestamp, and the UI must not imply one. `severity` is
 * 'critical' when the replacement edition is known and can be named, and
 * 'warning' when the problem is real but this corpus cannot resolve it.
 *
 * `coverage` is not optional decoration. Amendments are researched for a
 * handful of standards, so a short list means "mostly unchecked", not "mostly
 * clean", and the screen has to say which.
 */
export function getAlerts({ category, signal } = {}) {
  const query = category ? `?category=${encodeURIComponent(category)}` : '';
  return request(`/alerts${query}`, { signal });
}

/**
 * How complete the served corpus's own metadata is.
 *
 * Resolves to counts of active/superseded records, confirmed and unverified
 * certification status, amendment research, and the sector spread. Each
 * researched figure is paired with the total it is out of, because the ratio
 * is the honest number.
 */
export function getCorpusHealth({ signal } = {}) {
  return request('/corpus-health', { signal });
}

/**
 * Audit a tender document's citations against the corpus.
 *
 * Resolves to `{ filename, citations_found, findings, critical_count,
 * clean_citations, corpus_size, note, text, warnings }`.
 *
 * Checks only the IS numbers the document already cites — not whether it
 * cites the right ones for its goods. Two consequences the UI must honour:
 * `citations_found: 0` means nothing could be checked and is **not** a pass,
 * and an 'info' finding is a coverage gap rather than a defect in the tender.
 */
export async function auditDocument(file, { signal } = {}) {
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new ApiError(
      `That file is ${(file.size / 1048576).toFixed(1)} MB. The limit is ${MAX_UPLOAD_BYTES / 1048576} MB.`,
      { kind: 'http', status: 413 },
    );
  }

  const form = new FormData();
  form.append('file', file);

  // Not using request(): FormData must not get a JSON Content-Type, and a
  // large scanned PDF going through OCR needs longer than a typed query.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    const res = await fetch(`${BASE_URL}/audit`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = `Audit failed (${res.status})`;
      try {
        const payload = await res.json();
        if (payload?.detail) detail = payload.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail, { kind: 'http', status: res.status });
    }

    return await res.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err.name === 'AbortError') {
      if (signal?.aborted) throw err;
      throw new ApiError('Reading the document took too long.', { kind: 'timeout' });
    }
    throw new ApiError(
      `Cannot reach the standards engine at ${BASE_URL}. Start the backend, then try again.`,
      { kind: 'offline' },
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Split a bill of quantities into line items and search each one.
 *
 * Resolves to `{ filename, is_boq, items, item_count, matched_count, text,
 * warnings, corpus_size }`, where every item carries its own results and its
 * own confidence verdict.
 *
 * `is_boq: false` means the document had no line-item structure. That is not
 * an error and not an empty BOQ — the document is simply not one, and the
 * caller should offer `extractAndSearch` instead of an empty item list.
 *
 * Each item is searched separately on purpose: flattening a BOQ into one
 * query lets the first item's vocabulary dominate, so the cement loses to
 * the cable.
 */
export async function analyseBOQ(file, { topK = 5, signal } = {}) {
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new ApiError(
      `That file is ${(file.size / 1048576).toFixed(1)} MB. The limit is ${MAX_UPLOAD_BYTES / 1048576} MB.`,
      { kind: 'http', status: 413 },
    );
  }

  const form = new FormData();
  form.append('file', file);

  // One retrieval per line item, each loading the ranking models on a cold
  // start, so this needs the most generous timeout of any call here.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180000);
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    const res = await fetch(`${BASE_URL}/boq?top_k=${topK}`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = `Could not read that document (${res.status})`;
      try {
        const payload = await res.json();
        if (payload?.detail) detail = payload.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail, { kind: 'http', status: res.status });
    }

    return await res.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err.name === 'AbortError') {
      if (signal?.aborted) throw err;
      throw new ApiError('Reading the document took too long.', { kind: 'timeout' });
    }
    throw new ApiError(
      `Cannot reach the standards engine at ${BASE_URL}. Start the backend, then try again.`,
      { kind: 'offline' },
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Every standard whose BIS certification status has been researched.
 *
 * Resolves to `{ rules, coverage }`. Each rule carries the Quality Control
 * Order and gazette notification it traces to, so the claim is checkable
 * against the source rather than taken on trust.
 *
 * Only researched standards are listed, and that is the load-bearing detail:
 * the corpus holds thousands whose status nobody has checked. Rendering those
 * as "no scheme applies" would turn an absence of research into a positive
 * clearance — the most dangerous error this data can produce, because it is
 * the one that puts an uncertifiable product into a live tender.
 */
export function getCertificationRules({ signal } = {}) {
  return request('/certification-rules', { signal });
}

export { BASE_URL };
