import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { AddButton } from '../components/SpecBasket';
import { useSpec } from '../state/SpecStore';
import { retrieve, getHealth, ApiError, BASE_URL } from '../api/client';
import { DISMISS_REASONS } from '../data/catalogue';
import './query.css';

const EXAMPLES = [
  'PVC insulated copper cable for indoor panel wiring',
  'OPC 43 grade cement for reinforced concrete',
  'Hot rolled structural steel for building frames',
  'Galvanized steel pipe for water supply',
];

/** Sector slugs from the backend rendered as readable labels. */
const SECTOR_LABEL = {
  electrical_cables: 'Electrical cables',
  electrical_installations: 'Electrical installations',
  cement_building_materials: 'Cement & building materials',
  steel_pipes_fittings: 'Steel pipes & fittings',
  structural_steel: 'Structural steel',
  plastic_pipes: 'Plastic pipes',
  ppe: 'Personal protective equipment',
};

const sectorLabel = (slug) => SECTOR_LABEL[slug] ?? (slug || '').replace(/_/g, ' ');

/**
 * How a result is labelled.
 *
 * `final_score` is rescaled per response by the backend, so it ranks results
 * against each other but says nothing absolute. The cross-encoder logit is
 * comparable across queries, so the band comes from that.
 */
function bandFor(result) {
  const ce = result?.stage_scores?.cross_encoder ?? 0;
  if (ce >= 4) return { label: 'Strong match', cls: 'badge-ok', hint: 'Scope closely matches the query wording' };
  if (ce >= 0) return { label: 'Probable', cls: 'badge-warn', hint: 'Related scope — confirm before citing' };
  return { label: 'Needs review', cls: 'badge-neutral', hint: 'Weak overlap only — verify manually' };
}

const CONFIDENCE_BANNER = {
  uncertain: { cls: 'notice-warn', icon: 'alert', title: 'Low confidence' },
  none: { cls: 'notice-crit', icon: 'alert', title: 'No match in the covered sectors' },
};

