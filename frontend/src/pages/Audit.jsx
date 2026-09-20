import { useState, useRef, useEffect } from 'react';
import Icon from '../components/Icon';
import { SeverityBadge, EmptyState } from '../components/Primitives';
import { AUDIT_FINDINGS, SEVERITY } from '../data/mock';
import './audit.css';
import DemoDataNotice from '../components/DemoDataNotice';

export default function Audit() {
  const [phase, setPhase] = useState('idle');   // idle | parsing | done
  const [view, setView] = useState('redline');  // redline | list
  const [applied, setApplied] = useState({});
  const [open, setOpen] = useState({ f1: true });
  const [filter, setFilter] = useState('all');
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const upload = () => {
    setPhase('parsing');
    timer.current = setTimeout(() => setPhase('done'), 1800);
  };

  const counts = {
    critical: AUDIT_FINDINGS.filter((f) => f.severity === 'critical').length,
    minor: AUDIT_FINDINGS.filter((f) => f.severity === 'minor').length,
    info: AUDIT_FINDINGS.filter((f) => f.severity === 'info').length,
  };

  const shown = filter === 'all' ? AUDIT_FINDINGS : AUDIT_FINDINGS.filter((f) => f.severity === filter);
  const appliedCount = Object.values(applied).filter(Boolean).length;

  return (
    <div className="container page">
      <DemoDataNotice
        what="The audit trail entries are sample records."
        next="Real entries would be written as officials run and accept recommendations."
      />
      <div className="page-head">
        <div>
          <h1 className="page-title">Audit tender</h1>
          <p className="page-sub">
            Upload an existing draft. The engine extracts every referenced standard, checks version
            currency and certification obligations, traverses the graph for missing companions, and
            returns a severity-tagged gap report as an inline redline.
          </p>
        </div>
        {phase === 'done' && (
          <div className="row" style={{ gap: 'var(--s2)' }}>
            <button className="btn btn-secondary" onClick={() => { setPhase('idle'); setApplied({}); }}>
              New audit
            </button>
            <button className="btn btn-primary">
              <Icon name="download" size={15} />
              Export corrected
            </button>
          </div>
        )}
      </div>

      {phase === 'idle' && (
        <div className="card">
          <div className="dropzone">
            <span className="dropzone-icon"><Icon name="upload" size={26} strokeWidth={1.4} /></span>
            <p className="strong">Drop a tender document here</p>
            <p className="small muted" style={{ maxWidth: '44ch' }}>
              PDF, DOCX or scanned document. Scanned files are processed with OCR.
              Maximum 40 MB.
            </p>
            <button className="btn btn-primary" onClick={upload} style={{ marginTop: 'var(--s3)' }}>
              Select file
            </button>
            <p className="xs faint" style={{ marginTop: 'var(--s2)' }}>
              Demo build — selecting loads a sample tender.
            </p>
          </div>
        </div>
      )}

      {phase === 'parsing' && (
        <div className="card stack stack-5 fade-in" aria-live="polite">
          <div className="row" style={{ gap: 'var(--s3)' }}>
            <Icon name="file" size={18} />
            <span className="small strong grow">Tender_HT_Cable_Supply_2026.pdf</span>
            <span className="spinner" />
          </div>
          <div className="stack stack-3">
            {['Extracting document text', 'Identifying referenced standards', 'Checking version currency', 'Traversing allied standards graph', 'Generating impact estimates'].map((s) => (
              <div key={s} className="row" style={{ gap: 'var(--s3)' }}>
                <div className="skeleton" style={{ width: 14, height: 14, borderRadius: '50%' }} />
                <span className="small muted">{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {phase === 'done' && (
        <div className="stack stack-5 fade-in">
          <div className="card stack stack-4">
            <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
              <div className="row" style={{ gap: 'var(--s3)' }}>
                <Icon name="file" size={18} />
                <div className="stack stack-2">
                  <span className="small strong">Tender_HT_Cable_Supply_2026.pdf</span>
                  <span className="xs faint">18 pages · 6 standards referenced · audited just now</span>
                </div>
              </div>
              <div className="seg" role="group" aria-label="View mode">
                <button onClick={() => setView('redline')} aria-pressed={view === 'redline'}>Redline</button>
                <button onClick={() => setView('list')} aria-pressed={view === 'list'}>Findings list</button>
              </div>
            </div>

            <hr className="divider" />

            <div className="audit-summary">
              {[
                { k: 'critical', n: counts.critical, label: 'Critical gaps' },
                { k: 'minor', n: counts.minor, label: 'Minor issues' },
                { k: 'info', n: counts.info, label: 'Informational' },
                { k: 'applied', n: appliedCount, label: 'Fixes applied' },
              ].map((c) => (
                <div key={c.k} className="summary-cell">
                  <span
                    className="tabular"
                    style={{
                      fontSize: 'var(--fs-lg)',
                      fontWeight: 600,
                      color: c.k === 'applied' ? 'var(--ok)' : SEVERITY[c.k]?.color,
                    }}
                  >
                    {c.n}
                  </span>
                  <span className="xs faint">{c.label}</span>
                </div>
              ))}
            </div>

            {counts.critical > 0 && (
              <div className="notice notice-crit">
                <Icon name="alert" size={15} />
                <span className="xs">
                  This tender cites a superseded standard and omits a mandatory certification
                  requirement. Both are enforceability risks at the inspection stage.
                </span>
              </div>
            )}
          </div>

          <div className="row wrap" style={{ gap: 'var(--s2)' }}>
            <span className="xs faint" style={{ marginRight: 'var(--s2)' }}>Filter</span>
            <div className="seg" role="group" aria-label="Filter by severity">
              {['all', 'critical', 'minor', 'info'].map((f) => (
                <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}>
                  {f === 'all' ? 'All' : SEVERITY[f].label}
                </button>
              ))}
            </div>
          </div>

          {shown.length === 0 ? (
            <div className="card">
              <EmptyState icon="checkCircle" title="Nothing at this severity" body="No findings match the selected filter." />
            </div>
          ) : view === 'redline' ? (
            <div className="stack stack-4">
              {shown.map((f) => (
                <article key={f.id} className={`card card-flush finding sev-${f.severity} ${applied[f.id] ? 'is-applied' : ''}`}>
                  <div className="finding-head">
                    <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <SeverityBadge severity={f.severity} map={SEVERITY} />
                        <span className="xs faint">{f.clauseRef}</span>
                      </div>
                      <span className="small strong">{f.finding}</span>
                    </div>
                    {applied[f.id] ? (
                      <span className="badge badge-ok"><Icon name="check" size={12} /> Applied</span>
                    ) : (
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => setApplied((p) => ({ ...p, [f.id]: true }))}
                      >
                        Apply fix
                      </button>
                    )}
                  </div>

                  <div className="redline">
                    <div className="redline-row redline-del">
                      <span className="redline-tag">−</span>
                      <span className="small">{f.original}</span>
                    </div>
                    <div className="redline-row redline-add">
                      <span className="redline-tag">+</span>
                      <span className="small">{f.revised}</span>
                    </div>
                  </div>

                  <button
                    className="expander"
                    style={{ padding: '0 var(--s5) var(--s3)' }}
                    onClick={() => setOpen((p) => ({ ...p, [f.id]: !p[f.id] }))}
                    aria-expanded={!!open[f.id]}
                  >
                    <Icon name={open[f.id] ? 'chevronDown' : 'chevronRight'} size={14} />
                    Impact estimate
                  </button>

                  {open[f.id] && (
                    <div className="finding-impact fade-in">
                      <div className="stack stack-3">
                        <div className="row wrap" style={{ gap: 'var(--s4)' }}>
                          <div className="stack stack-2">
                            <span className="xs faint">Currently cited</span>
                            <span className="mono small">{f.cited}</span>
                          </div>
                          <div className="stack stack-2">
                            <span className="xs faint">Should be</span>
                            <span className="mono small strong">{f.correct}</span>
                          </div>
                        </div>
                        <p className="small" style={{ color: 'var(--ink-soft)' }}>{f.impact}</p>
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="card card-flush scroll-x" tabIndex={0} role="region" aria-label="Audit findings">
              <table className="table table-hover">
                <caption className="sr-only">Audit findings</caption>
                <thead>
                  <tr>
                    <th scope="col">Severity</th>
                    <th scope="col">Clause</th>
                    <th scope="col">Finding</th>
                    <th scope="col">Cited</th>
                    <th scope="col">Should be</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((f) => (
                    <tr key={f.id}>
                      <td><SeverityBadge severity={f.severity} map={SEVERITY} /></td>
                      <td className="xs muted nowrap">{f.clauseRef}</td>
                      <td className="small">{f.finding}</td>
                      <td className="mono xs nowrap">{f.cited}</td>
                      <td className="mono xs strong nowrap">{f.correct}</td>
                      <td>
                        {applied[f.id] ? (
                          <span className="badge badge-ok"><Icon name="check" size={12} /> Applied</span>
                        ) : (
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => setApplied((p) => ({ ...p, [f.id]: true }))}
                          >
                            Apply
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
