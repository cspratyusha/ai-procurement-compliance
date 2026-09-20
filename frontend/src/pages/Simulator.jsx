import { useState, useMemo } from 'react';
import Icon from '../components/Icon';
import { SIM_PARAMS, SIM_DELTAS, RECOMMENDATIONS } from '../data/mock';
import './simulator.css';
import DemoDataNotice from '../components/DemoDataNotice';

const BASE = RECOMMENDATIONS.filter((r) => r.confidence >= 0.6).map((r) => r.code);

export default function Simulator() {
  const [params, setParams] = useState(
    Object.fromEntries(SIM_PARAMS.map((p) => [p.id, p.value]))
  );

  const defaults = useMemo(
    () => Object.fromEntries(SIM_PARAMS.map((p) => [p.id, p.value])),
    []
  );

  const changed = SIM_PARAMS.filter((p) => params[p.id] !== defaults[p.id]);

  // Merge the delta sets for every non-default parameter value.
  const delta = useMemo(() => {
    const out = { added: [], changed: [], removed: [] };
    changed.forEach((p) => {
      const d = SIM_DELTAS[params[p.id]];
      if (!d) return;
      ['added', 'changed', 'removed'].forEach((k) => {
        d[k].forEach((item) => {
          if (!out[k].some((x) => x.code === item.code)) out[k].push(item);
        });
      });
    });
    return out;
  }, [params, changed]);

  const hasDelta = delta.added.length || delta.changed.length || delta.removed.length;
  const reset = () => setParams(defaults);

  const resulting = useMemo(() => {
    const removed = new Set(delta.removed.map((r) => r.code));
    return [...BASE.filter((c) => !removed.has(c)), ...delta.added.map((a) => a.code)];
  }, [delta]);

  return (
    <div className="container page">
      <DemoDataNotice
        what="Impact figures and cost deltas are illustrative."
        next="Nothing here is computed from real procurement data."
      />
      <div className="page-head">
        <div>
          <h1 className="page-title">Scenario simulator</h1>
          <p className="page-sub">
            Adjust a use-case parameter and watch the standards cluster change. The point is to show
            <em> why</em> specifications differ across use-cases — not just hand over an answer.
          </p>
        </div>
        {changed.length > 0 && (
          <button className="btn btn-secondary" onClick={reset}>
            <Icon name="refresh" size={15} />
            Reset to base
          </button>
        )}
      </div>

      <div className="grid split split-left" style={{ "--rail": "320px" }}>
        {/* ---- Controls ---- */}
        <div className="card stack stack-5">
          <div className="stack stack-2">
            <span className="eyebrow">Base query</span>
            <p className="xs muted mono" style={{ lineHeight: 1.55 }}>
              PVC insulated copper cable, single core, 1100 V, indoor panel wiring
            </p>
          </div>

          <hr className="divider" />

          {SIM_PARAMS.map((p) => (
            <div key={p.id} className="field">
              <label className="label" htmlFor={p.id}>
                {p.label}
                {params[p.id] !== defaults[p.id] && (
                  <span className="badge badge-accent" style={{ marginLeft: 'var(--s2)' }}>changed</span>
                )}
              </label>
              <select
                id={p.id}
                className="select"
                value={params[p.id]}
                onChange={(e) => setParams((prev) => ({ ...prev, [p.id]: e.target.value }))}
              >
                {p.options.map((o) => <option key={o}>{o}</option>)}
              </select>
            </div>
          ))}
        </div>

        {/* ---- Delta view ---- */}
        <div className="stack stack-4">
          {!hasDelta ? (
            <div className="card">
              <div className="empty">
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 'var(--s4)', color: 'var(--ink-faint)' }}>
                  <Icon name="sliders" size={28} strokeWidth={1.4} />
                </div>
                <p className="empty-title">Base cluster unchanged</p>
                <p className="small" style={{ maxWidth: '44ch', margin: '0 auto' }}>
                  Change a parameter on the left — try <strong>Marine</strong> environment or
                  <strong> 11 kV</strong> voltage class — to see which standards enter, leave, or
                  change requirement.
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="notice notice-info">
                <Icon name="info" size={15} />
                <span className="xs">
                  {changed.length} parameter{changed.length === 1 ? '' : 's'} changed:{' '}
                  {changed.map((p) => `${p.label} → ${params[p.id]}`).join(' · ')}
                </span>
              </div>

              {delta.added.length > 0 && (
                <DeltaGroup
                  kind="added"
                  icon="plus"
                  title="Standards added"
                  items={delta.added}
                />
              )}
              {delta.changed.length > 0 && (
                <DeltaGroup
                  kind="changed"
                  icon="refresh"
                  title="Requirements changed"
                  items={delta.changed}
                />
              )}
              {delta.removed.length > 0 && (
                <DeltaGroup
                  kind="removed"
                  icon="minus"
                  title="No longer applicable"
                  items={delta.removed}
                />
              )}
            </>
          )}

          <div className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Resulting cluster</h2>
              <span className="badge badge-neutral">{resulting.length} standards</span>
            </div>
            <div className="card-body">
              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                {resulting.map((code) => {
                  const isNew = delta.added.some((a) => a.code === code);
                  return (
                    <span
                      key={code}
                      className={`badge ${isNew ? 'badge-ok' : 'badge-neutral'} mono`}
                    >
                      {isNew && <Icon name="plus" size={11} />}
                      {code}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DeltaGroup({ kind, icon, title, items }) {
  return (
    <div className={`card card-flush delta delta-${kind}`}>
      <div className="card-head">
        <div className="row" style={{ gap: 'var(--s2)' }}>
          <Icon name={icon} size={15} />
          <h2 className="card-title">{title}</h2>
        </div>
        <span className="badge badge-neutral tabular">{items.length}</span>
      </div>
      <div className="stack" style={{ padding: 'var(--s2)' }}>
        {items.map((i) => (
          <div key={i.code} className="delta-row">
            <span className="mono small strong nowrap">{i.code}</span>
            <span className="xs muted">{i.reason}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
