import { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState, CopyButton } from '../components/Primitives';
import { auditDocument, SUPPORTED_UPLOAD_TYPES, MAX_UPLOAD_BYTES, ApiError } from '../api/client';
import './audit.css';
import './query.css';   // .notice, shared with the query screen

/**
 * Audit a tender's citations against the corpus.
 *
 * This screen used to simulate an audit: a 1.8-second timer, then five
 * hardcoded findings about a tender nobody uploaded. It now uploads a real
 * document to POST /audit, which extracts the text, finds every IS number the
 * document cites, and checks each one.
 *
 * The distinction this screen must not blur is what an audit here *is*.
 *
 * It checks the citations the document already makes, superseded editions,
 * missing amendments, undated citations, standards outside the corpus. It
 * does **not** judge whether the tender cites the right standards for the
 * goods it describes; that needs someone to read the specification.
 *
 * So a document with no findings has not passed. It has had its existing
 * citations checked and nothing was wrong with them, which is a much smaller
 * claim, and a document citing nothing at all produces no findings while
 * being the worst case of all. Both states say so explicitly rather than
 * rendering a green all-clear.
 */

const SEVERITY = {
  critical: { label: 'Critical', cls: 'badge-crit', color: 'var(--crit)', blurb: 'Fix before issuing' },
  minor:    { label: 'Minor',    cls: 'badge-warn', color: 'var(--warn)', blurb: 'Should be corrected' },
  info:     { label: 'Advisory', cls: 'badge-info', color: 'var(--info)', blurb: 'Not a defect in the tender' },
};

const KIND_LABEL = {
  superseded: 'Superseded edition',
  amendment:  'Amendments not cited',
  undated:    'No edition year',
  unknown:    'Outside corpus coverage',
};

