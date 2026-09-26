import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { getStats, ApiError } from '../api/client';
import './query.css';   // .notice — shared with the query screen

/**
 * Usage dashboard, counted from the engine's own logs.
 *
 * Every figure on this screen is a count of something that happened: a search
 * the engine served, or a decision an officer recorded. Nothing is projected,
 * estimated, or defaulted to a plausible-looking number.
 *
 * This screen used to render fixtures behind an "Illustrative screen" label —
 * 1,248 queries a month, an 87-gap count, per-department compliance rates.
 * Those figures are gone rather than reproduced, because the data that would
 * back them does not exist: gap counts need the tender auditor, and department
 * rates need user accounts. A tile that cannot be computed is not shown at
 * all, which is the one presentation that cannot mislead.
 *
 * Three states have to stay distinct, and conflating any two of them would
 * reintroduce exactly the dishonesty this screen was rebuilt to remove:
 *
 *   engine unreachable  — we do not know the figures
 *   engine up, no log   — we know, and the answer is genuinely nothing yet
 *   engine up, log      — the counts below
 */

const ACTIONS = [
  { to: '/app/query', icon: 'search', title: 'New specification', body: 'Describe a product and get the applicable standards cluster.' },
  { to: '/app/catalogue', icon: 'graph', title: 'Standards catalogue', body: 'Browse everything the engine can currently search.' },
  { to: '/app/audit', icon: 'audit', title: 'Audit a tender', body: 'Upload a draft and get a severity-tagged gap report.' },
  { to: '/app/explorer', icon: 'sliders', title: 'Standards explorer', body: 'Browse the relationship graph around any standard.' },
];

/** Sector keys that are acronyms, which sentence-casing would mangle. */
const SECTOR_ACRONYMS = { ppe: 'PPE' };

/**
 * Display name for a sector key.
 *
 * The backend normalises and merges sector spellings before counting, so this
 * only has to present them: sentence case, except where the key is an
 * acronym and "Ppe" would be simply wrong.
 */
function sectorLabel(key) {
  return SECTOR_ACRONYMS[key] ?? key.replace(/^./, (c) => c.toUpperCase());
}

