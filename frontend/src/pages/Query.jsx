import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { AddButton } from '../components/SpecBasket';
import { useSpec } from '../state/SpecStore';
import { useAuth } from '../state/Auth';
import {
  retrieve, explainResults, getHealth, extractAndSearch, listLanguages, sendFeedback, ApiError, BASE_URL,
  SUPPORTED_UPLOAD_TYPES,
} from '../api/client';
import {
  CertificationBadge, CertificationBanner, DataWarning,
} from '../components/CertificationBadge';
import { DISMISS_REASONS } from '../data/ui';
import './query.css';
import { sectorLabel } from '../data/sectors';

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
  { lang: 'gu', label: 'ગુજરાતી', query: 'ઘર માટે તાંબાનો વાયર' },
  { lang: 'kn', label: 'ಕನ್ನಡ', query: 'ಕುಡಿಯುವ ನೀರಿನ ಗುಣಮಟ್ಟ' },
  { lang: 'ml', label: 'മലയാളം', query: 'കുടിവെള്ളത്തിന്റെ ഗുണനിലവാരം' },
];

/** Sector slugs from the backend rendered as readable labels. */

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
  if (ce >= 0) return { label: 'Probable', cls: 'badge-warn', hint: 'Related scope, confirm before citing' };
  return { label: 'Needs review', cls: 'badge-neutral', hint: 'Weak overlap only, verify manually' };
}

/** No explanation answer yet, for any result set. */
const EMPTY_EXPLAINED = { key: '', explanations: {}, failed: false };

const CONFIDENCE_BANNER = {
  uncertain: { cls: 'notice-warn', icon: 'alert', title: 'Low confidence' },
  none: { cls: 'notice-crit', icon: 'alert', title: 'No close match' },
};

/** What each scheme asks of the supplier, as the product note words it. */
const BIS_SCHEME_TEXT = {
  ISI: 'ISI mark',
  CRS: 'BIS registration (CRS)',
  'Scheme X': 'BIS certificate (Scheme X)',
  Hallmark: 'BIS hallmark with HUID',
};

