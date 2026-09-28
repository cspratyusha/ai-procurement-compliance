import { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { CopyButton, EmptyState } from '../components/Primitives';
import { SCHEME_DESCRIPTION } from '../components/CertificationBadge';
import { useSpec } from '../state/SpecStore';
import { getCertificationRules, getCertification, getStandard, ApiError } from '../api/client';
import './query.css';   // .notice, shared with the query screen

/**
 * Which standards carry a mandatory BIS certification obligation.
 *
 * Read from BIS's own lists of products under compulsory certification
 * (Scheme I ISI mark, Scheme II CRS, Scheme X) and its hallmarking order,
 * every entry with the order that imposes it and a link to that order. The
 * failure that matters is asymmetric (saying no certification is needed when
 * an order requires it puts uncertifiable goods into a live tender), so the
 * statuses are kept strictly apart:
 *
 *   in_force        mandatory now, order quoted and linked
 *   deferred        named in an order whose enforcement is deferred: not yet mandatory
 *   voluntary       a BIS scheme exists, no order makes it compulsory (silver hallmarking)
 *   related_listed  not listed itself; a parent/general part or successor is
 *   checked_none    checked by hand, no scheme (codes of practice)
 *   not_listed      not on BIS's lists as read on the stated date
 */

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'ISI', label: 'ISI' },
  { id: 'CRS', label: 'CRS' },
  { id: 'Scheme X', label: 'Scheme X' },
  { id: 'Hallmark', label: 'Hallmarking' },
  { id: 'deferred', label: 'Deferred' },
];

const RENDER_LIMIT = 150;

/** A clause naming the order, worded for the scheme, so it is enforceable as written. */
function clauseFor(rule) {
  const order = (rule.qco ? `, as required by the ${rule.qco}` : '') + (rule.gazette ? ` (${rule.gazette})` : '');
  const conform = `The item shall conform to ${rule.is_number}`;
  if (rule.scheme === 'CRS') {
    return `${conform} and shall be registered with BIS under the Compulsory Registration Scheme${order}. ` +
      'The BIS registration number of the model offered shall be stated in the bid and marked on the product. ' +
      'Unregistered product shall be rejected at inspection.';
  }
  if (rule.scheme === 'Scheme X') {
    return `${conform} and shall be covered by a valid BIS certificate of conformity under Scheme X${order}. ` +
      'A copy of the certificate shall be furnished with the bid. Uncertified product shall be rejected at inspection.';
  }
  if (rule.scheme === 'Hallmark') {
    return `${conform} and shall bear the BIS hallmark (BIS logo, purity grade and six-digit HUID)${order}. ` +
      "Articles shall be supplied by a BIS-registered jeweller, whose registration number shall be stated in the bid. " +
      'Articles without a valid HUID shall be rejected at inspection.';
  }
  return `${conform} and shall bear a valid ISI mark under BIS Product Certification${order}. ` +
    "The supplier's BIS licence number shall be stated in the bid and shall be valid at the time of supply. " +
    'Uncertified product shall be rejected at inspection.';
}

function StatusBadge({ rec }) {
  if (rec.status === 'in_force') {
    return <span className="badge badge-accent"><Icon name="shield" size={12} />{rec.scheme} mandatory</span>;
  }
  if (rec.status === 'deferred') return <span className="badge badge-warn">Deferred, not yet mandatory</span>;
  if (rec.status === 'voluntary') {
    return <span className="badge badge-neutral">{rec.scheme === 'Hallmark' ? 'Hallmarking voluntary' : 'Voluntary'}</span>;
  }
  if (rec.status === 'related_listed') return <span className="badge badge-warn">Related standard listed</span>;
  if (rec.status === 'not_verified') return <span className="badge badge-neutral">Could not be checked</span>;
  return <span className="badge badge-neutral">No compulsory certification</span>;
}

function OrderLink({ rec }) {
  if (!rec.qco) return <span className="xs faint">Not recorded</span>;
  return rec.qco_url
    ? <a className="small" href={rec.qco_url} target="_blank" rel="noreferrer">{rec.qco} <Icon name="external" size={12} /></a>
    : <span className="small">{rec.qco}</span>;
}

