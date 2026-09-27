import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { getAlerts, ApiError } from '../api/client';
import './query.css';   // .notice, shared with the query screen
import { sectorLabel as labelFor } from '../data/sectors';

/**
 * Standards-hygiene findings, computed from the corpus.
 *
 * This screen used to render five invented notifications with times like
 * "2 hours ago". What replaced them is narrower and true: every row is a fact
 * the corpus actually supports, a superseded edition, or a standard with
 * published amendments in force, with the replacement named wherever the
 * corpus holds it.
 *
 * The honesty problem here is specific and worth stating, because it is not
 * the same one the dashboard had.
 *
 * **Nothing here is a feed.** No crawler watches BIS for newly published
 * revisions. These are findings about data already in the corpus, so they do
 * not arrive, they are not new, and they have no timestamp. The old screen's
 * relative times were the most convincing thing on it and the least true, so
 * this one shows none at all rather than a defensible-looking substitute.
 *
 * **A short list is not an all-clear.** Amendments are researched for three
 * standards out of forty-five. A standard raising no finding has almost
 * certainly never been checked, which is a completely different statement
 * from "it is clean", so the coverage line is rendered with the list, not
 * tucked into a tooltip.
 */

const KIND = {
  supersession: { icon: 'refresh', label: 'Superseded edition' },
  amendment:    { icon: 'file',    label: 'Amendments in force' },
};

// "critical" is a superseded edition whose replacement the corpus names: do
// not cite it, cite the replacement. It was labelled "Fix before issue" (as in
// before issuing a tender), which read as a typo, and there is nothing to fix
// in the catalogue itself; the card's action line says what to cite instead.
/** Findings rendered per page. */
const PAGE_SIZE = 50;

const SEVERITY = {
  critical: { label: 'Replaced', cls: 'badge-crit' },
  warning:  { label: 'Check before citing', cls: 'badge-warn' },
};

/** Sector keys are stored as `electrical_cables`; show them as words. */
const sectorLabel = (key) => (key ? labelFor(key) : 'Uncategorised');