export default function Query() {
  const spec = useSpec();
  const [text, setText] = useState('');
  const [phase, setPhase] = useState('idle'); // idle | running | done | error
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(null);
  const [dismissing, setDismissing] = useState(null);
  const [health, setHealth] = useState(undefined); // undefined = checking
  const abortRef = useRef(null);

  // Probe the backend once on mount so the UI can say up front whether the
  // engine is reachable, rather than only failing at search time.
  useEffect(() => {
    let alive = true;
    getHealth().then((h) => { if (alive) setHealth(h); });
    return () => { alive = false; };
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const run = useCallback(async (e, override) => {
    e?.preventDefault();
    const query = (override ?? text).trim();
    if (!query) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPhase('running');
    setError(null);
    setResponse(null);
    const started = performance.now();

    try {
      const data = await retrieve(query, { topK: 10, signal: controller.signal });
      if (controller.signal.aborted) return;
      setResponse(data);
      setElapsed(Math.round(performance.now() - started));
      setPhase('done');
      // A successful call is also a liveness signal.
      setHealth((h) => h ?? { status: 'ok', corpus_size: data.corpus_size, ltr_model_loaded: true });
    } catch (err) {
      if (controller.signal.aborted || err.name === 'AbortError') return;
      setError(err instanceof ApiError ? err : new ApiError('Unexpected error while searching.'));
      setPhase('error');
    }
  }, [text]);

  const applyExample = (ex) => { setText(ex); run(null, ex); };

  const reset = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setText('');
    setResponse(null);
    setError(null);
  };

  const dismissed = spec.dismissed;
  const allResults = (response?.results ?? []).filter((r) => !dismissed[r.number]);
  const confidence = response?.confidence ?? 'strong';

  // How results are split between "recommended" and "for reference only".
  //
  //   none      — nothing is a recommendation; everything is a nearest match.
  //   uncertain — the engine is unsure, but the user still needs something to
  //               act on. Show the best candidate above the fold with the
  //               caution banner, and demote the rest. Showing the warning
  //               with an empty list below it is a dead end.
  //   strong    — split on the cross-encoder sign: positive is a real match,
  //               negative is background noise worth listing but not citing.
  let recommended;
  let reference;
  if (confidence === 'none') {
    recommended = [];
    reference = allResults;
  } else if (confidence === 'uncertain') {
    recommended = allResults.slice(0, 1);
    reference = allResults.slice(1);
  } else {
    recommended = allResults.filter((r) => (r.stage_scores?.cross_encoder ?? 0) >= 0);
    reference = allResults.filter((r) => (r.stage_scores?.cross_encoder ?? 0) < 0);
  }

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">New query</h1>
          <p className="page-sub">
            Describe the product or paste specification text. Results come from the live
            retrieval engine, ranked by meaning rather than keyword match.
          </p>
        </div>
        {phase !== 'idle' && (
          <button className="btn btn-secondary" onClick={reset}>
            <Icon name="plus" size={15} /> New query
          </button>
        )}
      </div>

      <div className="stack stack-5">
        {/* Engine status — shown only when the backend is unreachable, so the
            user learns about it before typing rather than after searching. */}
        {health === null && (
          <div className="notice notice-warn" role="status">
            <Icon name="alert" size={15} />
            <div className="stack stack-2">
              <span className="small strong">The standards engine is not running</span>
              <span className="xs">
                Searches will fail until it is started. Expected at <code className="mono">{BASE_URL}</code>.
                Start it with <code className="mono">uvicorn main:app --port 8000</code> from the
                <code className="mono"> standards-retrieval/</code> directory.
              </span>
            </div>
          </div>
        )}

        <form className="card stack stack-4" onSubmit={run}>
          <div className="field">
            <label className="label sr-only" htmlFor="spec">Product description or specification text</label>
            <textarea
              id="spec"
              className="textarea"
              style={{ minHeight: 88 }}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. PVC insulated copper cable, single core, 1100 V, indoor panel wiring"
              disabled={phase === 'running'}
            />
          </div>

          {phase === 'idle' && (
            <div className="stack stack-3">
              <span className="xs faint">Try an example</span>
              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                {EXAMPLES.map((ex) => (
                  <button key={ex} type="button" className="example-chip" onClick={() => applyExample(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}

          <hr className="divider" />

          <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
            <span className="xs faint">
              {health
                ? `Searching ${health.corpus_size} standards${health.ltr_model_loaded ? ' · learned ranker active' : ''}`
                : 'Engine status unknown'}
            </span>
            <button className="btn btn-primary" type="submit" disabled={!text.trim() || phase === 'running'}>
              {phase === 'running'
                ? <><span className="spinner" /> Searching</>
                : <>Find standards <Icon name="arrowRight" size={15} /></>}
            </button>
          </div>
        </form>

        {phase === 'running' && (
          <div className="card stack stack-3 fade-in" aria-live="polite" aria-busy="true">
            <span className="eyebrow">Searching</span>
            <p className="xs muted">
              Running dense and keyword retrieval, then re-ranking the candidates.
              The first search after starting the engine also loads the models, which takes longer.
            </p>
            <div className="stack stack-3">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 76 }} />)}
            </div>
          </div>
        )}

        {phase === 'error' && error && (
          <div className="card fade-in">
            <EmptyState
              icon="alert"
              title={error.kind === 'offline' ? 'Cannot reach the standards engine' : 'Search failed'}
              body={error.message}
              action={
                <div className="row" style={{ gap: 'var(--s2)' }}>
                  <button className="btn btn-primary btn-sm" onClick={() => run(null, text)}>Try again</button>
                  <Link to="/app/catalogue" className="btn btn-secondary btn-sm">Browse catalogue</Link>
                </div>
              }
            />
          </div>
        )}

        {phase === 'done' && response && (
          <div className="stack stack-4 fade-in">
            {confidence !== 'strong' && (
              <div className={`notice ${CONFIDENCE_BANNER[confidence].cls}`} role="status">
                <Icon name={CONFIDENCE_BANNER[confidence].icon} size={15} />
                <div className="stack stack-2">
                  <span className="small strong">{CONFIDENCE_BANNER[confidence].title}</span>
                  <span className="xs">{response.confidence_reason}</span>
                  {confidence === 'none' && (
                    <span className="xs">
                      The corpus currently covers {response.corpus_size} standards across a few
                      pilot sectors, so most product categories are not represented yet.
                    </span>
                  )}
                </div>
              </div>
            )}

            <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
              <div className="row" style={{ gap: 'var(--s2)' }}>
                <h2 style={{ fontSize: 'var(--fs-md)' }}>
                  {confidence === 'none' ? 'Nearest text matches' : 'Recommended standards'}
                </h2>
                <span className="badge badge-neutral">{recommended.length || allResults.length}</span>
              </div>
              {elapsed != null && (
                <span className="xs faint">
                  {response.corpus_size} standards searched in {elapsed} ms
                </span>
              )}
            </div>

            {recommended.map((r) => {
              const band = bandFor(r);
              const item = {
                code: r.number,
                title: r.title,
                role: 'primary',
                version: r.status === 'superseded' ? 'superseded' : 'latest',
                addedFrom: 'recommendations',
              };

              return (
                <article key={r.id} className="card card-flush rec">
                  <div className="rec-head">
                    <div className="stack stack-3 grow" style={{ minWidth: 0 }}>
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <Link
                          to={`/app/standard/${encodeURIComponent(r.number)}`}
                          className="mono strong build-link"
                          style={{ fontSize: 'var(--fs-md)' }}
                        >
                          {r.number}
                        </Link>
                        <span className={`badge ${band.cls}`} title={band.hint}>{band.label}</span>
                        {r.status === 'superseded'
                          ? <span className="badge badge-crit"><Icon name="alert" size={11} />Superseded</span>
                          : <span className="badge badge-ok"><Icon name="check" size={11} />Current</span>}
                        {r.category && <span className="badge badge-neutral">{sectorLabel(r.category)}</span>}
                      </div>

                      <p className="small" style={{ color: 'var(--ink-soft)' }}>{r.title}</p>
                      {r.scope && <p className="xs muted">{r.scope}</p>}

                      <div className="row wrap" style={{ gap: 5 }}>
                        {r.version && <span className="badge badge-neutral">{r.version}</span>}
                        {r.last_amended && <span className="badge badge-neutral">Amended {r.last_amended}</span>}
                        {r.superseded_by && (
                          <span className="badge badge-warn">Replaced by {r.superseded_by}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="rec-foot">
                    <Link
                      to={`/app/standard/${encodeURIComponent(r.number)}`}
                      className="btn btn-ghost btn-sm"
                    >
                      Open detail <Icon name="chevronRight" size={13} />
                    </Link>
                    <div className="row" style={{ gap: 'var(--s2)' }}>
                      <button className="btn btn-secondary btn-sm" onClick={() => setDismissing(r.number)}>
                        Dismiss
                      </button>
                      <AddButton item={item} />
                    </div>
                  </div>

                  {dismissing === r.number && (
                    <div className="dismiss-panel fade-in">
                      <span className="xs strong">Why are you dismissing this?</span>
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        {DISMISS_REASONS.map((reason) => (
                          <button
                            key={reason}
                            className="example-chip"
                            onClick={() => { spec.dismiss(r.number, reason); setDismissing(null); }}
                          >
                            {reason}
                          </button>
                        ))}
                      </div>
                      <button className="btn btn-ghost btn-sm" onClick={() => setDismissing(null)}>Cancel</button>
                    </div>
                  )}
                </article>
              );
            })}

            {reference.length > 0 && (
              <div className="card stack stack-3">
                <div className="stack stack-2">
                  <span className="eyebrow">
                    {confidence === 'none' ? 'Closest entries in the corpus' : 'Below threshold'}
                  </span>
                  <p className="xs muted">
                    Shown for reference only. These are <strong>not</strong> recommendations.
                  </p>
                </div>
                {reference.map((r) => (
                  <div key={r.id} className="weak-row">
                    <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <div className="row wrap" style={{ gap: 6 }}>
                        <span className="mono small strong">{r.number}</span>
                        <span className="badge badge-neutral">{bandFor(r).label}</span>
                        {r.status === 'superseded' && <span className="badge badge-crit">Superseded</span>}
                      </div>
                      <span className="xs muted">{r.title}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {allResults.length === 0 && (
              <div className="card">
                <EmptyState
                  icon="filter"
                  title="Every result was dismissed"
                  body="Undo a dismissal or start a new query to see results again."
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
