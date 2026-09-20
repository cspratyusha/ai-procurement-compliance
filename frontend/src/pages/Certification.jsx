import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { CopyButton, EmptyState } from '../components/Primitives';
import { useSpec } from '../state/SpecStore';
import { CERTIFICATION, STANDARD_DETAIL } from '../data/catalogue';
import DemoDataNotice from '../components/DemoDataNotice';

const ALL = Object.entries(CERTIFICATION);

export default function Certification() {
  const { code } = useParams();
  const spec = useSpec();
  const [selected, setSelected] = useState(
    code ? decodeURIComponent(code) : ALL.find(([, r]) => r.mandatory)?.[0]
  );

  const rec = CERTIFICATION[selected];
  const detail = STANDARD_DETAIL[selected];
  const inSpec = spec.has(selected);

  return (
    <div className="container page">
      <DemoDataNotice
        what="Certification requirements shown are placeholder rules."
        next="They are not sourced from the official BIS compulsory-certification lists."
      />
      <div className="page-head">
        <div>
          <h1 className="page-title">Certification &amp; compliance</h1>
          <p className="page-sub">
            Whether a product carries a mandatory certification obligation is a legally distinct
            question from which standard describes it. This mapping is rules-based, not inferred —
            it traces to a specific Quality Control Order.
          </p>
        </div>
      </div>

      <div className="grid split split-left" style={{ "--rail": "300px" }}>
        <div className="card card-flush">
          <div className="card-head"><h2 className="card-title">Standards</h2></div>
          <div className="stack" style={{ padding: 'var(--s2)' }}>
            {ALL.map(([c, r]) => (
              <button
                key={c}
                className={`alert-mini ${selected === c ? 'is-active-row' : ''}`}
                style={{ width: '100%', textAlign: 'left' }}
                onClick={() => setSelected(c)}
                aria-pressed={selected === c}
              >
                <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                  <span className="row wrap" style={{ gap: 6 }}>
                    <span className="mono xs strong">{c}</span>
                    {r.mandatory
                      ? <span className="badge badge-accent">Mandatory</span>
                      : <span className="badge badge-neutral">Voluntary</span>}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>

        {!rec ? (
          <div className="card">
            <EmptyState icon="shield" title="Select a standard" body="Choose a standard to see its certification position." />
          </div>
        ) : !rec.mandatory ? (
          <div className="card stack stack-4">
            <div className="row wrap" style={{ gap: 'var(--s2)' }}>
              <span className="mono strong" style={{ fontSize: 'var(--fs-md)' }}>{selected}</span>
              <span className="badge badge-neutral">No mandatory scheme</span>
            </div>
            <div className="notice notice-info">
              <Icon name="info" size={15} />
              <span className="xs">{rec.note}</span>
            </div>
            <p className="xs muted">
              A voluntary position still allows a buyer to require certification contractually —
              but it cannot be enforced as a statutory obligation.
            </p>
          </div>
        ) : (
          <div className="stack stack-4">
            <div className="card stack stack-4">
              <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
                <div className="stack stack-2" style={{ minWidth: 0 }}>
                  <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                    <span className="mono strong" style={{ fontSize: 'var(--fs-md)' }}>{selected}</span>
                    <span className="badge badge-accent"><Icon name="shield" size={12} />Mandatory</span>
                  </div>
                  {detail && <span className="xs muted">{detail.title}</span>}
                </div>
                {!inSpec && detail && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => spec.add({ code: selected, title: detail.title, role: 'certification', scheme: rec.scheme, version: 'latest', addedFrom: 'certification panel' })}
                  >
                    <Icon name="plus" size={14} /> Add clause to spec
                  </button>
                )}
              </div>

              <hr className="divider" />

              <div className="grid grid-2" style={{ gap: 'var(--s4)' }}>
                {[
                  ['Scheme', rec.scheme],
                  ['Regulation', rec.schemeCode],
                  ['Statutory order', rec.order],
                  ['Notified', rec.orderDate],
                ].map(([k, v]) => (
                  <div key={k} className="stack stack-2">
                    <span className="xs faint">{k}</span>
                    <span className="small">{v}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card stack stack-4">
              <span className="eyebrow">Marking requirements</span>
              <ul className="stack stack-3" style={{ margin: 0, paddingLeft: 'var(--s5)' }}>
                {rec.marking.map((m, i) => (
                  <li key={i} className="small" style={{ color: 'var(--ink-soft)' }}>{m}</li>
                ))}
              </ul>
              <div className="notice notice-info">
                <Icon name="info" size={15} />
                <span className="xs">{rec.verify}</span>
              </div>
            </div>

            <div className="card card-flush">
              <div className="card-head">
                <div className="stack stack-2">
                  <h2 className="card-title">Copy-ready tender clause</h2>
                  <span className="xs faint">References the standard and the statutory order</span>
                </div>
                <CopyButton text={rec.clause} />
              </div>
              <div className="card-body">
                <blockquote className="clause">{rec.clause}</blockquote>
              </div>
            </div>

            {detail && (
              <Link to={`/app/standard/${encodeURIComponent(selected)}`} className="card card-link row-between">
                <span className="stack stack-2">
                  <span className="small strong">Open standard detail</span>
                  <span className="xs muted">Version history, scope and references for {selected}</span>
                </span>
                <Icon name="chevronRight" size={16} />
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
