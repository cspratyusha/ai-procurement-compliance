import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { listStandards, ApiError } from '../api/client';

const SECTOR_LABEL = {
  electrical_cables: 'Electrical cables',
  electrical_installations: 'Electrical installations',
  cement_building_materials: 'Cement & building materials',
  steel_pipes_fittings: 'Steel pipes & fittings',
  structural_steel: 'Structural steel',
  plastic_pipes: 'Plastic pipes',
  ppe: 'Personal protective equipment',
  geotechnical: 'Geotechnical & soils',
  water_quality: 'Water & sanitation',
  textiles: 'Textiles & apparel',
  timber_furniture: 'Timber & furniture',
  machinery_equipment: 'Machinery & equipment',
  chemicals: 'Chemicals',
  food_agriculture: 'Food & agriculture',
  packaging: 'Packaging',
  rubber_leather: 'Rubber & leather',
  measurement_testing: 'Measurement & test methods',
};

const sectorLabel = (slug) => SECTOR_LABEL[slug] ?? (slug || '').replace(/_/g, ' ');

const ALL = 'All sectors';

/** How many standards to render before asking the user to expand. */
const PAGE_SIZE = 150;

export default function Explorer() {
  const [standards, setStandards] = useState([]);
  const [state, setState] = useState('loading'); // loading | ready | error
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [sector, setSector] = useState(ALL);
  const [showSuperseded, setShowSuperseded] = useState(true);
  // The corpus is now thousands of standards. Rendering every one of them
  // costs ~1.7 s on first paint and re-runs on every keystroke, so the list
  // is capped and extended on demand.
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  useEffect(() => {
    const controller = new AbortController();
    listStandards({ signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        setStandards(data);
        setState('ready');
      })
      .catch((err) => {
        if (controller.signal.aborted || err.name === 'AbortError') return;
        setError(err instanceof ApiError ? err : new ApiError('Could not load the catalogue.'));
        setState('error');
      });
    return () => controller.abort();
  }, []);

  const sectors = useMemo(
    () => [ALL, ...[...new Set(standards.map((s) => s.category))].sort()],
    [standards],
  );

  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [query, sector, showSuperseded]);

  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    return standards.filter((s) => {
      if (sector !== ALL && s.category !== sector) return false;
      if (!showSuperseded && s.status === 'superseded') return false;
      if (!term) return true;
      return (
        s.number.toLowerCase().includes(term)
        || s.title.toLowerCase().includes(term)
        || (s.scope ?? '').toLowerCase().includes(term)
        || (s.keywords ?? []).some((k) => k.toLowerCase().includes(term))
      );
    });
  }, [standards, query, sector, showSuperseded]);

  // Group by sector so the shape of the corpus is visible at a glance --
  // which is the honest way to show that coverage is partial.
  const shown = useMemo(() => results.slice(0, visibleCount), [results, visibleCount]);

  const grouped = useMemo(() => {
    const map = new Map();
    for (const s of shown) {
      if (!map.has(s.category)) map.set(s.category, []);
      map.get(s.category).push(s);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [shown]);

  const supersededCount = standards.filter((s) => s.status === 'superseded').length;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Standards catalogue</h1>
          <p className="page-sub">
            Everything the engine can currently search. This is a pilot corpus, not the
            full BIS catalogue — if a product category is not listed here, the engine
            cannot recommend a standard for it.
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

      {state === 'ready' && (
        <div className="stack stack-5">
          <div className="card stack stack-4">
            <div className="row wrap" style={{ gap: 'var(--s3)' }}>
              <div className="field grow" style={{ minWidth: 240 }}>
                <label className="label sr-only" htmlFor="cat-search">Search the catalogue</label>
                <div style={{ position: 'relative' }}>
                  <span
                    style={{
                      position: 'absolute', left: 11, top: '50%',
                      transform: 'translateY(-50%)', color: 'var(--ink-faint)',
                    }}
                  >
                    <Icon name="search" size={15} />
                  </span>
                  <input
                    id="cat-search"
                    className="input"
                    style={{ paddingLeft: 34 }}
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
                  {sectors.map((s) => (
                    <option key={s} value={s}>{s === ALL ? ALL : sectorLabel(s)}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
              <span className="xs faint">
                Showing {shown.length} of {results.length} matching
                {results.length !== standards.length ? ` (${standards.length} in corpus)` : ' standards'}
                {supersededCount > 0 && ` · ${supersededCount} superseded`}
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

          {results.length === 0 ? (
            <div className="card">
              <EmptyState
                icon="search"
                title="Nothing matches"
                body="No standard in the pilot corpus matches that. Try a broader term, or clear the sector filter."
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

          {results.length > shown.length && (
            <div className="card stack stack-3" style={{ alignItems: 'center' }}>
              <span className="xs muted">
                {results.length - shown.length} more standard
                {results.length - shown.length === 1 ? '' : 's'} match this search.
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
              >
                Show {Math.min(PAGE_SIZE, results.length - shown.length)} more
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
