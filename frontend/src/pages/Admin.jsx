import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { getHealth, getStats, getCorpusHealth, getAlerts, BASE_URL, ApiError } from '../api/client';
import './query.css';   // .notice — shared with the query screen

/**
 * Engine status — what is actually running and what it is serving.
 *
 * The previous screen was a catalogue-sync console: "22,418 standards
 * indexed", four data-source feeds with sync times, "the QCO / Gazette feed
 * is 3 days stale". None of that exists. There is no sync job, no amendment
 * feed, and no connection to BIS of any kind — the corpus is a file that
 * changes when someone rebuilds it. A stale-feed warning about a feed that
 * was never built is a particularly bad kind of fiction, because it implies
 * the other three are fresh.
 *
 * What an operator can truthfully be told is what this process is running
 * right now: which corpus, whether the learned ranker loaded, how much of
 * the metadata has been researched, and what the live accept/reject signal
 * looks like. All of it is read from the engine at load.
 *
 * The acceptance figures are the one part that carries over in spirit. They
 * used to be three invented bands; they are now counted from the feedback
 * log, and they report `—` rather than 0% until an officer has actually
 * accepted or dismissed something.
 */

export default function Admin() {
  const [state, setState] = useState('loading'); // loading | ready | error
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    Promise.all([
      getHealth({ signal }),
      getStats({ signal }),
      getCorpusHealth({ signal }),
      getAlerts({ signal }),
    ])
      .then(([health, stats, corpus, alerts]) => {
        setData({ health, stats, corpus, alerts });
        setState('ready');
      })
      .catch((err) => {
        if (signal.aborted) return;
        setError(err instanceof ApiError ? err : new ApiError('Could not reach the engine.'));
        setState('error');
      });

    return () => controller.abort();
  }, []);

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="admin-title">Engine status</h1>
          <p className="page-sub">
            What this instance is running and serving, read from the engine at load.
            There is no scheduled sync with BIS — the corpus changes when it is rebuilt.
          </p>
        </div>
      </div>

      {state === 'loading' && (
        <div className="stack stack-3" aria-busy="true">
          <div className="grid grid-4">
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 96 }} />)}
          </div>
          <div className="skeleton" style={{ height: 200 }} />
        </div>
      )}

      {state === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="The engine is not reachable"
            body={`${error?.message ?? 'No response.'} Nothing is shown rather than a stale status.`}
            action={
              <button className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>
                Retry
              </button>
            }
          />
        </div>
      )}

      {state === 'ready' && data && (
        <div className="stack stack-5">
          <section className="grid grid-4">
            <div className="card stack stack-3">
              <span className="xs faint">Engine</span>
              <span className="row" style={{ gap: 'var(--s2)', alignItems: 'center' }}>
                <span
                  className="status-dot"
                  style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: data.health ? 'var(--ok)' : 'var(--crit)',
                    display: 'inline-block',
                  }}
                  aria-hidden="true"
                />
                <span className="small strong">{data.health ? 'Running' : 'Unreachable'}</span>
              </span>
              <span className="xs muted mono">{BASE_URL}</span>
            </div>

            <div className="card stack stack-3">
              <span className="xs faint">Corpus served</span>
              <span className="tabular stat-value">
                {data.corpus.corpus_size.toLocaleString('en-IN')}
              </span>
              <span className="xs muted">{data.corpus.sectors.length} sectors</span>
            </div>

            <div className="card stack stack-3">
              <span className="xs faint">Learned ranker</span>
              <span className="small strong" style={{ paddingTop: 4 }}>
                {data.health?.ltr_model_loaded ? 'Loaded' : 'Not loaded'}
              </span>
              <span className="xs muted">
                {data.health?.ltr_model_loaded
                  ? 'LightGBM model ranking results'
                  : 'Falling back to the heuristic blend'}
              </span>
            </div>

            <div className="card stack stack-3">
              <span className="xs faint">Searches served</span>
              <span className="tabular stat-value">
                {data.stats.queries_total.toLocaleString('en-IN')}
              </span>
              <span className="xs muted">
                {data.stats.median_latency_ms != null
                  ? `${data.stats.median_latency_ms} ms median`
                  : 'No timing recorded yet'}
              </span>
            </div>
          </section>

          {!data.health?.ltr_model_loaded && (
            <div className="notice notice-warn" role="note">
              <Icon name="alert" size={15} />
              <div className="stack stack-2">
                <span className="small strong">The learned ranker did not load</span>
                <span className="xs">
                  Results are being ranked by the heuristic fallback instead. This is
                  usually a corpus/model mismatch: a ranker trained on one corpus scores
                  against ids that another corpus does not have, so the engine declines to
                  use it rather than ranking against the wrong records.
                </span>
              </div>
            </div>
          )}

          <div className="grid split" style={{ '--rail': '1fr' }}>
            <section className="card card-flush">
              <div className="card-head">
                <div className="stack stack-2">
                  <h2 className="card-title">Ranking feedback</h2>
                  <span className="xs faint">Counted from the feedback log</span>
                </div>
              </div>
              <div className="card-body stack stack-4">
                {data.stats.feedback_total === 0 ? (
                  <>
                    <span className="small">No decisions recorded yet</span>
                    <p className="xs muted">
                      An accept is recorded when an officer adds a standard to a
                      specification, and a rejection when they dismiss one on the search
                      screen. Until that happens there is no rate to report — this reads
                      “—” rather than 0%, which would wrongly assert that decisions were
                      made and none were accepts.
                    </p>
                  </>
                ) : (
                  <>
                    {[
                      { label: 'Accepted', value: data.stats.feedback_accepted, tone: 'var(--ok)' },
                      { label: 'Dismissed', value: data.stats.feedback_rejected, tone: 'var(--warn)' },
                      { label: 'Corrected', value: data.stats.feedback_corrected, tone: 'var(--info)' },
                    ].map((row) => {
                      const pct = data.stats.feedback_total
                        ? Math.round((row.value / data.stats.feedback_total) * 100)
                        : 0;
                      return (
                        <div key={row.label} className="stack stack-2">
                          <div className="row-between">
                            <span className="small">{row.label}</span>
                            <span className="small strong tabular">
                              {row.value}
                              <span className="xs faint"> / {data.stats.feedback_total}</span>
                            </span>
                          </div>
                          <div className="meter" role="meter" aria-valuenow={row.value} aria-valuemin={0} aria-valuemax={data.stats.feedback_total} aria-label={row.label}>
                            <div className="meter-fill" style={{ width: `${pct}%`, background: row.tone }} />
                          </div>
                        </div>
                      );
                    })}
                    <hr className="divider" />
                    <div className="row-between">
                      <span className="xs faint">Acceptance rate</span>
                      <span className="xs tabular strong">
                        {data.stats.acceptance_rate != null ? `${data.stats.acceptance_rate}%` : '—'}
                      </span>
                    </div>
                  </>
                )}

                {data.stats.synthetic_interactions > 0 && (
                  <p className="xs faint">
                    {data.stats.synthetic_interactions.toLocaleString('en-IN')} synthetic records
                    bootstrapped the ranker. They are training data, not usage, and are excluded
                    from every figure above.
                  </p>
                )}
              </div>
            </section>

            <section className="card card-flush">
              <div className="card-head">
                <div className="stack stack-2">
                  <h2 className="card-title">Data completeness</h2>
                  <span className="xs faint">Researched, against the corpus served</span>
                </div>
              </div>
              <div className="card-body stack stack-4">
                {[
                  {
                    label: 'Certification confirmed',
                    value: data.corpus.certification_mandatory,
                    hint: 'Against a QCO. Everything else reports not_verified, which is not a clearance.',
                  },
                  {
                    label: 'Amendments researched',
                    value: data.corpus.amendments_researched,
                    hint: `${data.corpus.amendments_total} published amendments recorded across them.`,
                  },
                  {
                    label: 'Marked superseded',
                    value: data.corpus.superseded,
                    hint: `${data.alerts.critical_count} have a replacement this corpus can name.`,
                  },
                ].map((row) => (
                  <div key={row.label} className="stack stack-2">
                    <div className="row-between">
                      <span className="small">{row.label}</span>
                      <span className="small strong tabular">
                        {row.value.toLocaleString('en-IN')}
                        <span className="xs faint"> / {data.corpus.corpus_size.toLocaleString('en-IN')}</span>
                      </span>
                    </div>
                    <span className="xs faint">{row.hint}</span>
                  </div>
                ))}
                <hr className="divider" />
                <Link to="/app/compliance" className="btn btn-secondary btn-sm">
                  Full corpus health <Icon name="chevronRight" size={13} />
                </Link>
              </div>
            </section>
          </div>

          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Coverage gaps</h2>
              <Link to="/app/alerts" className="btn btn-ghost btn-sm">
                Standards hygiene <Icon name="chevronRight" size={13} />
              </Link>
            </div>
            <div className="card-body stack stack-3">
              <div className="row-between">
                <span className="small">Searches the corpus could not answer</span>
                <span className="small tabular strong">{data.stats.no_match_queries}</span>
              </div>
              <span className="xs faint">
                The clearest signal of which sectors to expand next: officers asked for
                these and the engine had nothing to offer.
              </span>
              <hr className="divider" />
              <div className="row-between">
                <span className="small">Never checked for amendments</span>
                <span className="small tabular strong" style={{ color: 'var(--warn)' }}>
                  {data.alerts.coverage.amendments_unchecked.toLocaleString('en-IN')}
                </span>
              </div>
              <span className="xs faint">
                Not a statement that they have none — only that nobody has looked.
              </span>
            </div>
          </section>

          <div className="card stack stack-3">
            <span className="eyebrow">Not built</span>
            <p className="xs muted">
              User accounts and roles, a scheduled BIS catalogue sync, an amendment feed,
              and user-submitted flags on corpus records. The previous version of this
              screen showed all four as though they were running. Operating this engine
              today means rebuilding the corpus and restarting the process.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