/** Relative time, in the coarse units a dashboard actually needs. */
function timeAgo(iso) {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return '';

  const seconds = Math.floor((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'Yesterday';
  return `${days} days ago`;
}

const CONFIDENCE = {
  strong:    { label: 'Match',      cls: 'badge-ok' },
  uncertain: { label: 'Uncertain',  cls: 'badge-warn' },
  none:      { label: 'No match',   cls: 'badge-crit' },
};

/**
 * One counted figure.
 *
 * `value` of null renders as an em dash, never as zero: "no decisions
 * recorded yet" and "0% of decisions were accepts" are different statements,
 * and a dashboard that shows the second when it means the first is lying.
 */
function StatTile({ label, value, suffix = '', hint }) {
  const missing = value === null || value === undefined;
  return (
    <div className="card stack stack-3">
      <span className="xs faint">{label}</span>
      <span
        className="tabular stat-value"
        style={{ color: missing ? 'var(--ink-faint)' : undefined }}
      >
        {missing ? '—' : `${typeof value === 'number' ? value.toLocaleString('en-IN') : value}${suffix}`}
      </span>
      {hint && <span className="xs muted">{missing ? 'Not recorded yet' : hint}</span>}
    </div>
  );
}

export default function Dashboard() {
  const [state, setState] = useState('loading'); // loading | ready | error
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    getStats({ signal: controller.signal })
      .then((data) => {
        setStats(data);
        setState('ready');
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiError ? err : new ApiError('Could not load usage figures.'));
        setState('error');
      });

    return () => controller.abort();
  }, []);

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="dashboard-title">Usage</h1>
          <p className="page-sub">
            Counted from the engine's own query and feedback logs. Every figure here is
            a count of a search that was served or a decision an officer recorded —
            nothing on this screen is projected or estimated.
          </p>
        </div>
        <Link to="/app/query" className="btn btn-primary">
          <Icon name="plus" size={15} />
          New query
        </Link>
      </div>

      {state === 'loading' && (
        <div className="stack stack-3" aria-busy="true">
          <div className="grid grid-4">
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 96 }} />)}
          </div>
          <div className="skeleton" style={{ height: 220 }} />
        </div>
      )}

      {state === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not load usage figures"
            body={
              `${error?.message ?? 'The standards engine did not respond.'} ` +
              'No figures are shown rather than stale or invented ones.'
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
        <div className="stack stack-6">
          {!stats.has_live_data && (
            <div className="notice notice-info" role="note">
              <Icon name="info" size={15} />
              <div className="stack stack-2">
                <span className="small strong">No searches recorded yet</span>
                <span className="xs">
                  The engine is running and its logs are empty, so there is nothing to
                  count. Run a search and this screen fills in.
                </span>
                {stats.synthetic_interactions > 0 && (
                  <span className="xs">
                    {stats.synthetic_interactions.toLocaleString('en-IN')} synthetic records
                    exist from bootstrapping the ranking model. They are training data, not
                    usage, and are deliberately excluded from the figures below.
                  </span>
                )}
              </div>
            </div>
          )}

          <section className="grid grid-4">
            <StatTile
              label="Searches served"
              value={stats.queries_total}
              hint={`${stats.queries_last_7d.toLocaleString('en-IN')} in the last 7 days`}
            />
            <StatTile
              label="Found a match"
              value={stats.match_rate}
              suffix="%"
              hint="Share of searches inside corpus coverage"
            />
            <StatTile
              label="No match in corpus"
              value={stats.no_match_queries}
              hint="Candidate standards gaps"
            />
            <StatTile
              label="Median response"
              value={stats.median_latency_ms}
              suffix=" ms"
              hint="Server-side, excluding network"
            />
          </section>

          <section>
            <h2 className="eyebrow" style={{ marginBottom: 'var(--s4)' }}>Quick actions</h2>
            <div className="grid grid-4">
              {ACTIONS.map((a) => (
                <Link key={a.to} to={a.to} className="card card-link stack stack-3">
                  <span style={{ color: 'var(--ink-soft)' }}><Icon name={a.icon} size={19} /></span>
                  <span className="small strong">{a.title}</span>
                  <span className="xs muted">{a.body}</span>
                </Link>
              ))}
            </div>
          </section>

          {/*
            A narrower rail than the even split the fixture dashboard used.
            Real queries are full sentences — "PVC insulated single core copper
            conductor cable 1.5 sq mm 1100 V for concealed conduit wiring" —
            where the fixtures were short labels, and an even split clipped the
            verdict and time columns out of view.
          */}
          <section className="grid split" style={{ '--rail': '340px' }}>
            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Recent searches</h2>
                <Link to="/app/query" className="btn btn-ghost btn-sm">
                  New query <Icon name="chevronRight" size={13} />
                </Link>
              </div>

              {stats.recent_queries.length === 0 ? (
                <EmptyState
                  icon="search"
                  title="No searches yet"
                  body="Searches run against the engine are listed here as they happen."
                />
              ) : (
                <div className="scroll-x" tabIndex={0} role="region" aria-label="Recent searches">
                  <table className="table table-hover">
                    <caption className="sr-only">Searches the engine has served, most recent first</caption>
                    <thead>
                      <tr>
                        <th scope="col">Query</th>
                        <th scope="col">Top standard</th>
                        <th scope="col">Verdict</th>
                        <th scope="col">When</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.recent_queries.map((q, i) => {
                        const verdict = CONFIDENCE[q.confidence] ?? CONFIDENCE.none;
                        return (
                          <tr key={`${q.timestamp}-${i}`}>
                            {/* Capped rather than min-width: a long query should
                                wrap inside its cell, not widen the table until
                                the columns after it scroll out of sight. */}
                            <td style={{ maxWidth: 320 }}>
                              <span className="small">{q.query}</span>
                            </td>
                            <td>
                              {q.standard
                                ? <span className="mono small strong nowrap">{q.standard}</span>
                                : <span className="xs faint">—</span>}
                            </td>
                            <td><span className={`badge ${verdict.cls}`}>{verdict.label}</span></td>
                            <td className="xs faint nowrap">{timeAgo(q.timestamp)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="stack stack-4">
              <div className="card card-flush">
                <div className="card-head">
                  <h2 className="card-title">Most searched sectors</h2>
                </div>
                {stats.categories.length === 0 ? (
                  <div style={{ padding: 'var(--s5)' }}>
                    <span className="xs muted">
                      Ranked once searches have been served. Taken from the sector of each
                      search's top result.
                    </span>
                  </div>
                ) : (
                  <div className="stack stack-3" style={{ padding: 'var(--s4)' }}>
                    {stats.categories.map((c) => {
                      const share = Math.round((c.queries / stats.categories[0].queries) * 100);
                      return (
                        <div key={c.category} className="stack stack-2">
                          <div className="row-between">
                            <span className="xs">{sectorLabel(c.category)}</span>
                            <span className="xs tabular faint">{c.queries}</span>
                          </div>
                          <div
                            style={{
                              height: 4,
                              borderRadius: 2,
                              background: 'var(--surface-sunk)',
                            }}
                          >
                            <div
                              style={{
                                height: '100%',
                                width: `${share}%`,
                                borderRadius: 2,
                                background: 'var(--accent)',
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="card card-flush">
                <div className="card-head">
                  <h2 className="card-title">Officer decisions</h2>
                </div>
                <div className="stack stack-3" style={{ padding: 'var(--s4)' }}>
                  {stats.feedback_total === 0 ? (
                    <span className="xs muted">
                      Recorded when a standard is added to a spec or dismissed on the
                      search screen. These decisions also retrain the ranking model.
                    </span>
                  ) : (
                    <>
                      <div className="row-between">
                        <span className="xs">Accepted</span>
                        <span className="xs tabular strong">{stats.feedback_accepted}</span>
                      </div>
                      <div className="row-between">
                        <span className="xs">Dismissed</span>
                        <span className="xs tabular strong">{stats.feedback_rejected}</span>
                      </div>
                      <div className="row-between">
                        <span className="xs">Corrected</span>
                        <span className="xs tabular strong">{stats.feedback_corrected}</span>
                      </div>
                      {stats.acceptance_rate !== null && (
                        <div className="row-between" style={{ paddingTop: 'var(--s2)' }}>
                          <span className="xs faint">Acceptance rate</span>
                          <span className="xs tabular strong">{stats.acceptance_rate}%</span>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          </section>

          <p className="xs faint">
            Counted from the engine's append-only logs.
            {stats.synthetic_interactions > 0 && stats.has_live_data && (
              <> {stats.synthetic_interactions.toLocaleString('en-IN')} synthetic
              bootstrap records are excluded from every figure above.</>
            )}{' '}
            Tender gap counts and per-department compliance rates are not shown because
            the tender auditor and user accounts that would produce them are not built.
          </p>
        </div>
      )}
    </div>
  );
}
