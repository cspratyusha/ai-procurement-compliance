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
export function retrieve(query, { topK = 10, signal } = {}) {
  return request('/retrieve', {
    method: 'POST',
    body: { query, top_k: topK },
    signal,
  });
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

export { BASE_URL };
