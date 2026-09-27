import { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { CopyButton, EmptyState } from '../components/Primitives';
import { useSpec } from '../state/SpecStore';
import { getCertificationRules, getStandard, ApiError } from '../api/client';
import './query.css';   // .notice, shared with the query screen

/**
 * Which standards carry a mandatory BIS certification obligation.
 *
 * The notice this screen used to carry said the rules "are not sourced from
 * the official BIS compulsory-certification lists". That was false, and had
 * been for several phases: the data in
 * `data/certification/certification_rules.json` was read from the BIS Scheme I
 * product list and cross-checked against Quality Control Order notifications,
 * and every other screen in the app has been serving it. The page itself was
 * still on a two-entry hardcoded fixture.
 *
 * Certification is the highest-stakes data in this system, because the failure
 * is asymmetric. Saying a product needs an ISI mark when it does not is an
 * inconvenience. Saying it does not when it does puts uncertifiable goods into
 * a live tender that cannot lawfully be supplied. So three states are kept
 * strictly apart and never collapsed:
 *
 *   mandatory      confirmed against a named QCO, which is quoted
 *   none           checked, and no scheme applies
 *   not researched not in this list at all, NOT a clearance, and the reason
 *                  this screen lists only researched standards rather than
 *                  rendering every corpus entry as "voluntary"
 *
 * Every mandatory claim shows the order and gazette notification behind it, so
 * an officer can verify it rather than trusting the screen.
 */

export default function Certification() {
  const { code } = useParams();
  const spec = useSpec();

  const [state, setState] = useState('loading'); // loading | ready | error
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(code ? decodeURIComponent(code) : null);
  const [detail, setDetail] = useState(null);
  const [lookup, setLookup] = useState('');

  useEffect(() => {
    const controller = new AbortController();

    getCertificationRules({ signal: controller.signal })
      .then((payload) => {
        setData(payload);
        setState('ready');
        setSelected((current) => current ?? payload.rules[0]?.is_number ?? null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiError ? err : new ApiError('Could not load certification rules.'));
        setState('error');
      });

    return () => controller.abort();
  }, []);

  // The standard's title and scope, for context beside the obligation.
  useEffect(() => {
    if (!selected) { setDetail(null); return undefined; }

    const controller = new AbortController();
    getStandard(selected, { signal: controller.signal })
      .then(setDetail)
      // Not in the corpus: the rule still stands on its own, so this is a
      // missing nicety rather than a failure.
      .catch(() => setDetail(null));

    return () => controller.abort();
  }, [selected]);

  const rules = data?.rules ?? [];
  const rec = rules.find((r) => r.is_number === selected) ?? null;
  const inSpec = selected ? spec.has(selected) : false;

  const shown = useMemo(() => {
    const term = lookup.trim().toLowerCase();
    if (!term) return rules;
    return rules.filter(
      (r) =>
        r.is_number.toLowerCase().includes(term) ||
        (r.product || '').toLowerCase().includes(term) ||
        (r.qco || '').toLowerCase().includes(term),
    );
  }, [rules, lookup]);

  /** A clause naming the order, so the requirement is enforceable as written. */
  const clauseFor = (rule) =>
    `The item shall conform to ${rule.is_number} and shall bear a valid ${rule.scheme} ` +
    `mark under BIS Product Certification` +
    (rule.qco ? `, as required by the ${rule.qco}` : '') +
    (rule.gazette ? ` (${rule.gazette})` : '') +
    `. The supplier's BIS licence number shall be stated in the bid and shall be ` +
    `valid at the time of supply. Uncertified product shall be rejected at inspection.`;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="cert-title">Certification &amp; compliance</h1>
          <p className="page-sub">
            Whether a product carries a mandatory certification obligation is a legally
            distinct question from which standard describes it. Each position below
            traces to a named Quality Control Order.
          </p>
        </div>
      </div>

      {state === 'loading' && (
        <div className="stack stack-3" aria-busy="true">
          <div className="skeleton" style={{ height: 64 }} />
          <div className="skeleton" style={{ height: 320 }} />
        </div>
      )}

      {state === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not load certification rules"
            body={
              `${error?.message ?? 'The standards engine did not respond.'} ` +
              'No rules are shown rather than stale ones, a wrong certification claim is ' +
              'the most costly error this screen can make.'
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
        <div className="stack stack-4">
          <div className="notice notice-info" role="note">
            <Icon name="info" size={15} />
            <div className="stack stack-2">
              <span className="small strong">
                {data.coverage.standards_researched} standards researched ·
                {' '}{data.coverage.mandatory} carry a mandatory scheme
              </span>
              <span className="xs">{data.coverage.note}</span>
              <span className="xs">Source: {data.coverage.source}</span>
            </div>
          </div>

          <div className="grid split split-left" style={{ '--rail': '320px' }}>
            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Researched standards</h2>
                <span className="badge badge-neutral">{shown.length}</span>
              </div>
              <div style={{ padding: 'var(--s3)' }}>
                <label className="label sr-only" htmlFor="cert-search">Search rules</label>
                <input
                  id="cert-search"
                  className="input"
                  placeholder="IS number, product or order…"
                  value={lookup}
                  onChange={(e) => setLookup(e.target.value)}
                />
              </div>
              <div className="stack" style={{ padding: 'var(--s2)', maxHeight: 520, overflowY: 'auto' }}>
                {shown.length === 0 ? (
                  <span className="xs muted" style={{ padding: 'var(--s3)' }}>
                    Nothing matches. Only researched standards are listed here.
                  </span>
                ) : shown.map((r) => (
                  <button
                    key={r.is_number}
                    className={`alert-mini ${selected === r.is_number ? 'is-active-row' : ''}`}
                    style={{ width: '100%', textAlign: 'left' }}
                    onClick={() => setSelected(r.is_number)}
                    aria-pressed={selected === r.is_number}
                  >
                    <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <span className="row wrap" style={{ gap: 6 }}>
                        <span className="mono xs strong">{r.is_number}</span>
                        {r.mandatory
                          ? <span className="badge badge-accent">{r.scheme}</span>
                          : <span className="badge badge-neutral">No scheme</span>}
                      </span>
                      {r.product && <span className="xs faint">{r.product}</span>}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {!rec ? (
              <div className="card">
                <EmptyState
                  icon="shield"
                  title="Select a standard"
                  body="Choose a standard to see its certification position and the order it traces to."
                />
              </div>
            ) : !rec.mandatory ? (
              <div className="card stack stack-4">
                <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                  <span className="mono strong" style={{ fontSize: 'var(--fs-md)' }}>{rec.is_number}</span>
                  <span className="badge badge-neutral">No mandatory scheme</span>
                </div>
                {detail?.title && <span className="xs muted">{detail.title}</span>}
                <div className="notice notice-info" style={{ margin: 0 }}>
                  <Icon name="info" size={15} />
                  <span className="xs">{rec.explanation}</span>
                </div>
                <p className="xs muted">
                  This standard was checked and no mandatory scheme was found, which is a
                  stronger statement than the silence for an unresearched standard. A buyer
                  may still require certification contractually, but it cannot be enforced
                  as a statutory obligation.
                </p>
              </div>
            ) : (
              <div className="stack stack-4">
                <div className="card stack stack-4">
                  <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
                    <div className="stack stack-2" style={{ minWidth: 0 }}>
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <span className="mono strong" style={{ fontSize: 'var(--fs-md)' }}>
                          {rec.is_number}
                        </span>
                        <span className="badge badge-accent">
                          <Icon name="shield" size={12} />{rec.scheme} mandatory
                        </span>
                        {rec.confidence === 'confirmed' && (
                          <span className="badge badge-ok">Confirmed</span>
                        )}
                      </div>
                      {detail?.title && <span className="xs muted">{detail.title}</span>}
                    </div>
                    {!inSpec && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => spec.add({
                          code: rec.is_number,
                          title: detail?.title || rec.product || rec.is_number,
                          role: 'certification',
                          scheme: rec.scheme,
                          version: 'latest',
                          addedFrom: 'certification panel',
                        })}
                      >
                        <Icon name="plus" size={14} /> Add clause to spec
                      </button>
                    )}
                  </div>

                  <div className="notice notice-warn" style={{ margin: 0 }}>
                    <Icon name="alert" size={15} />
                    <span className="xs">{rec.explanation}</span>
                  </div>

                  <hr className="divider" />

                  <div className="grid grid-2" style={{ gap: 'var(--s4)' }}>
                    {[
                      ['Scheme', rec.scheme === 'ISI'
                        ? 'Scheme I, Standard Mark (ISI), under BIS licence'
                        : rec.scheme === 'CRS'
                          ? 'Scheme II, Compulsory Registration Scheme'
                          : 'BIS Hallmarking'],
                      ['Product as listed by BIS', rec.product],
                      ['Statutory order', rec.qco],
                      ['Gazette notification', rec.gazette],
                    ].map(([k, v]) => (
                      <div key={k} className="stack stack-2">
                        <span className="xs faint">{k}</span>
                        <span className="small">
                          {v || <span className="xs faint">Not recorded</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="card card-flush">
                  <div className="card-head">
                    <div className="stack stack-2">
                      <h2 className="card-title">Copy-ready tender clause</h2>
                      <span className="xs faint">
                        Names the standard and the statutory order, so the requirement is
                        enforceable as written
                      </span>
                    </div>
                    <CopyButton text={clauseFor(rec)} />
                  </div>
                  <div className="card-body">
                    <blockquote className="clause">{clauseFor(rec)}</blockquote>
                  </div>
                </div>

                <Link
                  to={`/app/standard/${encodeURIComponent(rec.is_number)}`}
                  className="card card-link row-between"
                >
                  <span className="stack stack-2">
                    <span className="small strong">Open standard detail</span>
                    <span className="xs muted">
                      Scope, edition and amendments for {rec.is_number}
                    </span>
                  </span>
                  <Icon name="chevronRight" size={16} />
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
