import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { AddButton } from '../components/SpecBasket';
import { useSpec } from '../state/SpecStore';
import {
  retrieve, getHealth, extractAndSearch, listLanguages, ApiError, BASE_URL,
  SUPPORTED_UPLOAD_TYPES,
} from '../api/client';
import {
  CertificationBadge, CertificationBanner, DataWarning,
} from '../components/CertificationBadge';
import { DISMISS_REASONS } from '../data/catalogue';
import './query.css';

const EXAMPLES = [
  'PVC insulated copper cable for indoor panel wiring',
  'OPC 43 grade cement for reinforced concrete',
  'Hot rolled structural steel for building frames',
  'Galvanized steel pipe for water supply',
];

/** Shown alongside the English examples so the feature is discoverable. */
const LANGUAGE_EXAMPLES = [
  { lang: 'hi', label: 'हिन्दी', query: 'घर की वायरिंग के लिए तांबे का तार' },
  { lang: 'ta', label: 'தமிழ்', query: 'குடிநீர் விநியோகத்திற்கான எஃகு குழாய்' },
  { lang: 'bn', label: 'বাংলা', query: 'শ্রমিকদের জন্য নিরাপত্তা হেলমেট' },
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
  const [extraction, setExtraction] = useState(null);
  const [languages, setLanguages] = useState([]);
  const [language, setLanguage] = useState('auto');
  const [explain, setExplain] = useState(false);
  const abortRef = useRef(null);
  const fileRef = useRef(null);

  // Probe the backend once on mount so the UI can say up front whether the
  // engine is reachable, rather than only failing at search time.
  useEffect(() => {
    let alive = true;
    getHealth().then((h) => { if (alive) setHealth(h); });
    listLanguages().then((l) => { if (alive) setLanguages(l); });
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
    setExtraction(null);
    const started = performance.now();

    try {
      const data = await retrieve(query, {
        topK: 10,
        language: language === 'auto' ? null : language,
        explain,
        signal: controller.signal,
      });
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
  }, [text, language, explain]);

  const onFile = useCallback(async (event) => {
    const file = event.target.files?.[0];
    // Let the same file be chosen twice in a row.
    event.target.value = '';
    if (!file) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPhase('running');
    setError(null);
    setResponse(null);
    setExtraction(null);
    setText('');
    const started = performance.now();

    try {
      const data = await extractAndSearch(file, { topK: 10, signal: controller.signal });
      if (controller.signal.aborted) return;
      setExtraction(data);
      setResponse(data.retrieval);
      setElapsed(Math.round(performance.now() - started));
      setPhase('done');
    } catch (err) {
      if (controller.signal.aborted || err.name === 'AbortError') return;
      setError(err instanceof ApiError ? err : new ApiError('Could not read that document.'));
      setPhase('error');
    }
  }, []);

  const applyExample = (ex) => { setText(ex); run(null, ex); };

  const reset = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setText('');
    setResponse(null);
    setError(null);
    setExtraction(null);
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
          {languages.length > 1 && (
            <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
              <div className="row" style={{ gap: 'var(--s3)', alignItems: 'center' }}>
                <label className="label xs" htmlFor="q-lang" style={{ margin: 0 }}>
                  Query language
                </label>
                <select
                  id="q-lang"
                  className="select"
                  style={{ width: 'auto', minWidth: 170 }}
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={phase === 'running'}
                >
                  <option value="auto">Detect automatically</option>
                  {languages.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.native}{l.native !== l.name ? ` (${l.name})` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <span className="xs faint">Translated before searching</span>
              <label className="check" title="Uses a local language model; adds a few seconds">
                <input
                  type="checkbox"
                  checked={explain}
                  onChange={() => setExplain((v) => !v)}
                  disabled={phase === 'running'}
                />
                <span className="xs">Explain why each standard matched</span>
              </label>
            </div>
          )}

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

              <span className="xs faint">Or try another language</span>
              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                {LANGUAGE_EXAMPLES.map((ex) => (
                  <button
                    key={ex.lang}
                    type="button"
                    className="example-chip"
                    onClick={() => { setLanguage(ex.lang); setText(ex.query); run(null, ex.query); }}
                  >
                    <span className="strong">{ex.label}</span>&nbsp; {ex.query}
                  </button>
                ))}
              </div>
            </div>
          )}

          <hr className="divider" />

          <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
            <div className="row wrap" style={{ gap: 'var(--s3)' }}>
              <input
                ref={fileRef}
                type="file"
                accept={SUPPORTED_UPLOAD_TYPES.join(',')}
                onChange={onFile}
                style={{ display: 'none' }}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => fileRef.current?.click()}
                disabled={phase === 'running'}
              >
                <Icon name="upload" size={14} /> Upload tender
              </button>
              <span className="xs faint">
                {health
                  ? `${health.corpus_size} standards${health.ltr_model_loaded ? ' · learned ranker' : ''}`
                  : 'Engine status unknown'}
              </span>
            </div>
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
            {response?.translation && (
              <div className={`notice ${response.translation.translated ? 'notice-info' : 'notice-warn'}`} role="status">
                <Icon name={response.translation.translated ? 'info' : 'alert'} size={15} />
                <div className="stack stack-2">
                  <span className="small strong">
                    {response.translation.translated
                      ? `Translated from ${response.translation.language_name}`
                      : `Could not translate this ${response.translation.language_name} query`}
                  </span>
                  <span className="xs">
                    <strong>You typed:</strong> {response.translation.original}
                  </span>
                  <span className="xs">
                    <strong>Searched for:</strong> {response.translation.translated_text}
                  </span>
                  {response.translation.error
                    ? <span className="xs">{response.translation.error}</span>
                    : (
                      <span className="xs">
                        Machine translation. Check it matches what you meant before relying on the results.
                      </span>
                    )}
                </div>
              </div>
            )}

            {extraction && (
              <div className="card stack stack-3">
                <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
                  <span className="eyebrow">Read from {extraction.filename}</span>
                  <span className="xs faint">
                    {extraction.page_count ? `${extraction.page_count} page${extraction.page_count === 1 ? '' : 's'} · ` : ''}
                    {extraction.char_count.toLocaleString()} characters
                  </span>
                </div>

                {extraction.matched_section ? (
                  <p className="xs muted">
                    Searched the <strong>{extraction.matched_section}</strong> section. Other
                    parts of the document (terms, eligibility, signatures) were ignored.
                  </p>
                ) : (
                  <p className="xs muted">
                    No specification heading was found, so the whole document was scanned
                    for product details.
                  </p>
                )}

                {extraction.warnings?.map((w) => (
                  <div key={w} className="notice notice-warn">
                    <Icon name="alert" size={14} />
                    <span className="xs">{w}</span>
                  </div>
                ))}

                <details>
                  <summary className="xs muted" style={{ cursor: 'pointer' }}>
                    Show the text that was searched
                  </summary>
                  <blockquote className="clause xs" style={{ marginTop: 'var(--s3)', whiteSpace: 'pre-wrap' }}>
                    {extraction.query}
                  </blockquote>
                </details>
              </div>
            )}

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
                        <CertificationBadge certification={r.certification} />
                      </div>

                      <p className="small" style={{ color: 'var(--ink-soft)' }}>{r.title}</p>
                      {r.explanation && (
                        <p className="xs" style={{ color: 'var(--ink-soft)', fontStyle: 'italic' }}>
                          {r.explanation}
                        </p>
                      )}
                      {r.scope && <p className="xs muted">{r.scope}</p>}
                      <DataWarning warning={r.data_warning} />
                      <CertificationBanner certification={r.certification} />

                      <div className="row wrap" style={{ gap: 5 }}>
                        {r.version && <span className="badge badge-neutral">{r.version}</span>}
                        {r.amendment_count > 0 && (
                          <span
                            className="badge badge-warn"
                            title={r.citation}
                          >
                            {r.amendment_count} amendment{r.amendment_count === 1 ? '' : 's'}
                          </span>
                        )}
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