export default function Query() {
  const spec = useSpec();
  const { user } = useAuth();
  const [params] = useSearchParams();
  // `?q=` comes from "recent searches": the query is put back in the box to
  // run again or edit first.
  const [text, setText] = useState(() => params.get('q') ?? '');
  const [phase, setPhase] = useState('idle'); // idle | running | done | error
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(null);
  const [dismissing, setDismissing] = useState(null);
  const [health, setHealth] = useState(undefined); // undefined = checking
  const [extraction, setExtraction] = useState(null);
  const [languages, setLanguages] = useState([]);
  // Starts on the language chosen in Settings.
  const [language, setLanguage] = useState(() => user?.language || 'auto');
  // Explanations are fetched after the results render, so they no longer slow
  // a search down; on by default once the model is available, and the choice
  // is remembered per browser.
  const [explain, setExplain] = useState(() => {
    try { return localStorage.getItem('bis-explain') !== 'off'; } catch { return true; }
  });
  // The last explanation answer, tagged with the result set it belongs to.
  // "Still waiting" is derived by comparing that tag with the current set,
  // rather than kept as its own flag that would have to be reset in sync.
  const [explained, setExplained] = useState(EMPTY_EXPLAINED);
  const explainAbortRef = useRef(null);
  // What the officer asked, shown as their turn in the thread. The input
  // clears on send (the chat convention), so the question lives here.
  const [submitted, setSubmitted] = useState(null); // { kind: 'text', text } | { kind: 'file', name }
  const abortRef = useRef(null);
  const fileRef = useRef(null);
  const inputRef = useRef(null);

  // Grow the composer with its content, up to a cap, like a chat input.
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text, phase]);

  // Probe the backend once on mount so the UI can say up front whether the
  // engine is reachable, rather than only failing at search time.
  useEffect(() => {
    let alive = true;
    getHealth().then((h) => { if (alive) setHealth(h); });
    listLanguages().then((l) => { if (alive) setLanguages(l); });
    return () => { alive = false; };
  }, []);

  useEffect(() => () => { abortRef.current?.abort(); explainAbortRef.current?.abort(); }, []);

  useEffect(() => {
    try { localStorage.setItem('bis-explain', explain ? 'on' : 'off'); } catch { /* storage blocked */ }
  }, [explain]);

  /** Drop explanations from a previous search, and stop any still generating. */
  const clearExplanations = useCallback(() => {
    explainAbortRef.current?.abort();
    setExplained(EMPTY_EXPLAINED);
  }, []);

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
    clearExplanations();
    setSubmitted({ kind: 'text', text: query });
    setText('');
    const started = performance.now();

    try {
      // Never ask /retrieve for explanations: that would hold the results
      // until the model finished. They are requested after rendering instead.
      const data = await retrieve(query, {
        topK: 10,
        language: language === 'auto' ? null : language,
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
  }, [text, language, clearExplanations]);

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
    clearExplanations();
    setText('');
    setSubmitted({ kind: 'file', name: file.name });
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
  }, [clearExplanations]);

  const applyExample = (ex) => { setText(ex); run(null, ex); };

  const reset = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setText('');
    setResponse(null);
    setError(null);
    setExtraction(null);
    clearExplanations();
    setSubmitted(null);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  /** The send button doubles as stop while a search is in flight. */
  const stop = (e) => {
    e.preventDefault();
    abortRef.current?.abort();
    clearExplanations();
    setPhase('idle');
    // Hand the question back so it can be edited rather than retyped.
    if (submitted?.kind === 'text') setText(submitted.text);
    setSubmitted(null);
  };

  // Enter sends, Shift+Enter breaks the line. An IME mid-composition (Hindi,
  // Tamil, Bengali input) uses Enter to commit a character, so never send then.
  const onKeyDown = (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    if (text.trim() && phase !== 'running') run();
  };

  const dismissed = spec.dismissed;
  const allResults = (response?.results ?? []).filter((r) => !dismissed[r.number]);

  /**
   * Report what the officer decided about one result.
   *
   * Adding a standard to the spec is an acceptance and dismissing one is a
   * rejection -- both are already deliberate acts, so no extra thumbs-up
   * widget is needed to capture the signal, and the officer is not asked to
   * rate anything they did not want to rate.
   *
   * The whole candidate list goes with each decision, not just the chosen
   * standard: the ranker learns from what was passed over as much as from
   * what was taken, and the dashboard's acceptance rate is only meaningful
   * against what was actually on offer.
   *
   * Fire-and-forget by construction. `sendFeedback` never throws, and the
   * result is ignored, because the basket change has already happened on
   * screen -- a failed log must not undo it or raise an error over it.
   */
  const recordDecision = useCallback((action, code) => {
    const results = response?.results ?? [];
    if (!results.length) return;

    const target = results.find((r) => r.number === code);
    const candidates = results.map((r, i) => ({
      id: r.id,
      final_score: r.final_score,
      rank: i + 1,
    }));

    sendFeedback({
      query: response.query,
      candidatesShown: candidates,
      chosenId: action === 'accept' ? target?.id : null,
      action,
    });
  }, [response]);
  const confidence = response?.confidence ?? 'strong';

  // How results are split between "recommended" and "for reference only".
  //
  //   none, nothing is a recommendation; everything is a nearest match.
  //   uncertain, the engine is unsure, but the user still needs something to
  //               act on. Show the best candidate above the fold with the
  //               caution banner, and demote the rest. Showing the warning
  //               with an empty list below it is a dead end.
  //   strong, split on the cross-encoder sign: positive is a real match,
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

  const explanationsAvailable = Boolean(health?.explanations_available);

  // The recommendations worth explaining: the top five, never a 'none'
  // verdict (those are nearest text matches, and a fluent reason beside each
  // would read as endorsement). Joined into a string so the effect below
  // re-runs only when the set actually changes.
  const explainKey = phase === 'done' && confidence !== 'none'
    ? recommended.slice(0, 5).map((r) => r.number).join('|')
    : '';

  const explainActive = explain && explanationsAvailable && Boolean(explainKey);

  useEffect(() => {
    if (!explainActive || !response) return undefined;

    const controller = new AbortController();
    explainAbortRef.current?.abort();
    explainAbortRef.current = controller;

    // Explain against what was actually searched: the translation for a
    // non-English query, and a bounded excerpt for an uploaded document.
    const searched = (response.translation?.translated_text || response.query || '').slice(0, 600);

    explainResults(searched, explainKey.split('|'), { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        const got = data.explanations ?? {};
        setExplained({ key: explainKey, explanations: got, failed: !data.available || !Object.keys(got).length });
      })
      .catch((err) => {
        if (controller.signal.aborted || err.name === 'AbortError') return;
        setExplained({ key: explainKey, explanations: {}, failed: true });
      });

    return () => controller.abort();
  }, [explainActive, explainKey, response]);

  // Derived view state for the cards and the note under the heading.
  const current = explained.key === explainKey;
  const explanations = current ? explained.explanations : {};
  const explaining = explainActive && !current ? explainKey.split('|') : [];
  const explainFailed = current && explained.failed;

  const running = phase === 'running';
  const corpusNote = health
    ? `${health.corpus_size.toLocaleString('en-IN')} standards${health.ltr_model_loaded ? ' · learned ranker' : ''}`
    : 'Engine status unknown';

  // One composer, rendered centred before the first search and docked at the
  // foot of the thread after it. Only one instance is ever mounted, so there is
  // exactly one submit button on the page.
  const composer = (
    <form className="composer" onSubmit={run}>
      <label className="sr-only" htmlFor="spec">Product description or specification text</label>
      <textarea
        id="spec"
        ref={inputRef}
        rows={1}
        className="composer-input"
        data-demo-target="query-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={phase === 'idle'
          ? 'Describe a product or paste specification text…'
          : 'Search for another product…'}
        disabled={running}
      />

      <div className="composer-bar">
        <div className="composer-tools">
          <input
            ref={fileRef}
            type="file"
            accept={SUPPORTED_UPLOAD_TYPES.join(',')}
            onChange={onFile}
            style={{ display: 'none' }}
          />
          <button
            type="button"
            className="composer-icon"
            onClick={() => fileRef.current?.click()}
            disabled={running}
            aria-label="Upload a tender document (PDF, Word, Excel or text)"
            title="Upload a tender document"
          >
            <Icon name="paperclip" size={18} />
          </button>

          {languages.length > 1 && (
              <label className="composer-pill pill-select" title="Query language, translated to English before searching">
                <span className="sr-only">Query language</span>
                {/* The select fills the whole pill, so a click anywhere on it
                    opens the list; the icons sit on top and let clicks through. */}
                <select
                  id="q-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={running}
                >
                  <option value="auto">Auto-detect</option>
                  {languages.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.native}{l.native !== l.name ? ` (${l.name})` : ''}
                    </option>
                  ))}
                </select>
                <span className="pill-icon pill-icon-start" aria-hidden="true"><Icon name="globe" size={15} /></span>
                <span className="pill-icon pill-icon-end" aria-hidden="true"><Icon name="chevronDown" size={14} /></span>
              </label>
          )}

          {/* Offered only when the engine reports a local model is ready:
              an option that silently does nothing is worse than no option. */}
          {explanationsAvailable && (
              <label
                className={`composer-pill ${explain ? 'is-on' : ''}`}
                title="A local language model writes one sentence per recommendation, after the results appear"
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={explain}
                  onChange={() => setExplain((v) => !v)}
                />
                <Icon name={explain ? 'check' : 'sparkle'} size={15} />
                <span>Explain matches</span>
              </label>
          )}
        </div>

        <button
          type="submit"
          className={`composer-send ${running ? 'is-running' : ''}`}
          data-demo-target="query-submit"
          aria-label={running ? 'Stop searching' : 'Find standards'}
          title={running ? 'Stop searching' : 'Find standards (Enter)'}
          disabled={!running && !text.trim()}
          onClick={running ? stop : undefined}
        >
          {running
            ? <Icon name="stop" size={14} strokeWidth={3} />
            : <Icon name="arrowUp" size={20} strokeWidth={2.25} />}
        </button>
      </div>
    </form>
  );

  return (
    <div className="container page query-page">
      {/* Engine status, shown only when the backend is unreachable, so the
          user learns about it before typing rather than after searching. */}
      {health === null && (
        <div className="notice notice-warn query-engine-notice" role="status">
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

      {phase === 'idle' ? (
        <div className="prompt-hero">
          <h1 className="sr-only">New query</h1>

          <div className="prompt-greet">
            <p className="greet-title">What are you procuring today?</p>
            <p className="greet-sub">
              Describe it in plain words. The engine finds the applicable Indian Standards
              by meaning, not keywords.
            </p>
          </div>

          {composer}

          <p className="composer-foot">
            {corpusNote} · <kbd>Enter</kbd> to search · <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line
          </p>

          <div className="suggest-grid">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="suggest-card" onClick={() => applyExample(ex)}>
                <span className="suggest-text">{ex}</span>
                <span className="suggest-go" aria-hidden="true"><Icon name="arrowUp" size={14} strokeWidth={2.25} /></span>
              </button>
            ))}
          </div>

          <div className="lang-row">
            <span className="xs faint">Or ask in</span>
            {LANGUAGE_EXAMPLES.map((ex) => (
              <button
                key={ex.lang}
                type="button"
                className="example-chip"
                title={ex.query}
                onClick={() => { setLanguage(ex.lang); setText(ex.query); run(null, ex.query); }}
              >
                {ex.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="thread">
          <div className="thread-head">
            <h1 className="sr-only">New query</h1>
            <span className="xs faint">{corpusNote}</span>
            <button className="btn btn-secondary btn-sm" onClick={reset}>
              <Icon name="plus" size={15} /> New query
            </button>
          </div>

          {submitted && (
            <div className="turn-user fade-in">
              <div className="user-bubble">
                {submitted.kind === 'file'
                  ? <><Icon name="paperclip" size={15} /><span>{submitted.name}</span></>
                  : submitted.text}
              </div>
            </div>
          )}

          <div className="turn-ai">
            <span className={`ai-avatar ${running ? 'is-thinking' : ''}`} aria-hidden="true">
              <Icon name="sparkle" size={18} />
            </span>

            <div className="ai-body stack stack-4">
              {running && (
                <div className="thinking fade-in" aria-live="polite" aria-busy="true">
                  <p className="thinking-text">
                    {submitted?.kind === 'file'
                      ? 'Reading the document and searching…'
                      : health?.corpus_size
                        ? `Searching ${health.corpus_size.toLocaleString('en-IN')} standards…`
                        : 'Searching the standards…'}
                  </p>
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
                      <div className="row" style={{ gap: 'var(--s2)', justifyContent: 'center' }}>
                        {submitted?.kind === 'text' && (
                          <button className="btn btn-primary btn-sm" onClick={() => run(null, submitted.text)}>
                            Try again
                          </button>
                        )}
                        <Link to="/app/catalogue" className="btn btn-secondary btn-sm">Browse catalogue</Link>
                      </div>
                    }
                  />
                </div>
              )}

        {phase === 'done' && response && (
          <div className="stack stack-4 fade-in" data-demo-target="query-results">
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

            {response.expanded_with?.length > 0 && (
              <div className="notice notice-info" role="status" data-demo-target="query-expansion">
                <Icon name="info" size={15} />
                <span className="xs">
                  <strong>Also searched for:</strong> {response.expanded_with.join('; ')}. Standards name
                  products in technical terms, so the standards&rsquo; own words were added to yours.
                </span>
              </div>
            )}

            {response.bis_products?.length > 0 && (() => {
              // Silver hallmarking exists but no order makes it compulsory; a
              // note holding only such schemes must not say "compulsory".
              const compulsory = response.bis_products.some((p) => p.status !== 'voluntary');
              return (
              <div className={`notice ${compulsory ? 'notice-warn' : 'notice-info'}`} role="note" data-demo-target="query-bis-products">
                <Icon name="shield" size={15} />
                <div className="stack stack-2">
                  <span className="small strong">
                    {compulsory
                      ? 'BIS lists this product under compulsory certification'
                      : 'BIS certification is available for this product, but not compulsory'}
                  </span>
                  {response.bis_products.map((p) => (
                    <span key={`${p.is_number}-${p.product}`} className="xs">
                      <strong>{p.product}</strong>:{' '}
                      {p.status === 'deferred' ? 'named in a deferred order, not yet mandatory; ' : ''}
                      {p.status === 'voluntary' ? 'voluntary; ' : ''}
                      {BIS_SCHEME_TEXT[p.scheme] ?? p.scheme} to{' '}
                      {p.in_corpus
                        ? <Link to={`/app/certification/${encodeURIComponent(p.is_number)}`} className="mono">{p.is_number}</Link>
                        : <span className="mono">{p.is_number}</span>}
                      {p.qco ? <>, under the {p.qco_url ? <a href={p.qco_url} target="_blank" rel="noreferrer">{p.qco}</a> : p.qco}</> : ''}
                      {!p.in_corpus ? '. The catalogue does not hold this standard’s text.' : '.'}
                    </span>
                  ))}
                </div>
              </div>
              );
            })()}

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
                      Searched {response.corpus_size.toLocaleString('en-IN')} standards from the
                      published catalogue.
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

            {/* Say what the explanations are, and say when they did not come. */}
            {explain && explanationsAvailable && confidence !== 'none' && (
              explainFailed && !explaining.length ? (
                <p className="xs faint">
                  Explanations could not be generated for this search. The results above are unaffected.
                </p>
              ) : (explaining.length > 0 || Object.keys(explanations).length > 0) && (
                <p className="xs faint">
                  Explanations are written by a local language model from each standard&rsquo;s title and
                  scope. They never change the ranking; check the scope before citing.
                </p>
              )
            )}

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
                      {(explanations[r.number] || r.explanation) ? (
                        <div className="ai-note fade-in">
                          <span className="ai-note-mark" aria-hidden="true"><Icon name="sparkle" size={14} /></span>
                          <div className="stack" style={{ gap: 2, minWidth: 0 }}>
                            <span className="ai-note-label">Why it matches</span>
                            <p className="ai-note-text">{explanations[r.number] || r.explanation}</p>
                          </div>
                        </div>
                      ) : explaining.includes(r.number) && (
                        <div className="ai-note is-loading" aria-live="polite">
                          <span className="ai-note-mark" aria-hidden="true"><Icon name="sparkle" size={14} /></span>
                          <span className="thinking-text ai-note-pending">Writing an explanation…</span>
                        </div>
                      )}
                      {r.scope && <p className="xs muted rec-scope" title={r.scope}>{r.scope}</p>}
                      <DataWarning warning={r.data_warning} />
                      <CertificationBanner certification={r.certification} />

                      <div className="row wrap" style={{ gap: 5 }}>
                        {r.version && <span className="badge badge-neutral">{r.version}</span>}
                        {r.amendment_count > 0 && (
                          <span
                            className="badge badge-warn"
                            title={r.citation}
                          >
                            Amended, No. {r.amendment_count}{r.amendment_count > 1 ? ' latest known' : ''}
                          </span>
                        )}
                        {r.replaced_by ? (
                          <span className="badge badge-warn">Replaced by {r.replaced_by}</span>
                        ) : r.withdrawn && (
                          <span className="badge badge-warn">Withdrawn by BIS, no replacement named</span>
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
                      <AddButton item={item} onAdd={() => recordDecision('accept', r.number)} />
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
                            onClick={() => {
                              spec.dismiss(r.number, reason);
                              recordDecision('reject', r.number);
                              setDismissing(null);
                            }}
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

          <div className="composer-dock">
            {composer}
            <p className="composer-foot">
              Rankings come from the retrieval engine. Check a standard&rsquo;s scope before citing it in a tender.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
