import { useState, useMemo, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { CopyButton, EmptyState } from '../components/Primitives';
import { useSpec, ROLE_ORDER, ROLE_LABEL, buildClause } from '../state/SpecStore';
import { useAuth } from '../state/Auth';
import { getStandard, recordActivity } from '../api/client';
import { specDocument, specRecord, fileName, download, printDocument } from '../state/exportSpec';
import './builder.css';
import './query.css';   // .notice, shared with the query screen

const EXPORTS = [
  { id: 'doc', icon: 'file', label: 'Word document', hint: 'A .doc file for the tender document' },
  { id: 'pdf', icon: 'download', label: 'Print or save as PDF', hint: 'Opens the print dialog' },
  { id: 'clip', icon: 'copy', label: 'Copy clause text', hint: 'Paste straight into the portal' },
  { id: 'json', icon: 'external', label: 'JSON record', hint: 'Machine-readable, for a portal or an archive' },
];

export default function Builder() {
  const spec = useSpec();
  const { user, org } = useAuth();
  const { list, grouped, gaps, count, frozen } = spec;
  const [exported, setExported] = useState(null);   // { ok, text }

  const clause = useMemo(() => buildClause(list), [list]);

  /**
   * Certification status per basket item, from the engine.
   *
   * This was a hardcoded lookup table covering two standards. It is now
   * fetched, which matters for a reason beyond freshness: the engine
   * distinguishes a confirmed requirement from 'not_verified', and the
   * fixture could only express "mandatory or absent". Treating an unresearched
   * standard as having no certification obligation is precisely the error
   * that puts an uncertifiable product into a live tender.
   */
  const [certInfo, setCertInfo] = useState({});   // code -> CertificationInfo
  // Codes already requested, kept in a ref so the effect does not depend on
  // the state it writes -- depending on `certInfo` would re-run this on every
  // resolution and re-request anything still in flight.
  const requested = useRef(new Set());

  useEffect(() => {
    const codes = list.map((i) => i.code).filter((c) => !requested.current.has(c));
    if (codes.length === 0) return undefined;

    codes.forEach((c) => requested.current.add(c));
    const controller = new AbortController();

    Promise.all(
      codes.map((code) =>
        getStandard(code, { signal: controller.signal })
          .then((data) => [code, data.certification ?? null])
          // A standard outside the corpus has no record to report. Null is
          // "unknown", which the UI renders differently from "not required".
          .catch(() => [code, null]),
      ),
    ).then((pairs) => {
      if (controller.signal.aborted) return;
      setCertInfo((prev) => ({ ...prev, ...Object.fromEntries(pairs) }));
    });

    return () => controller.abort();
  }, [list]);

  // Only positively confirmed obligations. 'not_verified' is not a clearance,
  // but it is also not a requirement we can assert in a tender clause.
  const certs = useMemo(
    () => list
      .map((i) => ({ code: i.code, rec: certInfo[i.code] }))
      .filter((c) => c.rec?.mandatory),
    [list, certInfo]
  );

  // Standards that need a look before issuing: named in a deferred order, a
  // related part is listed, or the lists could not be read.
  const unverified = useMemo(
    () => list.filter((i) => ['deferred', 'related_listed', 'not_verified'].includes(certInfo[i.code]?.status)),
    [list, certInfo]
  );

  const critical = gaps.filter((g) => g.severity === 'critical');
  const canExport = count > 0 && critical.length === 0;

  const certClause = (rec) => {
    const order = rec.qco ? `, as required by the ${rec.qco}${rec.gazette ? ` (${rec.gazette})` : ''}` : '';
    if (rec.scheme === 'CRS') {
      return `The item shall be registered with BIS under the Compulsory Registration Scheme${order}. ` +
        'The registration number of the model offered shall be stated in the bid and marked on the product.';
    }
    if (rec.scheme === 'Scheme X') {
      return `The item shall be covered by a valid BIS certificate of conformity under Scheme X${order}. ` +
        'A copy of the certificate shall be furnished with the bid.';
    }
    if (rec.scheme === 'Hallmark') {
      return `The articles shall bear the BIS hallmark (BIS logo, purity grade and six-digit HUID)${order}, ` +
        'and shall be supplied by a BIS-registered jeweller whose registration number is stated in the bid.';
    }
    return `The item shall bear a valid ISI mark under BIS Product Certification${order}. ` +
      'The licence number shall be stated in the bid and shall be valid at the time of supply.';
  };

  const runExport = async (kind) => {
    const project = spec.project || 'Specification';
    const input = {
      project, list, clause, frozen, user, org,
      certClauses: certs.map(({ code, rec }) => ({ code, text: certClause(rec) })),
    };
    let result;
    if (kind === 'doc') {
      download(fileName(project, 'doc'), specDocument(input), 'application/msword');
      result = { ok: true, text: `Downloaded ${fileName(project, 'doc')}.` };
    } else if (kind === 'pdf') {
      result = printDocument(specDocument(input))
        ? { ok: true, text: 'Opened the print dialog. Choose "Save as PDF" to keep a copy.' }
        : { ok: false, text: 'The browser blocked the print window. Allow pop-ups for this site and try again.' };
    } else if (kind === 'clip') {
      try {
        await navigator.clipboard.writeText(clause);
        result = { ok: true, text: 'Clause text copied.' };
      } catch {
        result = { ok: false, text: 'The browser did not allow copying. Select the clause text and copy it by hand.' };
      }
    } else {
      download(fileName(project, 'json'), JSON.stringify(specRecord(input), null, 2), 'application/json');
      result = { ok: true, text: `Downloaded ${fileName(project, 'json')}.` };
    }
    setExported(result);
    if (result.ok) {
      recordActivity('export.' + kind, `Exported ${project} (${count} standards) as ${EXPORTS.find((e) => e.id === kind).label}`,
        { project, standards: list.map((i) => i.code) });
    }
  };

  if (count === 0) {
    return (
      <div className="container page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Spec builder</h1>
            <p className="page-sub">
              Standards you collect are assembled here into clause text, checked for gaps, and
              frozen with a timestamp for the audit record.
            </p>
          </div>
        </div>
        <div className="card">
          <EmptyState
            icon="layers"
            title="No standards collected yet"
            body="Run a query and add standards from the recommendations, the detail page, or the related-standards map. They will accumulate here."
            action={<Link to="/app/query" className="btn btn-primary btn-sm">Start a query</Link>}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="builder-title">Spec builder</h1>
          <p className="page-sub">
            {count} standard{count === 1 ? '' : 's'} collected
            {spec.project ? ` for ${spec.project}` : ''}. Reorder within a group, review the gap
            warnings, then export or freeze.
          </p>
        </div>
        <div className="row" style={{ gap: 'var(--s2)' }}>
          <button
            className="btn btn-primary"
            data-demo-target="builder-freeze"
            disabled={!canExport}
            onClick={() => spec.freeze('Tender draft')}
          >
            <Icon name="shield" size={15} />
            Freeze recommendation
          </button>
        </div>
      </div>

      <div className="grid split" style={{ "--rail": "340px" }}>
        {/* ---------------- Left: assembled spec ---------------- */}
        <div className="stack stack-5" data-demo-target="builder-list">
          {gaps.length > 0 && (
            <section className="stack stack-2" data-demo-target="builder-gaps">
              {gaps.map((g, i) => (
                <div key={i} className={`notice ${g.severity === 'critical' ? 'notice-crit' : 'notice-warn'}`}>
                  <Icon name="alert" size={15} />
                  <div className="stack stack-2">
                    <span className="xs strong">
                      {g.severity === 'critical' ? 'Blocks export' : 'Recommended'}
                    </span>
                    <span className="xs">{g.text}</span>
                  </div>
                </div>
              ))}
            </section>
          )}

          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Collected standards</h2>
              <span className="badge badge-neutral tabular">{count}</span>
            </div>

            <div className="stack" style={{ padding: 'var(--s4)', gap: 'var(--s5)' }}>
              {ROLE_ORDER.filter((r) => grouped[r]?.length).map((role) => (
                <div key={role} className="stack stack-3">
                  <div className="row-between">
                    <span className="eyebrow">{ROLE_LABEL[role]}</span>
                    <span className="xs faint tabular">{grouped[role].length}</span>
                  </div>

                  {grouped[role].map((it, idx) => (
                    <div key={it.code} className="build-row">
                      <span className="build-index mono xs">{idx + 1}</span>

                      <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                        <div className="row wrap" style={{ gap: 6 }}>
                          <Link to={`/app/standard/${encodeURIComponent(it.code)}`} className="mono small strong build-link">
                            {it.code}
                          </Link>
                          {it.amendment && <span className="badge badge-neutral">{it.amendment}</span>}
                          {it.version === 'superseded' && <span className="badge badge-crit">Superseded</span>}
                          {certInfo[it.code]?.mandatory && (
                            <span className="badge badge-accent"><Icon name="shield" size={11} /> Certified</span>
                          )}
                        </div>
                        <span className="xs muted">{it.title}</span>
                        {it.addedFrom && <span className="xs faint">Added from {it.addedFrom}</span>}
                      </div>

                      <div className="row" style={{ gap: 2, flexShrink: 0 }}>
                        <button className="btn-icon basket-mini" onClick={() => spec.move(it.code, -1)} aria-label={`Move ${it.code} up`}>
                          <Icon name="chevronDown" size={13} style={{ transform: 'rotate(180deg)' }} />
                        </button>
                        <button className="btn-icon basket-mini" onClick={() => spec.move(it.code, 1)} aria-label={`Move ${it.code} down`}>
                          <Icon name="chevronDown" size={13} />
                        </button>
                        <button className="btn-icon basket-mini" onClick={() => spec.remove(it.code)} aria-label={`Remove ${it.code}`}>
                          <Icon name="x" size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </section>

          <section className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title">Generated clause text</h2>
                <span className="xs faint">Ready to paste into the tender document</span>
              </div>
              <CopyButton text={clause} label="Copy clause" />
            </div>
            <div className="card-body">
              <blockquote className="clause clause-lg">{clause}</blockquote>
            </div>
          </section>

          {certs.length > 0 && (
            <section className="card card-flush">
              <div className="card-head">
                <div className="row" style={{ gap: 'var(--s2)' }}>
                  <Icon name="shield" size={15} />
                  <h2 className="card-title">Certification clauses</h2>
                </div>
                <span className="badge badge-accent">{certs.length} mandatory</span>
              </div>
              <div className="stack" style={{ padding: 'var(--s4)', gap: 'var(--s4)' }}>
                {certs.map(({ code, rec }) => {
                  // Built from what the engine actually confirmed, naming the
                  // governing order where one was recorded. No order is
                  // invented when the record does not carry one.
                  const clauseText = certClause(rec);
                  return (
                    <div key={code} className="stack stack-3">
                      <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
                        <div className="row wrap" style={{ gap: 6 }}>
                          <span className="mono small strong">{code}</span>
                          <span className="badge badge-accent">{rec.scheme}</span>
                        </div>
                        <CopyButton text={clauseText} label="Copy" />
                      </div>
                      <blockquote className="clause">{clauseText}</blockquote>
                      {rec.gazette && (
                        <span className="xs faint">Gazette: {rec.gazette}</span>
                      )}
                      <Link to={`/app/standard/${encodeURIComponent(code)}`} className="xs build-link" style={{ textDecoration: 'underline' }}>
                        View the standard
                      </Link>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {unverified.length > 0 && (
            <div className="notice notice-warn" role="note">
              <Icon name="alert" size={15} />
              <div className="stack stack-2">
                <span className="small strong">
                  Check certification for {unverified.length} standard{unverified.length === 1 ? '' : 's'} before issuing
                </span>
                {unverified.map((i) => (
                  <span key={i.code} className="xs">
                    <strong className="mono">{i.code}</strong>: {certInfo[i.code].explanation}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ---------------- Right: export & freeze ---------------- */}
        <div className="stack stack-4">
          <div className="card stack stack-4">
            <span className="eyebrow">Export</span>
            {!canExport && (
              <div className="notice notice-crit">
                <Icon name="alert" size={14} />
                <span className="xs">Resolve the critical gap before exporting.</span>
              </div>
            )}
            <div className="stack stack-2">
              {EXPORTS.map((e) => (
                <button
                  key={e.id}
                  className="export-row"
                  disabled={!canExport}
                  onClick={() => runExport(e.id)}
                >
                  <Icon name={e.icon} size={15} />
                  <span className="stack stack-2 grow" style={{ textAlign: 'left' }}>
                    <span className="small strong">{e.label}</span>
                    <span className="xs faint">{e.hint}</span>
                  </span>
                  <Icon name="chevronRight" size={13} />
                </button>
              ))}
            </div>
            {exported && (
              <div className={`notice ${exported.ok ? 'notice-ok' : 'notice-crit'} fade-in`} role="status">
                <Icon name={exported.ok ? 'check' : 'alert'} size={14} />
                <span className="xs">{exported.text}</span>
              </div>
            )}
          </div>

          <div className="card stack stack-4">
            <span className="eyebrow">Audit record</span>
            {frozen ? (
              <div className="stack stack-3">
                <div className="notice notice-ok">
                  <Icon name="shield" size={14} />
                  <span className="xs">Recommendation frozen.</span>
                </div>
                <div className="sunk stack stack-2">
                  <span className="xs faint">Frozen at</span>
                  <span className="mono xs">
                    {new Date(frozen.at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
                  </span>
                </div>
                <p className="xs muted">
                  This records the standard editions that were current at the time of drafting. If a
                  standard is revised later, the frozen record shows what was correct when the tender
                  was written.
                </p>
              </div>
            ) : (
              <div className="stack stack-3">
                <p className="xs muted">
                  Freezing stamps the current edition and amendment state of every collected
                  standard. If one is revised next month, there is a defensible record of what was
                  current when this tender was drafted.
                </p>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={!canExport}
                  onClick={() => spec.freeze('Tender draft')}
                >
                  <Icon name="shield" size={14} />
                  Freeze now
                </button>
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