export default function Alerts() {
  const [state, setState] = useState('loading'); // loading | ready | error
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [severity, setSeverity] = useState('all');
  const [sectors, setSectors] = useState({});   // sector -> included

  useEffect(() => {
    const controller = new AbortController();

    getAlerts({ signal: controller.signal })
      .then((payload) => {
        setData(payload);
        // Every sector present starts included: the default view is the whole
        // scan, and narrowing it is the user's choice.
        const present = [...new Set(payload.findings.map((f) => f.category))];
        setSectors(Object.fromEntries(present.map((c) => [c, true])));
        setState('ready');
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiError ? err : new ApiError('Could not load findings.'));
        setState('error');
      });

    return () => controller.abort();
  }, []);

  const findings = data?.findings ?? [];

  const shown = useMemo(() => findings.filter((f) => {
    if (severity !== 'all' && f.severity !== severity) return false;
    // A sector with no entry yet (first render) counts as included.
    return sectors[f.category] !== false;
  }), [findings, severity, sectors]);

  // The full archive holds ~2,240 replaced editions. Rendering every card at
  // once took seconds and made the page hard to scan, so findings are paged,
  // and the page resets whenever a filter changes the set.
  const [limit, setLimit] = useState(PAGE_SIZE);
  const filterKey = `${severity}|${Object.entries(sectors).filter(([, on]) => !on).map(([c]) => c).join(',')}`;
  const [pagedFor, setPagedFor] = useState(filterKey);
  if (pagedFor !== filterKey) {
    setPagedFor(filterKey);
    setLimit(PAGE_SIZE);
  }
  const visible = shown.slice(0, limit);

  const criticalCount = findings.filter((f) => f.severity === 'critical').length;
  const presentSectors = useMemo(
    () => [...new Set(findings.map((f) => f.category))].sort(),
    [findings],
  );

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="alerts-title">Standards hygiene</h1>
          <p className="page-sub">
            Superseded editions and published amendments found in the corpus the engine
            serves. Each finding is computed from the standards data, not a notification
            feed, and nothing here monitors BIS for newly published revisions.
          </p>
        </div>
      </div>

      {state === 'loading' && (
        <div className="stack stack-3" aria-busy="true">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 96 }} />)}
        </div>
      )}

      {state === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not load findings"
            body={
              `${error?.message ?? 'The standards engine did not respond.'} ` +
              'No findings are shown rather than stale ones.'
            }
            action={
              <button className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>
                Retry
              </button>
            }
          />
        </div>
      )}

      {state === 'ready' && (
        <div className="grid split" style={{ '--rail': '320px' }}>
          <div className="stack stack-4">
            <div className="row wrap" style={{ gap: 'var(--s2)' }}>
              <div className="seg" role="group" aria-label="Filter by severity">
                <button onClick={() => setSeverity('all')} aria-pressed={severity === 'all'}>
                  All ({findings.length})
                </button>
                <button onClick={() => setSeverity('critical')} aria-pressed={severity === 'critical'}>
                  Replaced ({criticalCount.toLocaleString('en-IN')})
                </button>
              </div>
            </div>

            {shown.length === 0 ? (
              <div className="card">
                <EmptyState
                  icon="checkCircle"
                  title={findings.length === 0 ? 'No findings in this corpus' : 'Nothing matches this filter'}
                  body={
                    findings.length === 0
                      ? 'No superseded editions or researched amendments were found. Most standards have not been checked for amendments, so this is not an all-clear.'
                      : 'Widen the severity or sector filter to see the rest of the scan.'
                  }
                />
              </div>
            ) : (
              <div className="stack stack-3">
                {visible.map((f) => {
                  const kind = KIND[f.kind] ?? KIND.supersession;
                  const sev = SEVERITY[f.severity] ?? SEVERITY.warning;
                  return (
                    <article key={`${f.kind}-${f.standard}`} className="card alert-card">
                      <div className="row" style={{ alignItems: 'flex-start', gap: 'var(--s4)' }}>
                        <span className="alert-icon"><Icon name={kind.icon} size={17} /></span>

                        <div className="stack stack-3 grow" style={{ minWidth: 0 }}>
                          <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                            <span className={`badge ${sev.cls}`}>{sev.label}</span>
                            <span className="badge badge-neutral">{kind.label}</span>
                            {f.category && (
                              <span className="badge badge-neutral">{sectorLabel(f.category)}</span>
                            )}
                          </div>

                          <h2 className="small strong">
                            <span className="mono">{f.standard}</span>
                            {f.title ? `, ${f.title}` : ''}
                          </h2>

                          <p className="small muted">{f.detail}</p>

                          <div className="notice notice-info" role="note" style={{ margin: 0 }}>
                            <Icon name="info" size={14} />
                            <span className="xs">{f.action}</span>
                          </div>

                          <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                            <Link
                              to={`/app/standard/${encodeURIComponent(f.standard)}`}
                              className="btn btn-secondary btn-sm"
                            >
                              Open {f.standard} <Icon name="chevronRight" size={13} />
                            </Link>
                            {f.replacement && (
                              <Link
                                to={`/app/standard/${encodeURIComponent(f.replacement)}`}
                                className="btn btn-ghost btn-sm"
                              >
                                Open {f.replacement} <Icon name="chevronRight" size={13} />
                              </Link>
                            )}
                          </div>
                        </div>
                      </div>
                    </article>
                  );
                })}
                {shown.length > visible.length && (
                  <div className="row" style={{ justifyContent: 'center', gap: 'var(--s3)' }}>
                    <span className="xs faint">
                      Showing {visible.length.toLocaleString('en-IN')} of {shown.length.toLocaleString('en-IN')}
                    </span>
                    <button className="btn btn-secondary btn-sm" onClick={() => setLimit((n) => n + PAGE_SIZE)}>
                      Show {Math.min(PAGE_SIZE, shown.length - visible.length)} more
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="stack stack-4">
            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Sectors in this scan</h2>
              </div>
              {presentSectors.length === 0 ? (
                <div className="card-body">
                  <span className="xs muted">No findings to filter.</span>
                </div>
              ) : (
                <div className="stack" style={{ padding: 'var(--s3)' }}>
                  {presentSectors.map((c) => {
                    const count = findings.filter((f) => f.category === c).length;
                    return (
                      <label key={c} className="sub-row">
                        <input
                          type="checkbox"
                          checked={sectors[c] !== false}
                          onChange={() => setSectors((p) => ({ ...p, [c]: p[c] === false }))}
                        />
                        <span className="stack stack-2 grow">
                          <span className="small">{sectorLabel(c)}</span>
                          <span className="xs faint">
                            {count} finding{count === 1 ? '' : 's'}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            {data.coverage && (
              <div className="card stack stack-3">
                <span className="eyebrow">What this scan covered</span>
                <div className="row-between">
                  <span className="xs">Standards scanned</span>
                  <span className="xs tabular strong">{data.coverage.corpus_size}</span>
                </div>
                <div className="row-between">
                  <span className="xs">Marked superseded</span>
                  <span className="xs tabular strong">{data.coverage.superseded_in_corpus}</span>
                </div>
                <div className="row-between">
                  <span className="xs">Amendments researched</span>
                  <span className="xs tabular strong">{data.coverage.amendments_researched}</span>
                </div>
                <div className="row-between">
                  <span className="xs faint">Never checked for amendments</span>
                  <span className="xs tabular strong" style={{ color: 'var(--warn)' }}>
                    {data.coverage.amendments_unchecked}
                  </span>
                </div>
                <hr className="divider" />
                <p className="xs muted">{data.coverage.note}</p>
              </div>
            )}

            <div className="card stack stack-3">
              <span className="eyebrow">Notifications</span>
              <p className="xs muted">
                Email digests and immediate revision alerts are not built. Delivering them
                needs a job that watches BIS for newly published revisions, which does not
                exist, so no channel settings are offered here rather than switches that
                would change nothing.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
