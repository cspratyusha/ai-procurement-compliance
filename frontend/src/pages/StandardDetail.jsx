import { useParams, Link, useNavigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { AddButton } from '../components/SpecBasket';
import { useSpec } from '../state/SpecStore';
import { STANDARD_DETAIL, STATUS_BADGE, CERTIFICATION, CONFLICTS } from '../data/catalogue';
import './detail.css';

export default function StandardDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const spec = useSpec();
  const d = STANDARD_DETAIL[decodeURIComponent(code)];

  if (!d) {
    return (
      <div className="container page">
        <div className="card">
          <EmptyState
            icon="search"
            title="Standard not in the local catalogue"
            body={`No detail record for ${decodeURIComponent(code)} in this demo dataset. In the deployed system this loads from the PostgreSQL catalogue.`}
            action={<Link to="/app/catalogue" className="btn btn-secondary btn-sm">Browse catalogue</Link>}
          />
        </div>
      </div>
    );
  }

  const status = STATUS_BADGE[d.status];
  const cert = CERTIFICATION[d.code];
  const conflict = CONFLICTS.find((c) => c.a === d.code || c.b === d.code);

  const addWithRefs = () => {
    spec.addMany([
      { code: d.code, title: d.title, role: d.role, version: d.status === 'superseded' ? 'superseded' : 'latest', amendment: d.amendment, addedFrom: 'detail page' },
      ...d.normative.map((n) => ({ code: n.code, title: n.title, role: n.role, version: 'latest', addedFrom: `normative ref of ${d.code}` })),
    ]);
  };

  return (
    <div className="container page">
      <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)} style={{ marginBottom: 'var(--s4)' }}>
        <Icon name="chevronLeft" size={14} /> Back
      </button>

      <div className="page-head">
        <div className="stack stack-3" style={{ minWidth: 0 }}>
          <div className="row wrap" style={{ gap: 'var(--s2)' }}>
            <h1 className="mono" style={{ fontSize: 'var(--fs-lg)', fontWeight: 600 }}>{d.code}</h1>
            <span className={`badge ${status.cls}`}><Icon name={status.icon} size={12} />{status.label}</span>
            {d.amendment && <span className="badge badge-neutral">{d.amendment}</span>}
            {cert?.mandatory && <span className="badge badge-accent"><Icon name="shield" size={12} />Certification required</span>}
          </div>
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--ink-soft)', maxWidth: '62ch' }}>{d.title}</p>
          <span className="xs faint">{d.edition} · {d.division}</span>
        </div>

        <div className="row" style={{ gap: 'var(--s2)' }}>
          <a href={d.bisUrl} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
            <Icon name="external" size={15} /> BIS record
          </a>
          <AddButton
            item={{ code: d.code, title: d.title, role: d.role, version: d.status === 'superseded' ? 'superseded' : 'latest', amendment: d.amendment, addedFrom: 'detail page' }}
            size="md"
          />
        </div>
      </div>

      <div className="grid split" style={{ "--rail": "320px" }}>
        <div className="stack stack-4">
          {conflict && (
            <div className="notice notice-warn">
              <Icon name="alert" size={15} />
              <div className="stack stack-2">
                <span className="xs strong">Overlapping scope with {conflict.a === d.code ? conflict.b : conflict.a}</span>
                <span className="xs">{conflict.difference}</span>
                <Link to="/app/query" className="xs" style={{ textDecoration: 'underline' }}>Compare side by side</Link>
              </div>
            </div>
          )}

          {/* ---- Version timeline ---- */}
          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Version history</h2>
              <span className="xs faint">Superseded editions greyed</span>
            </div>
            <div className="card-body">
              <ol className="timeline">
                {d.timeline.map((t, i) => (
                  <li key={i} className={`tl-node is-${t.state}`}>
                    <span className="tl-dot" />
                    <span className="stack stack-2">
                      <span className="mono xs strong">{t.ed}</span>
                      <span className="xs faint">{t.year}</span>
                    </span>
                  </li>
                ))}
              </ol>
              <div className="row wrap" style={{ gap: 'var(--s4)', marginTop: 'var(--s4)' }}>
                {[['current', 'Current'], ['amendment', 'Amendment'], ['superseded', 'Superseded'], ['revision', 'Under revision']].map(([k, label]) => (
                  <span key={k} className="legend-item">
                    <span className={`tl-dot tl-legend is-${k}`} />
                    <span className="xs faint">{label}</span>
                  </span>
                ))}
              </div>
            </div>
          </section>

          {/* ---- Scope ---- */}
          <section className="card stack stack-4">
            <span className="eyebrow">Scope — plain language</span>
            <p className="small" style={{ color: 'var(--ink-soft)' }}>{d.scopePlain}</p>
            <details className="scope-official">
              <summary className="xs muted">Show official scope text</summary>
              <blockquote className="clause" style={{ marginTop: 'var(--s3)' }}>{d.scopeOfficial}</blockquote>
            </details>
          </section>

          {/* ---- References ---- */}
          <div className="grid grid-2" style={{ alignItems: 'start' }}>
            <section className="card card-flush">
              <div className="card-head">
                <div className="stack stack-2">
                  <h2 className="card-title">Normative references</h2>
                  <span className="xs faint">What this standard depends on</span>
                </div>
              </div>
              <div className="stack" style={{ padding: 'var(--s3)' }}>
                {d.normative.length === 0 ? (
                  <p className="xs faint" style={{ padding: 'var(--s3)' }}>None recorded.</p>
                ) : (
                  d.normative.map((n) => (
                    <Link key={n.code} to={`/app/standard/${encodeURIComponent(n.code)}`} className="ref-row">
                      <Icon name="chevronRight" size={13} />
                      <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                        <span className="mono xs strong">{n.code}</span>
                        <span className="xs faint">{n.title}</span>
                      </span>
                    </Link>
                  ))
                )}
              </div>
              {d.normative.length > 0 && (
                <div className="card-body" style={{ borderTop: '1px solid var(--line)' }}>
                  <button className="btn btn-secondary btn-sm" style={{ width: '100%' }} onClick={addWithRefs}>
                    <Icon name="plus" size={14} />
                    Add this standard and its references
                  </button>
                </div>
              )}
            </section>

            <section className="card card-flush">
              <div className="card-head">
                <div className="stack stack-2">
                  <h2 className="card-title">Reverse references</h2>
                  <span className="xs faint">What depends on this</span>
                </div>
              </div>
              <div className="stack" style={{ padding: 'var(--s3)' }}>
                {d.reverse.length === 0 ? (
                  <p className="xs faint" style={{ padding: 'var(--s3)' }}>Nothing in the catalogue cites this standard.</p>
                ) : (
                  d.reverse.map((n) => (
                    <Link key={n.code} to={`/app/standard/${encodeURIComponent(n.code)}`} className="ref-row">
                      <Icon name="chevronRight" size={13} />
                      <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                        <span className="mono xs strong">{n.code}</span>
                        <span className="xs faint">{n.title}</span>
                      </span>
                    </Link>
                  ))
                )}
              </div>
            </section>
          </div>
        </div>

        {/* ---- Right column ---- */}
        <div className="stack stack-4">
          <div className="card stack stack-3">
            <span className="eyebrow">Catalogue record</span>
            {[
              ['Status', status.label],
              ['Edition', d.edition],
              ['Latest amendment', d.amendment || 'None'],
              ['BIS division', d.division],
              ['Committee', d.committee],
            ].map(([k, v]) => (
              <div key={k} className="stack stack-2">
                <span className="xs faint">{k}</span>
                <span className="small">{v}</span>
              </div>
            ))}
          </div>

          <div className="card stack stack-3">
            <span className="eyebrow">Certification</span>
            {cert?.mandatory ? (
              <>
                <div className="notice notice-warn">
                  <Icon name="shield" size={14} />
                  <span className="xs strong">Mandatory certification applies</span>
                </div>
                <div className="stack stack-2">
                  <span className="xs faint">Scheme</span>
                  <span className="small">{cert.scheme}</span>
                </div>
                <Link to={`/app/certification/${encodeURIComponent(d.code)}`} className="btn btn-secondary btn-sm">
                  View requirement and clause
                </Link>
              </>
            ) : (
              <p className="xs muted">
                {cert?.note || 'No mandatory product certification scheme attaches to this standard.'}
              </p>
            )}
          </div>

          <Link to="/app/map" className="card card-link stack stack-3">
            <span style={{ color: 'var(--ink-soft)' }}><Icon name="graph" size={18} /></span>
            <span className="small strong">Open in related-standards map</span>
            <span className="xs muted">See the full cluster around this standard and add a whole branch at once.</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
