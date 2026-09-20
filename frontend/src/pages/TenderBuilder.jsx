import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState, CopyButton } from '../components/Primitives';
import { CertificationBanner } from '../components/CertificationBadge';
import { retrieve, ApiError } from '../api/client';
import './builder.css';

/**
 * A simplified tender-specification form with live standards recommendations
 * beside it.
 *
 * The problem statement asks for this to sit inside a procurement portal such
 * as GeM. We have no integration access, so this demonstrates the pattern: as
 * an official types the item description, the engine searches in the
 * background and offers the standards that belong in the specification.
 *
 * Everything here is live. The recommendations come from the real engine, the
 * certification flags from the curated BIS data, and the generated clause is
 * assembled from whichever standards the official actually accepted.
 */

const CATEGORIES = [
  'Electrical works',
  'Civil works',
  'Water supply & plumbing',
  'Structural steel',
  'Safety equipment',
  'Other',
];

const UNITS = ['metres', 'numbers', 'kilograms', 'tonnes', 'bags', 'litres'];

/** Wait for typing to settle before searching, so every keystroke is not a query. */
const DEBOUNCE_MS = 900;

export default function TenderBuilder() {
  const [form, setForm] = useState({
    reference: 'MHI/2026/PROC/0001',
    category: 'Electrical works',
    description: '',
    quantity: '',
    unit: 'metres',
  });

  const [results, setResults] = useState([]);
  const [confidence, setConfidence] = useState(null);
  const [status, setStatus] = useState('idle'); // idle | searching | done | error
  const [error, setError] = useState(null);
  const [accepted, setAccepted] = useState([]);

  const abortRef = useRef(null);
  const timerRef = useRef(null);

  const search = useCallback(async (text) => {
    if (text.trim().length < 12) {
      setResults([]);
      setStatus('idle');
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus('searching');
    setError(null);

    try {
      const data = await retrieve(text, { topK: 5, signal: controller.signal });
      if (controller.signal.aborted) return;
      setResults(data.results ?? []);
      setConfidence(data.confidence);
      setStatus('done');
    } catch (err) {
      if (controller.signal.aborted || err.name === 'AbortError') return;
      setError(err instanceof ApiError ? err : new ApiError('Search failed.'));
      setStatus('error');
    }
  }, []);

  // Re-search as the description settles.
  useEffect(() => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => search(form.description), DEBOUNCE_MS);
    return () => clearTimeout(timerRef.current);
  }, [form.description, search]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const toggleAccept = (standard) => {
    setAccepted((list) =>
      list.some((s) => s.number === standard.number)
        ? list.filter((s) => s.number !== standard.number)
        : [...list, standard],
    );
  };

  const isAccepted = (number) => accepted.some((s) => s.number === number);

  // Certification obligations follow from the standards actually accepted,
  // not from what the engine happened to suggest.
  const mandatory = accepted.filter((s) => s.certification?.mandatory);

  const clause = buildTenderClause(form, accepted);

  return (
    <div className="container page">
      <div className="notice notice-info" role="note" style={{ marginBottom: 'var(--s5)' }}>
        <Icon name="info" size={15} />
        <div className="stack stack-2">
          <span className="small strong">Demonstration of an in-portal integration</span>
          <span className="xs">
            This shows how the engine would sit inside an e-procurement portal such as GeM,
            recommending standards as a tender is drafted. It is not connected to GeM — we
            have no integration access. The recommendations, certification flags and the
            generated clause below are all live.
          </span>
        </div>
      </div>

      <div className="page-head">
        <div>
          <h1 className="page-title">Tender builder</h1>
          <p className="page-sub">
            Describe the item you are procuring. Applicable Indian Standards appear
            alongside as you type.
          </p>
        </div>
      </div>

      <div className="grid split" style={{ '--rail': '380px' }}>
        {/* ---------------- Tender form ---------------- */}
        <div className="stack stack-4">
          <section className="card stack stack-4">
            <span className="eyebrow">Tender details</span>

            <div className="row wrap" style={{ gap: 'var(--s3)' }}>
              <div className="field grow" style={{ minWidth: 200 }}>
                <label className="label xs" htmlFor="t-ref">Tender reference</label>
                <input
                  id="t-ref"
                  className="input mono"
                  value={form.reference}
                  onChange={update('reference')}
                />
              </div>
              <div className="field grow" style={{ minWidth: 200 }}>
                <label className="label xs" htmlFor="t-cat">Category</label>
                <select id="t-cat" className="select" value={form.category} onChange={update('category')}>
                  {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
            </div>

            <div className="field">
              <label className="label xs" htmlFor="t-desc">
                Item description
              </label>
              <textarea
                id="t-desc"
                className="textarea"
                style={{ minHeight: 96 }}
                value={form.description}
                onChange={update('description')}
                placeholder="e.g. PVC insulated single core copper conductor cable, 1.5 sq mm, 1100 V, for concealed conduit wiring"
              />
              <span className="xs faint">
                {form.description.trim().length < 12
                  ? 'Keep typing — recommendations appear once there is enough to go on.'
                  : status === 'searching'
                    ? 'Looking for applicable standards…'
                    : `${results.length} standard${results.length === 1 ? '' : 's'} suggested`}
              </span>
            </div>

            <div className="row wrap" style={{ gap: 'var(--s3)' }}>
              <div className="field" style={{ minWidth: 140 }}>
                <label className="label xs" htmlFor="t-qty">Quantity</label>
                <input
                  id="t-qty"
                  className="input"
                  type="number"
                  min="0"
                  value={form.quantity}
                  onChange={update('quantity')}
                  placeholder="500"
                />
              </div>
              <div className="field" style={{ minWidth: 140 }}>
                <label className="label xs" htmlFor="t-unit">Unit</label>
                <select id="t-unit" className="select" value={form.unit} onChange={update('unit')}>
                  {UNITS.map((u) => <option key={u}>{u}</option>)}
                </select>
              </div>
            </div>
          </section>

          {/* ---------------- Generated clause ---------------- */}
          <section className="card stack stack-4">
            <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
              <span className="eyebrow">Specification clause</span>
              {accepted.length > 0 && <CopyButton text={clause} label="Copy clause" />}
            </div>

            {accepted.length === 0 ? (
              <p className="xs muted">
                Accept one or more standards from the panel and the conformance clause
                for this line item is assembled here, ready to paste into the tender.
              </p>
            ) : (
              <>
                <blockquote className="clause xs" style={{ whiteSpace: 'pre-wrap' }}>
                  {clause}
                </blockquote>
                <p className="xs muted">
                  Drafted from the {accepted.length} standard{accepted.length === 1 ? '' : 's'} you
                  accepted. Review before issuing — this is a drafting aid, not legal advice.
                </p>
              </>
            )}
          </section>

          {mandatory.length > 0 && (
            <section className="stack stack-3">
              <span className="eyebrow">Certification obligations</span>
              {mandatory.map((s) => (
                <CertificationBanner
                  key={s.number}
                  certification={s.certification}
                  isNumber={s.number}
                />
              ))}
            </section>
          )}
        </div>

        {/* ---------------- Live recommendations ---------------- */}
        <div className="stack stack-4">
          <div className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title">Suggested standards</h2>
                <span className="xs faint">Updated as you type</span>
              </div>
              {status === 'searching' && <span className="spinner" />}
            </div>

            <div className="card-body stack stack-3">
              {status === 'error' && (
                <EmptyState
                  icon="alert"
                  title="Engine unreachable"
                  body={error?.message ?? 'Could not reach the standards engine.'}
                />
              )}

              {status === 'idle' && form.description.trim().length < 12 && (
                <p className="xs muted">
                  Start describing the item and applicable standards will be suggested here.
                </p>
              )}

              {status === 'done' && confidence === 'none' && (
                <div className="notice notice-crit">
                  <Icon name="alert" size={14} />
                  <span className="xs">
                    No standard in the covered sectors matches this description. Nothing is
                    suggested rather than offering a poor guess.
                  </span>
                </div>
              )}

              {status !== 'error' && confidence !== 'none' && results.map((r) => (
                <div key={r.id} className={`rec-mini ${isAccepted(r.number) ? 'is-accepted' : ''}`}>
                  <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <div className="row wrap" style={{ gap: 6 }}>
                      <Link
                        to={`/app/standard/${encodeURIComponent(r.number)}`}
                        className="mono xs strong build-link"
                      >
                        {r.number}
                      </Link>
                      {r.certification?.mandatory && (
                        <span className="badge badge-accent">
                          <Icon name="shield" size={10} />ISI
                        </span>
                      )}
                      {r.status === 'superseded' && (
                        <span className="badge badge-crit">Superseded</span>
                      )}
                    </div>
                    <span className="xs faint" style={{ lineHeight: 1.45 }}>{r.title}</span>
                  </div>
                  <button
                    type="button"
                    className={`btn btn-sm ${isAccepted(r.number) ? 'btn-secondary' : 'btn-primary'}`}
                    onClick={() => toggleAccept(r)}
                  >
                    {isAccepted(r.number) ? 'Accepted' : 'Accept'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Assemble a conformance clause from the accepted standards.
 *
 * Deliberately plain and conservative: it states conformance, quantity and any
 * certification requirement, and nothing it cannot support from the data.
 */
function buildTenderClause(form, accepted) {
  if (!accepted.length) return '';

  const lines = [];
  const numbers = accepted.map((s) => s.number);

  const quantity = form.quantity
    ? ` Quantity: ${form.quantity} ${form.unit}.`
    : '';

  lines.push(
    `1. SCOPE — Supply of ${form.description.trim() || 'the item specified'}.${quantity}`,
  );

  lines.push(
    `2. CONFORMANCE — The item shall conform in all respects to ${
      numbers.length === 1
        ? numbers[0]
        : `${numbers.slice(0, -1).join(', ')} and ${numbers[numbers.length - 1]}`
    }, in the latest edition in force on the date of supply, including all amendments.`,
  );

  const certified = accepted.filter((s) => s.certification?.mandatory);
  if (certified.length) {
    const qcos = [...new Set(certified.map((s) => s.certification.qco).filter(Boolean))];
    lines.push(
      `3. CERTIFICATION — ${certified.map((s) => s.number).join(', ')} ${
        certified.length === 1 ? 'falls' : 'fall'
      } under mandatory BIS certification. The supplier shall hold a valid BIS licence and the goods shall bear the Standard Mark (ISI). The licence number shall be quoted in the bid.${
        qcos.length ? ` Governing order: ${qcos.join('; ')}.` : ''
      }`,
    );
  }

  const superseded = accepted.filter((s) => s.status === 'superseded');
  if (superseded.length) {
    lines.push(
      `${lines.length + 1}. NOTE — ${superseded
        .map((s) => s.number)
        .join(', ')} ${superseded.length === 1 ? 'is' : 'are'} recorded as superseded. Confirm the current edition with BIS before issuing this tender.`,
    );
  }

  lines.push(
    `${lines.length + 1}. INSPECTION — Test certificates demonstrating conformance to the above standards shall be furnished with each supply lot.`,
  );

  return lines.join('\n\n');
}