export default function Certification() {
  const { code } = useParams();
  const spec = useSpec();

  const [state, setState] = useState('loading'); // loading | ready | error
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(code ? decodeURIComponent(code) : null);
  const [detail, setDetail] = useState(null);
  const [checked, setChecked] = useState(null);     // lookup of a standard not in the list
  const [lookup, setLookup] = useState('');
  const [filter, setFilter] = useState('all');

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

  const rules = useMemo(() => data?.rules ?? [], [data]);
  const listed = rules.find((r) => r.is_number === selected) ?? null;

  // The standard's title for context, and, for a standard not on the list,
  // its own certification answer from the engine.
  useEffect(() => {
    if (!selected) return undefined;
    const controller = new AbortController();
    // BIS often lists a number without its edition; the engine names the
    // edition the corpus holds.
    const corpusNumber = rules.find((r) => r.is_number === selected)?.corpus_number ?? selected;
    getStandard(corpusNumber, { signal: controller.signal })
      .then(setDetail)
      .catch(() => setDetail(null));
    if (!rules.some((r) => r.is_number === selected)) {
      getCertification(selected, { signal: controller.signal })
        .then((c) => setChecked({ ...c, is_number: selected }))
        .catch(() => setChecked({ is_number: selected, missing: true }));
    }
    return () => controller.abort();
  }, [selected, rules]);

  const rec = listed ?? (checked?.is_number === selected ? checked : null);
  const inSpec = selected ? spec.has(listed?.corpus_number ?? selected) : false;

  const shown = useMemo(() => {
    const term = lookup.trim().toLowerCase();
    return rules.filter((r) => {
      if (filter === 'deferred' ? r.status !== 'deferred' : filter !== 'all' && r.scheme !== filter) return false;
      if (!term) return true;
      return r.is_number.toLowerCase().includes(term) ||
        (r.product || '').toLowerCase().includes(term) ||
        (r.qco || '').toLowerCase().includes(term) ||
        (r.category || '').toLowerCase().includes(term);
    });
  }, [rules, lookup, filter]);

  const looksLikeNumber = /^\s*is\b/i.test(lookup) && /\d/.test(lookup);
  const cov = data?.coverage;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="cert-title">Certification &amp; compliance</h1>
          <p className="page-sub">
            Which products need BIS certification before they can be supplied, read from BIS&rsquo;s
            own lists of products under compulsory certification and its hallmarking order for
            gold. Every obligation names the order that imposes it, with a link to the order.
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
            body={`${error?.message ?? 'The standards engine did not respond.'} No rules are shown rather than stale ones.`}
            action={<button className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>Retry</button>}
          />
        </div>
      )}

      {state === 'ready' && (
        <div className="stack stack-4">
          <div className="notice notice-info" role="note">
            <Icon name="info" size={15} />
            <div className="stack stack-2">
              <span className="small strong">
                {cov.mandatory.toLocaleString('en-IN')} standards under compulsory certification
                {cov.deferred ? ` · ${cov.deferred} named in deferred orders` : ''}
                {cov.retrieved ? ` · BIS lists read on ${new Date(cov.retrieved).toLocaleDateString('en-IN', { dateStyle: 'medium' })}` : ''}
              </span>
              <span className="xs">
                A standard not on these lists has no compulsory certification, unless an order
                notified after that date adds it. Deferred entries are named in an order whose
                enforcement has been put off, so they are not yet mandatory.
              </span>
              <span className="xs">
                Sources:{' '}
                {Object.entries(cov.sources ?? {}).map(([scheme, url], i) => (
                  <span key={scheme}>{i > 0 && ', '}<a href={url} target="_blank" rel="noreferrer">
                    {scheme === 'Hallmark' ? 'BIS hallmarking order' : `BIS ${scheme === 'X' ? 'Scheme X' : scheme} list`}
                  </a></span>
                ))}
              </span>
            </div>
          </div>

          <div className="grid split split-left" style={{ '--rail': '340px' }}>
            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">On BIS&rsquo;s lists</h2>
                <span className="badge badge-neutral">{shown.length.toLocaleString('en-IN')}</span>
              </div>
              <div className="stack stack-2" style={{ padding: 'var(--s3)' }}>
                <label className="label sr-only" htmlFor="cert-search">Search</label>
                <input
                  id="cert-search"
                  className="input"
                  placeholder="IS number, product or order…"
                  value={lookup}
                  onChange={(e) => setLookup(e.target.value)}
                />
                <div className="seg" role="group" aria-label="Filter by scheme">
                  {FILTERS.map((f) => (
                    <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="stack" style={{ padding: 'var(--s2)', maxHeight: 560, overflowY: 'auto' }}>
                {shown.length === 0 && (
                  <div className="stack stack-2" style={{ padding: 'var(--s3)' }}>
                    <span className="xs muted">Nothing on the lists matches.</span>
                    {looksLikeNumber && (
                      <button type="button" className="btn btn-secondary btn-sm" style={{ alignSelf: 'flex-start' }}
                        onClick={() => setSelected(lookup.trim())}>
                        Check {lookup.trim()}
                      </button>
                    )}
                  </div>
                )}
                {shown.slice(0, RENDER_LIMIT).map((r) => (
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
                        {r.status === 'in_force' && <span className="badge badge-accent">{r.scheme}</span>}
                        {r.status === 'deferred' && <span className="badge badge-warn">Deferred</span>}
                        {r.status === 'voluntary' && <span className="badge badge-neutral">{r.scheme} voluntary</span>}
                        {r.status === 'checked_none' && <span className="badge badge-neutral">No scheme</span>}
                      </span>
                      {r.product && <span className="xs faint cert-product">{r.product}</span>}
                    </span>
                  </button>
                ))}
                {shown.length > RENDER_LIMIT && (
                  <span className="xs muted" style={{ padding: 'var(--s3)' }}>
                    Showing {RENDER_LIMIT} of {shown.length.toLocaleString('en-IN')}. Search to narrow the list.
                  </span>
                )}
              </div>
            </div>

            {!rec ? (
              <div className="card">
                <EmptyState icon="shield" title="Select a standard"
                  body="Choose a standard to see its certification position and the order it traces to, or type any IS number to check it." />
              </div>
            ) : rec.missing ? (
              <div className="card">
                <EmptyState icon="alert" title={`${rec.is_number} is not in the catalogue`}
                  body="Check the number. Only standards the engine holds can be looked up here." />
              </div>
            ) : (
              <div className="stack stack-4">
                <div className="card stack stack-4">
                  <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
                    <div className="stack stack-2" style={{ minWidth: 0 }}>
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <span className="mono strong" style={{ fontSize: 'var(--fs-md)' }}>{rec.is_number}</span>
                        <StatusBadge rec={rec} />
                      </div>
                      {detail?.title && <span className="xs muted">{detail.title}</span>}
                    </div>
                    {rec.status === 'in_force' && !inSpec && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => spec.add({
                          code: detail?.number || rec.corpus_number || rec.is_number,
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

                  <div className={`notice ${rec.status === 'in_force' || rec.status === 'deferred' || rec.status === 'related_listed' ? 'notice-warn' : 'notice-info'}`} style={{ margin: 0 }}>
                    <Icon name={rec.status === 'in_force' ? 'shield' : 'info'} size={15} />
                    <span className="xs">{rec.explanation}</span>
                  </div>

                  {rec.related?.length > 0 && (
                    <div className="stack stack-2">
                      <span className="xs faint">Listed standards this relates to</span>
                      <span className="row wrap" style={{ gap: 'var(--s2)' }}>
                        {rec.related.map((n) => (
                          <button key={n} type="button" className="badge badge-neutral mono" onClick={() => setSelected(n)}>{n}</button>
                        ))}
                      </span>
                    </div>
                  )}

                  {['in_force', 'deferred', 'voluntary'].includes(rec.status) && (
                    <>
                      <hr className="divider" />
                      <div className="grid grid-2" style={{ gap: 'var(--s4)' }}>
                        <div className="stack stack-2">
                          <span className="xs faint">Scheme</span>
                          <span className="small">{SCHEME_DESCRIPTION[rec.scheme] ?? rec.scheme}</span>
                        </div>
                        <div className="stack stack-2">
                          <span className="xs faint">Statutory order</span>
                          {rec.status === 'voluntary'
                            ? <span className="xs faint">None: the scheme is voluntary</span>
                            : <OrderLink rec={rec} />}
                        </div>
                        <div className="stack stack-2">
                          <span className="xs faint">Gazette notification</span>
                          <span className="small">{rec.gazette || <span className="xs faint">Not recorded</span>}</span>
                        </div>
                        <div className="stack stack-2">
                          <span className="xs faint">Listed by BIS as</span>
                          <span className="small mono">{rec.listed_as || rec.is_number}</span>
                        </div>
                      </div>
                      {rec.products?.length > 0 && (
                        <div className="stack stack-2">
                          <span className="xs faint">Products as BIS lists them</span>
                          <ul className="cert-products">
                            {rec.products.map((p) => <li key={p} className="small">{p}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {(rec.status === 'in_force' || rec.status === 'voluntary') && (
                  <div className="card card-flush">
                    <div className="card-head">
                      <div className="stack stack-2">
                        <h2 className="card-title">{rec.status === 'voluntary' ? 'Optional tender clause' : 'Copy-ready tender clause'}</h2>
                        <span className="xs faint">
                          {rec.status === 'voluntary'
                            ? 'Not required by law for this product; include it only if the tender should demand it'
                            : 'Names the standard and the statutory order, so the requirement is enforceable as written'}
                        </span>
                      </div>
                      <CopyButton text={clauseFor(rec)} />
                    </div>
                    <div className="card-body">
                      <blockquote className="clause">{clauseFor(rec)}</blockquote>
                    </div>
                  </div>
                )}

                {detail && (
                  <Link to={`/app/standard/${encodeURIComponent(detail.number)}`} className="card card-link row-between">
                    <span className="stack stack-2">
                      <span className="small strong">Open standard detail</span>
                      <span className="xs muted">Scope, edition and amendments for {detail.number}</span>
                    </span>
                    <Icon name="chevronRight" size={16} />
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
