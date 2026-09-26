import { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { CertificationBadge } from '../components/CertificationBadge';
import { useSpec } from '../state/SpecStore';
import { analyseBOQ, SUPPORTED_UPLOAD_TYPES, MAX_UPLOAD_BYTES, ApiError } from '../api/client';
import './query.css';   // .notice — shared with the query screen

/**
 * Upload a bill of quantities and match every line item.
 *
 * The page previously showed a worked example behind a notice saying document
 * parsing was "a planned phase". That had gone stale — extraction was built
 * later, and /extract has served real PDF/DOCX/OCR since.
 *
 * But /extract alone was not enough to make this screen honest. It reduces a
 * whole document to one query, which is right for a tender describing one
 * product and wrong for a BOQ: searching "cable ... cement ... steel" as a
 * single string lets the first item's vocabulary dominate, and the cement
 * quietly loses. Rendering that as per-item matching would have replaced a
 * labelled fixture with an unlabelled inaccuracy.
 *
 * So POST /boq splits the document into line items and runs a full,
 * independent retrieval for each — same ranking, same confidence gate, same
 * supersession rules as a typed query.
 *
 * Two states this screen must keep distinct:
 *
 *   is_boq: false     the document has no line-item structure. Not an empty
 *                     BOQ — not a BOQ. The user is pointed at the search
 *                     screen rather than shown an empty table.
 *   confidence: none  this item is outside corpus coverage. Its results are
 *                     nearest text matches, never recommendations, and cannot
 *                     be accepted into a spec.
 */

const CONFIDENCE = {
  strong:    { label: 'Match',     cls: 'badge-ok' },
  uncertain: { label: 'Uncertain', cls: 'badge-warn' },
  none:      { label: 'No match',  cls: 'badge-crit' },
};

export default function BOQ() {
  const spec = useSpec();
  const [phase, setPhase] = useState('idle');   // idle | running | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);
  const [accepted, setAccepted] = useState({});
  const fileRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const onFile = useCallback(async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPhase('running');
    setError(null);
    setResult(null);
    setAccepted({});

    try {
      const data = await analyseBOQ(file, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setResult(data);
      setOpen(data.items?.[0]?.sr ?? null);
      setPhase('done');
    } catch (err) {
      if (controller.signal.aborted || err.name === 'AbortError') return;
      setError(err instanceof ApiError ? err : new ApiError('Could not read that document.'));
      setPhase('error');
    }
  }, []);

  const reset = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setResult(null);
    setError(null);
    setAccepted({});
  };

  /** Add an item's recommended standards to the spec basket. */
  const accept = useCallback((item) => {
    // Only the standards the engine actually recommends. On an out-of-scope
    // item there are none, and the button is not offered.
    const recommended = item.results.filter(
      (r) => (r.stage_scores?.cross_encoder ?? 0) >= 0,
    );
    const items = (recommended.length ? recommended : item.results.slice(0, 1)).map((r) => ({
      code: r.number,
      title: r.title,
      role: 'primary',
      version: r.status === 'superseded' ? 'superseded' : 'latest',
      addedFrom: `BOQ item ${item.sr}`,
    }));
    if (items.length) spec.addMany(items);
    setAccepted((p) => ({ ...p, [item.sr]: true }));

    const next = result?.items.find((i) => i.sr !== item.sr && !accepted[i.sr]);
    setOpen(next?.sr ?? null);
  }, [spec, result, accepted]);

  const items = result?.items ?? [];
  const acceptedCount = Object.values(accepted).filter(Boolean).length;

  return (
    <div className="container page">
      <input
        ref={fileRef}
        type="file"
        data-demo-target="boq-file"
        accept={SUPPORTED_UPLOAD_TYPES.join(',')}
        onChange={onFile}
        style={{ display: 'none' }}
      />

      <div className="page-head">
        <div>
          <h1 className="page-title">Upload tender or BOQ</h1>
          <p className="page-sub">
            Each line item is detected and searched separately, so one item's wording
            cannot crowd out another's. Accepted standards collect in the spec basket.
          </p>
        </div>
        {phase === 'done' && (
          <div className="row" style={{ gap: 'var(--s2)' }}>
            <button className="btn btn-secondary" onClick={reset}>New upload</button>
            {acceptedCount > 0 && (
              <Link to="/app/builder" className="btn btn-primary">
                Open spec builder <Icon name="chevronRight" size={14} />
              </Link>
            )}
          </div>
        )}
      </div>

      {phase === 'idle' && (
        <div className="card">
          <div className="dropzone" data-demo-target="boq-dropzone">
            <span className="dropzone-icon"><Icon name="upload" size={26} strokeWidth={1.4} /></span>
            <p className="strong">Upload a tender or bill of quantities</p>
            <p className="small muted" style={{ maxWidth: '48ch' }}>
              {SUPPORTED_UPLOAD_TYPES.join(', ')} up to {MAX_UPLOAD_BYTES / 1048576} MB.
              Line items are recognised by how the document numbers them —
              “Item 3:”, “3.”, or a bullet.
            </p>
            <button
              className="btn btn-primary"
              data-demo-target="boq-select"
              onClick={() => fileRef.current?.click()}
              style={{ marginTop: 'var(--s3)' }}
            >
              Select file
            </button>
          </div>
        </div>
      )}

      {phase === 'running' && (
        <div className="card stack stack-5 fade-in" aria-live="polite" data-demo-target="boq-running">
          <div className="row" style={{ gap: 'var(--s3)' }}>
            <Icon name="file" size={18} />
            <span className="small strong grow">Reading and matching each line item…</span>
            <span className="spinner" />
          </div>
          <p className="xs muted">
            One search per line item, so a long BOQ takes proportionally longer.
          </p>
        </div>
      )}

      {phase === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not read that document"
            body={error?.message ?? 'The standards engine did not respond.'}
            action={<button className="btn btn-primary btn-sm" onClick={reset}>Try another file</button>}
          />
        </div>
      )}

      {phase === 'done' && result && !result.is_boq && (
        <div className="stack stack-4 fade-in">
          <div className="notice notice-warn" role="note">
            <Icon name="alert" size={15} />
            <div className="stack stack-2">
              <span className="small strong">No line items found in {result.filename}</span>
              <span className="xs">
                Line items are recognised by document numbering — “Item 3:”, “3.”, or a
                bullet. This document has none, so it may be a tender describing a single
                product rather than a bill of quantities.
              </span>
            </div>
          </div>
          <div className="card">
            <EmptyState
              icon="search"
              title="Search it as a single specification instead"
              body="The search screen reads the same file formats and matches the document as one specification."
              action={<Link to="/app/query" className="btn btn-primary btn-sm">Go to search</Link>}
            />
          </div>
        </div>
      )}

      {phase === 'done' && result?.is_boq && (
        <div className="stack stack-5 fade-in" data-demo-target="boq-results">
          <div className="card stack stack-4" data-demo-target="boq-summary">
            <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
              <div className="row" style={{ gap: 'var(--s3)' }}>
                <Icon name="file" size={18} />
                <div className="stack stack-2">
                  <span className="small strong">{result.filename}</span>
                  <span className="xs faint">
                    {result.page_count ? `${result.page_count} pages · ` : ''}
                    {result.item_count} line item{result.item_count === 1 ? '' : 's'}
                    {' · '}{result.matched_count} matched against {result.corpus_size} standards
                  </span>
                </div>
              </div>
              <span className="xs faint">
                {acceptedCount} of {result.item_count} accepted
              </span>
            </div>

            {result.warnings?.length > 0 && (
              <div className="notice notice-warn" role="note">
                <Icon name="alert" size={14} />
                <div className="stack stack-2">
                  {result.warnings.map((w, i) => <span key={i} className="xs">{w}</span>)}
                </div>
              </div>
            )}

            {result.matched_count < result.item_count && (
              <div className="notice notice-info" role="note">
                <Icon name="info" size={14} />
                <span className="xs">
                  {result.item_count - result.matched_count} item
                  {result.item_count - result.matched_count === 1 ? ' is' : 's are'} outside
                  this corpus's coverage. Those show nearest text matches, which are not
                  recommendations and cannot be accepted.
                </span>
              </div>
            )}
          </div>

          <div className="stack stack-3">
            {items.map((item) => {
              const verdict = CONFIDENCE[item.confidence] ?? CONFIDENCE.none;
              const isOpen = open === item.sr;
              const usable = item.confidence !== 'none';
              const recommended = item.results.filter(
                (r) => (r.stage_scores?.cross_encoder ?? 0) >= 0,
              );
              const shown = usable ? (recommended.length ? recommended : item.results.slice(0, 1)) : item.results;

              return (
                <article key={item.sr} className="card card-flush">
                  <button
                    className="card-head"
                    style={{ width: '100%', textAlign: 'left', cursor: 'pointer', background: 'none', border: 0 }}
                    onClick={() => setOpen(isOpen ? null : item.sr)}
                    aria-expanded={isOpen}
                  >
                    <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <span className="badge badge-neutral">Item {item.sr}</span>
                        <span className={`badge ${verdict.cls}`}>{verdict.label}</span>
                        {item.quantity && <span className="badge badge-neutral">{item.quantity}</span>}
                        {accepted[item.sr] && <span className="badge badge-ok">Added to spec</span>}
                      </div>
                      <span className="small">{item.text}</span>
                    </div>
                    <Icon name={isOpen ? 'chevronDown' : 'chevronRight'} size={15} />
                  </button>

                  {isOpen && (
                    <div className="card-body stack stack-4" style={{ borderTop: '1px solid var(--line)' }}>
                      {!usable && (
                        <div className="notice notice-crit" role="note">
                          <Icon name="alert" size={14} />
                          <span className="xs">
                            {item.confidence_reason || 'The corpus does not cover this item.'}
                            {' '}The entries below are the nearest text matches, not recommendations.
                          </span>
                        </div>
                      )}

                      <div className="stack stack-3">
                        {shown.map((r) => (
                          <div key={r.number} className="row" style={{ gap: 'var(--s3)', alignItems: 'flex-start' }}>
                            <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                                <Link
                                  to={`/app/standard/${encodeURIComponent(r.number)}`}
                                  className="mono small strong"
                                >
                                  {r.number}
                                </Link>
                                <CertificationBadge certification={r.certification} />
                                {r.status === 'superseded' && (
                                  <span className="badge badge-warn">Superseded</span>
                                )}
                              </div>
                              <span className="xs muted">{r.title}</span>
                            </div>
                          </div>
                        ))}
                      </div>

                      {usable && !accepted[item.sr] && (
                        <div className="row" style={{ gap: 'var(--s2)' }}>
                          <button className="btn btn-primary btn-sm" onClick={() => accept(item)}>
                            <Icon name="plus" size={13} />
                            Add {shown.length} to spec
                          </button>
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => setOpen(null)}
                          >
                            Skip this item
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
