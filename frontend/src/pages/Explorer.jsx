import { useState, useEffect, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { searchStandards, ApiError } from '../api/client';
import { sectorLabel } from '../data/sectors';

const ALL = '';

/** Standards fetched per page. */
const PAGE_SIZE = 100;

/** Wait this long after typing stops before searching. */
const DEBOUNCE_MS = 300;

/**
 * The standards catalogue, searched on the server.
 *
 * It used to download the whole corpus and filter it in the browser. At
 * 21,848 standards that was about 10 MB and several seconds before the first
 * row appeared, so it now asks `/standards/search` for one page at a time and
 * fetches more on demand. The matching is unchanged: IS number, title, scope
 * and keywords.
 */
export default function Explorer() {
  const [query, setQuery] = useState('');
  const [term, setTerm] = useState('');          // `query`, debounced
  const [sector, setSector] = useState(ALL);
  const [showSuperseded, setShowSuperseded] = useState(true);

  const [page, setPage] = useState(null);        // last response, results accumulated
  const [state, setState] = useState('loading'); // loading | ready | error
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const moreAbort = useRef(null);

  useEffect(() => {
    const timer = setTimeout(() => setTerm(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  // A new search replaces the list. Keeping the previous results on screen
  // while it runs avoids a flash of skeletons on every keystroke.
  useEffect(() => {
    const controller = new AbortController();
    moreAbort.current?.abort();
    searchStandards({
      q: term, category: sector || undefined, includeSuperseded: showSuperseded,
      limit: PAGE_SIZE, offset: 0, signal: controller.signal,
    })
      .then((data) => {
        if (controller.signal.aborted) return;
        setPage(data);
        setState('ready');
      })
      .catch((err) => {
        if (controller.signal.aborted || err.name === 'AbortError') return;
        setError(err instanceof ApiError ? err : new ApiError('Could not load the catalogue.'));
        setState('error');
      });
    return () => controller.abort();
  }, [term, sector, showSuperseded]);

  const loadMore = () => {
    if (!page) return;
    const controller = new AbortController();
    moreAbort.current = controller;
    setLoadingMore(true);
    searchStandards({
      q: term, category: sector || undefined, includeSuperseded: showSuperseded,
      limit: PAGE_SIZE, offset: page.results.length, signal: controller.signal,
    })
      .then((data) => {
        if (controller.signal.aborted) return;
        setPage((prev) => ({ ...data, results: [...prev.results, ...data.results] }));
      })
      .catch(() => { /* the button stays; the officer can try again */ })
      .finally(() => { if (!controller.signal.aborted) setLoadingMore(false); });
  };

  const results = useMemo(() => page?.results ?? [], [page]);

  // Group the loaded rows by sector so the shape of the corpus stays visible.
  const grouped = useMemo(() => {
    const map = new Map();
    for (const s of results) {
      if (!map.has(s.category)) map.set(s.category, []);
      map.get(s.category).push(s);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [results]);

  const total = page?.total ?? 0;
  const remaining = total - results.length;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="catalogue-title">Standards catalogue</h1>
          <p className="page-sub">
            Every standard the engine can search, taken from the published BIS documents.
            A standard that is not listed here cannot be recommended.
          </p>
        </div>
      </div>

      {state === 'loading' && (
        <div className="stack stack-3" aria-busy="true">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 64 }} />)}
        </div>
      )}

      {state === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not load the catalogue"
            body={error?.message ?? 'The standards engine did not respond.'}
            action={
              <button className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>
                Reload
              </button>
            }
          />
        </div>
      )}

      {state === 'ready' && page && (
        <div className="stack stack-5">
          <div className="card stack stack-4">
            <div className="row wrap" style={{ gap: 'var(--s3)' }}>
              <div className="field grow" style={{ minWidth: 240 }}>
                <label className="label sr-only" htmlFor="cat-search">Search the catalogue</label>
                <div style={{ position: 'relative' }}>
                  <span
                    style={{
                      position: 'absolute', left: 14, top: '50%',
                      transform: 'translateY(-50%)', color: 'var(--ink-faint)',
                    }}
                  >
                    <Icon name="search" size={15} />
                  </span>
                  <input
                    id="cat-search"
                    className="input"
                    data-demo-target="catalogue-search"
                    style={{ paddingLeft: 38 }}
                    placeholder="IS number, title or keyword…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
              </div>

              <div className="field" style={{ minWidth: 200 }}>
                <label className="label sr-only" htmlFor="cat-sector">Sector</label>
                <select
                  id="cat-sector"
                  className="select"
                  value={sector}
                  onChange={(e) => setSector(e.target.value)}
                >
                  <option value={ALL}>All sectors</option>
                  {page.sectors.map((s) => (
                    <option key={s.category} value={s.category}>
                      {sectorLabel(s.category)} ({s.count.toLocaleString('en-IN')})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
              <span className="xs faint" aria-live="polite">
                Showing {results.length.toLocaleString('en-IN')} of {total.toLocaleString('en-IN')} matching
                {total !== page.corpus_size ? ` (${page.corpus_size.toLocaleString('en-IN')} in corpus)` : ' standards'}
                {page.superseded_total > 0 && ` · ${page.superseded_total.toLocaleString('en-IN')} superseded`}
              </span>
              <label className="check">
                <input
                  type="checkbox"
                  checked={showSuperseded}
                  onChange={() => setShowSuperseded((v) => !v)}
                />
                <span className="xs">Include superseded editions</span>
              </label>
            </div>
          </div>

          {total === 0 ? (
            <div className="card">
              <EmptyState
                icon="search"
                title="Nothing matches"
                body="No standard in the corpus matches that. Try a broader term, or clear the sector filter."
              />
            </div>
          ) : (
            grouped.map(([group, items]) => (
              <section key={group} className="stack stack-3">
                <div className="row" style={{ gap: 'var(--s2)' }}>
                  <h2 style={{ fontSize: 'var(--fs-md)' }}>{sectorLabel(group)}</h2>
                  <span className="badge badge-neutral">{items.length}</span>
                </div>

                <div className="stack stack-2">
                  {items.map((s) => (
                    <Link
                      key={s.id}
                      to={`/app/standard/${encodeURIComponent(s.number)}`}
                      className="card card-link stack stack-3"
                    >
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <span className="mono small strong">{s.number}</span>
                        {s.status === 'superseded'
                          ? <span className="badge badge-crit"><Icon name="alert" size={11} />Superseded</span>
                          : <span className="badge badge-ok"><Icon name="check" size={11} />Current</span>}
                        {s.version && <span className="badge badge-neutral">{s.version}</span>}
                      </div>
                      <span className="small" style={{ color: 'var(--ink-soft)' }}>{s.title}</span>
                      {s.scope && (
                        <span className="xs muted" style={{ lineHeight: 1.5 }}>
                          {s.scope.length > 180 ? `${s.scope.slice(0, 180)}…` : s.scope}
                        </span>
                      )}
                    </Link>
                  ))}
                </div>
              </section>
            ))
          )}

          {remaining > 0 && (
            <div className="card stack stack-3" style={{ alignItems: 'center' }}>
              <span className="xs muted">
                {remaining.toLocaleString('en-IN')} more standard{remaining === 1 ? '' : 's'} match this search.
              </span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? <><span className="spinner" /> Loading</> : `Show ${Math.min(PAGE_SIZE, remaining)} more`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