export default function Audit() {
  const [phase, setPhase] = useState('idle');   // idle | running | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [showText, setShowText] = useState(false);
  const fileRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const onFile = useCallback(async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';   // let the same file be chosen twice
    if (!file) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPhase('running');
    setError(null);
    setResult(null);

    try {
      const data = await auditDocument(file, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setResult(data);
      setPhase('done');
    } catch (err) {
      if (controller.signal.aborted || err.name === 'AbortError') return;
      setError(err instanceof ApiError ? err : new ApiError('Could not audit that document.'));
      setPhase('error');
    }
  }, []);

  const reset = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setResult(null);
    setError(null);
    setFilter('all');
    setShowText(false);
  };

  const findings = result?.findings ?? [];
  const shown = filter === 'all' ? findings : findings.filter((f) => f.severity === filter);
  const counts = {
    critical: findings.filter((f) => f.severity === 'critical').length,
    minor: findings.filter((f) => f.severity === 'minor').length,
    info: findings.filter((f) => f.severity === 'info').length,
  };

  /** Corrected citations, so the officer can paste the fixes back in. */
  const corrections = findings
    .filter((f) => f.replacement || f.kind === 'amendment')
    .map((f) => `${f.cited}  ->  ${f.action}`)
    .join('\n');

  return (
    <div className="container page">
      <input
        ref={fileRef}
        type="file"
        data-demo-target="audit-file"
        accept={SUPPORTED_UPLOAD_TYPES.join(',')}
        onChange={onFile}
        style={{ display: 'none' }}
      />

      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="audit-title">Audit tender</h1>
          <p className="page-sub">
            Upload a draft. Every IS number it cites is checked against the corpus for
            superseded editions, amendments in force, and citations that cannot be
            verified. What the tender <em>should</em> cite is not assessed.
          </p>
        </div>
        {phase === 'done' && (
          <div className="row" style={{ gap: 'var(--s2)' }}>
            <button className="btn btn-secondary" onClick={reset}>New audit</button>
            {corrections && <CopyButton text={corrections} label="Copy corrections" />}
          </div>
        )}
      </div>

      {phase === 'idle' && (
        <div className="card">
          <div className="dropzone" data-demo-target="audit-dropzone">
            <span className="dropzone-icon"><Icon name="upload" size={26} strokeWidth={1.4} /></span>
            <p className="strong">Upload a tender document</p>
            <p className="small muted" style={{ maxWidth: '46ch' }}>
              {SUPPORTED_UPLOAD_TYPES.join(', ')} up to {MAX_UPLOAD_BYTES / 1048576} MB.
              Scanned PDFs are read with OCR where it is available.
            </p>
            <button
              className="btn btn-primary"
              data-demo-target="audit-select"
              onClick={() => fileRef.current?.click()}
              style={{ marginTop: 'var(--s3)' }}
            >
              Select file
            </button>
          </div>
        </div>
      )}

      {phase === 'running' && (
        <div
          className="card stack stack-5 fade-in"
          aria-live="polite"
          data-demo-target="audit-running"
        >
          <div className="row" style={{ gap: 'var(--s3)' }}>
            <Icon name="file" size={18} />
            <span className="small strong grow">Reading the document…</span>
            <span className="spinner" />
          </div>
          <p className="xs muted">
            Extracting text, then checking every IS number it cites. A scanned document
            going through OCR takes longer.
          </p>
        </div>
      )}

      {phase === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not audit that document"
            body={error?.message ?? 'The standards engine did not respond.'}
            action={
              <button className="btn btn-primary btn-sm" onClick={reset}>Try another file</button>
            }
          />
        </div>
      )}

      {phase === 'done' && result && (
        <div className="stack stack-5 fade-in" data-demo-target="audit-results">
          <div className="card stack stack-4" data-demo-target="audit-summary">
            <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
              <div className="row" style={{ gap: 'var(--s3)' }}>
                <Icon name="file" size={18} />
                <div className="stack stack-2">
                  <span className="small strong">{result.filename}</span>
                  <span className="xs faint">
                    {result.page_count ? `${result.page_count} pages · ` : ''}
                    {result.char_count.toLocaleString('en-IN')} characters read
                    {result.method ? ` · ${result.method}` : ''}
                    {' · '}{result.citations_found} standard{result.citations_found === 1 ? '' : 's'} cited
                  </span>
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowText((v) => !v)}>
                {showText ? 'Hide' : 'Show'} extracted text
              </button>
            </div>

            {result.warnings?.length > 0 && (
              <div className="notice notice-warn" role="note">
                <Icon name="alert" size={14} />
                <div className="stack stack-2">
                  {result.warnings.map((w, i) => <span key={i} className="xs">{w}</span>)}
                </div>
              </div>
            )}

            {showText && (
              <pre className="extract-text" tabIndex={0}>{result.text}</pre>
            )}

            <hr className="divider" />

            <div className="audit-summary">
              {[
                { k: 'critical', n: counts.critical, label: 'Critical' },
                { k: 'minor', n: counts.minor, label: 'Minor' },
                { k: 'info', n: counts.info, label: 'Advisory' },
                { k: 'clean', n: result.clean_citations, label: 'No issue found' },
              ].map((c) => (
                <div key={c.k} className="summary-cell">
                  <span
                    className="tabular"
                    style={{
                      fontSize: 'var(--fs-lg)',
                      fontWeight: 600,
                      color: c.k === 'clean' ? 'var(--ok)' : SEVERITY[c.k]?.color,
                    }}
                  >
                    {c.n}
                  </span>
                  <span className="xs faint">{c.label}</span>
                </div>
              ))}
            </div>

            {/*
              The load-bearing caveat. A tender citing nothing produces no
              findings, and that is the worst case rather than a clean bill.
            */}
            <div
              className={`notice ${result.citations_found === 0 ? 'notice-warn' : 'notice-info'}`}
              role="note"
            >
              <Icon name="info" size={14} />
              <span className="xs">
                {result.citations_found === 0
                  ? 'No IS numbers were found in this document, so nothing could be checked. That is not a pass, either the document cites no standards, or the text could not be read.'
                  : result.note}
              </span>
            </div>
          </div>

          {findings.length === 0 ? (
            <div className="card">
              <EmptyState
                icon="checkCircle"
                title={
                  result.citations_found === 0
                    ? 'Nothing to check'
                    : 'No problems with the citations that were checked'
                }
                body={
                  result.citations_found === 0
                    ? 'No IS numbers were detected in the extracted text.'
                    : `All ${result.citations_found} cited standards are current editions with no amendment gaps this corpus knows about. Whether they are the right standards for these goods is not assessed.`
                }
              />
            </div>
          ) : (
            <>
              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                <div className="seg" role="group" aria-label="Filter findings by severity">
                  <button onClick={() => setFilter('all')} aria-pressed={filter === 'all'}>
                    All ({findings.length})
                  </button>
                  {['critical', 'minor', 'info'].map((k) => (
                    counts[k] > 0 && (
                      <button key={k} onClick={() => setFilter(k)} aria-pressed={filter === k}>
                        {SEVERITY[k].label} ({counts[k]})
                      </button>
                    )
                  ))}
                </div>
              </div>

              <div className="stack stack-3" data-demo-target="audit-findings">
                {shown.map((f, i) => {
                  const sev = SEVERITY[f.severity] ?? SEVERITY.info;
                  return (
                    <article key={`${f.cited}-${f.kind}-${i}`} className="card stack stack-3">
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <span className={`badge ${sev.cls}`}>{sev.label}</span>
                        <span className="badge badge-neutral">{KIND_LABEL[f.kind] ?? f.kind}</span>
                        {f.occurrences > 1 && (
                          <span className="badge badge-neutral">
                            cited {f.occurrences} times
                          </span>
                        )}
                      </div>

                      <h2 className="small strong">
                        <span className="mono">{f.cited}</span>
                        {f.title ? `, ${f.title}` : ''}
                      </h2>

                      <p className="small muted">{f.detail}</p>

                      {f.context && (
                        <blockquote className="audit-quote">
                          <span className="xs">{f.context}</span>
                        </blockquote>
                      )}

                      <div className="notice notice-info" role="note" style={{ margin: 0 }}>
                        <Icon name="info" size={14} />
                        <span className="xs">{f.action}</span>
                      </div>

                      {(f.replacement || f.kind !== 'unknown') && (
                        <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                          {f.replacement && (
                            <Link
                              to={`/app/standard/${encodeURIComponent(f.replacement)}`}
                              className="btn btn-secondary btn-sm btn-wrap"
                            >
                              Open {f.replacement} <Icon name="chevronRight" size={13} />
                            </Link>
                          )}
                          {f.kind !== 'unknown' && !f.replacement && (
                            <Link
                              to={`/app/standard/${encodeURIComponent(f.cited)}`}
                              className="btn btn-ghost btn-sm btn-wrap"
                            >
                              Open {f.cited} <Icon name="chevronRight" size={13} />
                            </Link>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </>
          )}

          <DependencyGaps gaps={result.dependency_gaps ?? []} total={result.dependency_gaps_total ?? 0} />
        </div>
      )}
    </div>
  );
}

const GAP_TYPE = {
  normative_reference: 'Required by reference',
  material_spec: 'Material',
  test_method: 'Test method',
  installation: 'Installation',
};

const GROUP_PREVIEW = 4;

/**
 * Standards the cited ones depend on, which the tender does not cite.
 *
 * Read from each cited standard's own text (its references clause, or a
 * "shall be tested as per ..." sentence) or recorded by hand, with the
 * evidence shown, so the officer can judge whether the tender needs it. Kept
 * apart from the findings above: those are defects in what is cited; these
 * are things the cited standards point to.
 */
function DependencyGaps({ gaps, total }) {
  const [open, setOpen] = useState({});
  if (!gaps.length) return null;

  const groups = {};
  gaps.forEach((g) => { (groups[g.required_by[0]] ||= []).push(g); });

  return (
    <section className="card card-flush" data-demo-target="audit-dependencies">
      <div className="card-head">
        <div className="stack stack-2">
          <h2 className="card-title">What the cited standards depend on</h2>
          <span className="xs faint">
            {total} standard{total === 1 ? '' : 's'} the cited ones require, read from their own text, that this tender
            does not cite. Check whether the tender should cite them too.
          </span>
        </div>
      </div>
      <div className="stack" style={{ padding: 'var(--s3)', gap: 'var(--s4)' }}>
        {Object.entries(groups).map(([source, items]) => {
          const expanded = open[source];
          const visible = expanded ? items : items.slice(0, GROUP_PREVIEW);
          return (
            <div key={source} className="stack stack-2">
              <span className="xs strong">
                <span className="mono">{source}</span> refers to
              </span>
              {visible.map((g) => (
                <div key={g.standard} className="dep-row">
                  <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <span className="row wrap" style={{ gap: 6 }}>
                      {g.in_corpus && !g.parts.length ? (
                        <Link to={`/app/standard/${encodeURIComponent(g.standard)}`} className="mono xs strong">{g.standard}</Link>
                      ) : (
                        <span className="mono xs strong">{g.standard}</span>
                      )}
                      {g.parts.length > 0 && <span className="xs">Parts {g.parts.join(', ')}</span>}
                      <span className="badge badge-neutral">{GAP_TYPE[g.type] ?? g.type}</span>
                      {g.required_by.length > 1 && (
                        <span className="badge badge-warn">also needed by {g.required_by.slice(1).join(', ')}</span>
                      )}
                    </span>
                    {g.title && <span className="xs muted">{g.title}</span>}
                    {g.evidence && <span className="xs faint dep-evidence">&ldquo;{g.evidence}&rdquo;</span>}
                  </span>
                </div>
              ))}
              {items.length > GROUP_PREVIEW && (
                <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }}
                  onClick={() => setOpen((o) => ({ ...o, [source]: !expanded }))}>
                  {expanded ? 'Show fewer' : `Show all ${items.length}`}
                </button>
              )}
            </div>
          );
        })}
        {total > gaps.length && (
          <span className="xs muted">Showing the {gaps.length} most-needed of {total}.</span>
        )}
      </div>
    </section>
  );
}
