import { useState, useEffect, useRef, useMemo } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { AddButton } from '../components/SpecBasket';
import ParsedChips from '../components/ParsedChips';
import { useSpec } from '../state/SpecStore';
import { RECOMMENDATIONS, PIPELINE_STAGES } from '../data/mock';
import {
  BANDS, bandFor, PARSED_ATTRS, STD_TYPES, BIS_DIVISIONS,
  STANDARD_DETAIL, CONFLICTS, CERTIFICATION, DISMISS_REASONS, LANG_SAMPLES,
} from '../data/catalogue';
import './query.css';

const EXAMPLES = [
  'PVC insulated copper cable 1100V',
  'OPC 43 grade cement',
  'MS structural steel angle 50x50x6',
  'Industrial safety helmet',
];

const ROLE_OF = { r1: 'primary', r2: 'primary', r3: 'test', r4: 'primary' };
const TYPE_OF = { r1: 'product', r2: 'product', r3: 'test', r4: 'product' };

export default function Query() {
  const spec = useSpec();
  const [text, setText] = useState('');
  const [phase, setPhase] = useState('idle');   // idle | running | done | orphan
  const [stage, setStage] = useState(0);
  const [attrs, setAttrs] = useState(PARSED_ATTRS);
  const [dismissing, setDismissing] = useState(null);
  const [lang, setLang] = useState('en');
  const [interpreted, setInterpreted] = useState(null);
  const [typeFilter, setTypeFilter] = useState([]);
  const [mandatoryOnly, setMandatoryOnly] = useState(false);
  const [division, setDivision] = useState('');
  const [showConflict, setShowConflict] = useState(false);
  const timers = useRef([]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const run = (e, override) => {
    e?.preventDefault();
    const q = override ?? text;
    if (!q.trim()) return;

    timers.current.forEach(clearTimeout);
    timers.current = [];
    setPhase('running');
    setStage(0);

    PIPELINE_STAGES.forEach((_, i) => {
      timers.current.push(setTimeout(() => setStage(i + 1), (i + 1) * 340));
    });
    timers.current.push(setTimeout(() => {
      setPhase(q.trim().split(/\s+/).length < 3 ? 'orphan' : 'done');
    }, PIPELINE_STAGES.length * 340 + 240));
  };

  const applyExample = (ex) => { setText(ex); run(null, ex); };

  const applyLangSample = (key) => {
    const s = LANG_SAMPLES[key];
    setLang(key);
    setText(s.raw);
    setInterpreted(s);
    run(null, s.english);
  };

  const dismissed = spec.dismissed;

  const visible = useMemo(() => {
    return RECOMMENDATIONS.filter((r) => {
      if (dismissed[r.code]) return false;
      if (typeFilter.length && !typeFilter.includes(TYPE_OF[r.id])) return false;
      if (mandatoryOnly && !CERTIFICATION[r.code]?.mandatory) return false;
      if (division) {
        // Match on the division prefix, e.g. "Electrotechnical (ETD)" vs "… (ETD 09)"
        const d = STANDARD_DETAIL[r.code]?.division || '';
        const code = division.match(/\(([A-Z]+)\)/)?.[1];
        if (code && !d.includes(code)) return false;
      }
      return true;
    });
  }, [dismissed, typeFilter, mandatoryOnly, division]);

  const strong = visible.filter((r) => r.confidence >= 0.6);
  const weak = visible.filter((r) => r.confidence < 0.6);
  const conflict = CONFLICTS[0];

  const toggleType = (id) =>
    setTypeFilter((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const reset = () => { setPhase('idle'); setText(''); setInterpreted(null); setStage(0); };

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">New query</h1>
          <p className="page-sub">
            Type a product name, paste specification text, or drop a tender, BOQ or spec file.
            Results are assembled into a spec, not just listed.
          </p>
        </div>
        {phase !== 'idle' && (
          <button className="btn btn-secondary" onClick={reset}>
            <Icon name="plus" size={15} /> New query
          </button>
        )}
      </div>

      <div className="stack stack-5">
        {/* ---------------- Input ---------------- */}
        <form className="card stack stack-4" onSubmit={run}>
          <div className="field">
            <label className="label sr-only" htmlFor="spec">Product description or specification text</label>
            <textarea
              id="spec"
              className="textarea"
              style={{ minHeight: 88 }}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. PVC insulated copper cable, single core, 1100 V, indoor panel wiring"
              disabled={phase === 'running'}
            />
          </div>

          {phase === 'idle' && (
            <div className="stack stack-3">
              <span className="xs faint">Try an example</span>
              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                {EXAMPLES.map((ex) => (
                  <button key={ex} type="button" className="example-chip" onClick={() => applyExample(ex)}>
                    {ex}
                  </button>
                ))}
                <button type="button" className="example-chip" onClick={() => applyLangSample('hi')}>
                  <Icon name="mic" size={12} /> वायरिंग के लिए तांबे का तार
                </button>
              </div>
            </div>
          )}

          <div className="row wrap" style={{ gap: 'var(--s3)' }}>
            <div className="field grow" style={{ minWidth: 150 }}>
              <label className="label xs" htmlFor="q-lang">Language</label>
              <select id="q-lang" className="select" value={lang} onChange={(e) => setLang(e.target.value)}>
                <option value="en">Auto-detect / English</option>
                <option value="hi">हिन्दी (Hindi)</option>
                <option value="ta">தமிழ் (Tamil)</option>
                <option value="bn">বাংলা (Bengali)</option>
              </select>
            </div>
            <div className="field grow" style={{ minWidth: 150 }}>
              <label className="label xs" htmlFor="q-dept">Department</label>
              <select id="q-dept" className="select" defaultValue="">
                <option value="">Any</option>
                <option>Electrical Wing</option>
                <option>Civil Works</option>
                <option>Mechanical</option>
                <option>Stores &amp; Supply</option>
              </select>
            </div>
            <div className="field grow" style={{ minWidth: 150 }}>
              <label className="label xs" htmlFor="q-sector">Sector</label>
              <select id="q-sector" className="select" defaultValue="">
                <option value="">Any</option>
                <option>Civil</option><option>Electrical</option><option>Food</option>
                <option>Textiles</option><option>IT</option>
              </select>
            </div>
          </div>

          <hr className="divider" />

          <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
            <div className="row" style={{ gap: 'var(--s2)' }}>
              <Link to="/app/boq" className="btn btn-secondary btn-sm">
                <Icon name="upload" size={14} /> Upload tender / BOQ
              </Link>
              <button type="button" className="btn btn-secondary btn-sm">
                <Icon name="mic" size={14} /> Voice
              </button>
            </div>
            <button className="btn btn-primary" type="submit" disabled={!text.trim() || phase === 'running'}>
              {phase === 'running' ? <><span className="spinner" /> Analysing</> : <>Find standards <Icon name="arrowRight" size={15} /></>}
            </button>
          </div>
        </form>

        {/* ---------------- Pipeline ---------------- */}
        {phase === 'running' && (
          <div className="card stack stack-4 fade-in" aria-live="polite">
            <span className="eyebrow">Analysing</span>
            <ol className="pipeline">
              {PIPELINE_STAGES.map((s, i) => {
                const state = i < stage ? 'done' : i === stage ? 'active' : 'idle';
                return (
                  <li key={s.id} className={`pipe-step is-${state}`}>
                    <span className="pipe-mark">
                      {state === 'done' ? <Icon name="check" size={12} />
                        : state === 'active' ? <span className="spinner" style={{ width: 11, height: 11 }} />
                        : <span className="pipe-dot" />}
                    </span>
                    <span className="small">{s.label}</span>
                  </li>
                );
              })}
            </ol>
          </div>
        )}

        {/* ---------------- Orphan ---------------- */}
        {phase === 'orphan' && (
          <div className="card fade-in">
            <EmptyState
              icon="alert"
              title="No confident match found"
              body="No candidate cleared the confidence threshold. Rather than return a weak recommendation, this has been flagged as a possible gap in the standards landscape. Nearest categories are offered below as a starting point — they are not recommendations."
              action={
                <div className="stack stack-4" style={{ alignItems: 'center' }}>
                  <div className="row wrap" style={{ justifyContent: 'center', gap: 'var(--s2)' }}>
                    {['Electrical cables', 'Fasteners & brackets', 'Structural steel'].map((c) => (
                      <button key={c} className="example-chip" onClick={() => applyExample(c)}>{c}</button>
                    ))}
                  </div>
                  <div className="row" style={{ gap: 'var(--s2)' }}>
                    <button className="btn btn-primary btn-sm">Report as standards gap</button>
                    <Link to="/app/catalogue" className="btn btn-secondary btn-sm">Search catalogue manually</Link>
                  </div>
                </div>
              }
            />
          </div>
        )}

        {/* ---------------- Results: three columns ---------------- */}
        {phase === 'done' && (
          <div className="rec-layout fade-in">
            {/* LEFT: what the system understood */}
            <aside className="rec-col-left stack stack-4">
              {interpreted && (
                <div className="card stack stack-3">
                  <span className="eyebrow">Interpreted query</span>
                  <div className="stack stack-2">
                    <span className="xs faint">{interpreted.detected} input</span>
                    <span className="small">{interpreted.raw}</span>
                  </div>
                  <hr className="divider" />
                  <div className="stack stack-2">
                    <span className="xs faint">Understood as</span>
                    <span className="small strong">{interpreted.english}</span>
                  </div>
                  <p className="xs muted">Confirm this is right before relying on the results.</p>
                </div>
              )}

              <div className="card">
                <ParsedChips attrs={attrs} onChange={setAttrs} onRerun={() => run(null, text || 'rerun')} />
              </div>

              <div className="card stack stack-3">
                <span className="eyebrow">Filters</span>

                <fieldset className="stack stack-2" style={{ border: 0, padding: 0, margin: 0 }}>
                  <legend className="xs faint" style={{ marginBottom: 4 }}>Standard type</legend>
                  {STD_TYPES.map((t) => (
                    <label key={t.id} className="check">
                      <input
                        type="checkbox"
                        checked={typeFilter.includes(t.id)}
                        onChange={() => toggleType(t.id)}
                      />
                      <span className="xs">{t.label}</span>
                    </label>
                  ))}
                </fieldset>

                <hr className="divider" />

                <div className="field">
                  <label className="label xs" htmlFor="f-div">BIS division</label>
                  <select id="f-div" className="select" value={division} onChange={(e) => setDivision(e.target.value)}>
                    <option value="">All divisions</option>
                    {BIS_DIVISIONS.map((d) => <option key={d}>{d}</option>)}
                  </select>
                </div>

                <label className="check">
                  <input type="checkbox" checked={mandatoryOnly} onChange={() => setMandatoryOnly((v) => !v)} />
                  <span className="xs">Mandatory certification only</span>
                </label>

                {(typeFilter.length || mandatoryOnly || division) && (
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => { setTypeFilter([]); setMandatoryOnly(false); setDivision(''); }}
                  >
                    Clear filters
                  </button>
                )}
              </div>

              {Object.keys(dismissed).length > 0 && (
                <div className="card stack stack-3">
                  <span className="eyebrow">Dismissed</span>
                  {Object.entries(dismissed).map(([code, reason]) => (
                    <div key={code} className="stack stack-2">
                      <div className="row-between">
                        <span className="mono xs strong">{code}</span>
                        <button className="btn btn-ghost btn-sm" onClick={() => spec.undismiss(code)}>Undo</button>
                      </div>
                      <span className="xs faint">{reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </aside>

            {/* CENTRE: ranked cards */}
            <div className="rec-col-main stack stack-4">
              <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
                <div className="row" style={{ gap: 'var(--s2)' }}>
                  <h2 style={{ fontSize: 'var(--fs-md)' }}>Recommended standards</h2>
                  <span className="badge badge-neutral">{strong.length}</span>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={() => setShowConflict((v) => !v)}>
                  <Icon name="alert" size={13} />
                  {showConflict ? 'Hide' : 'Show'} scope conflict
                </button>
              </div>

              {showConflict && conflict && (
                <section className="card stack stack-3 fade-in">
                  <div className="row" style={{ gap: 'var(--s2)' }}>
                    <Icon name="alert" size={15} style={{ color: 'var(--warn)' }} />
                    <span className="small strong">Overlapping scope</span>
                  </div>
                  <p className="xs muted">{conflict.overlap}</p>
                  <div className="conflict-grid">
                    {[conflict.a, conflict.b].map((c) => {
                      const isAuth = c === conflict.authoritative;
                      const det = STANDARD_DETAIL[c];
                      return (
                        <div key={c} className={`conflict-col ${isAuth ? 'is-authoritative' : ''}`}>
                          <div className="row wrap" style={{ gap: 6 }}>
                            <span className="mono small strong">{c}</span>
                            {isAuth && <span className="badge badge-ok"><Icon name="check" size={11} />Authoritative here</span>}
                          </div>
                          <span className="xs muted">{det?.title}</span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="stack stack-2">
                    <span className="xs strong">Difference</span>
                    <span className="xs muted">{conflict.difference}</span>
                  </div>
                  <div className="notice notice-info">
                    <Icon name="info" size={14} />
                    <span className="xs">{conflict.when}</span>
                  </div>
                </section>
              )}

              {strong.length === 0 ? (
                <div className="card">
                  <EmptyState icon="filter" title="Nothing matches these filters" body="Clear a filter to see the full result set." />
                </div>
              ) : strong.map((r) => {
                const band = BANDS[bandFor(r.confidence)];
                const det = STANDARD_DETAIL[r.code];
                const cert = CERTIFICATION[r.code];
                const item = {
                  code: r.code, title: r.title, role: ROLE_OF[r.id] || 'primary',
                  version: r.version, amendment: r.amendment, addedFrom: 'recommendations',
                };

                return (
                  <article key={r.id} className="card card-flush rec">
                    <div className="rec-head">
                      <div className="stack stack-3 grow" style={{ minWidth: 0 }}>
                        <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                          <Link to={`/app/standard/${encodeURIComponent(r.code)}`} className="mono strong build-link" style={{ fontSize: 'var(--fs-md)' }}>
                            {r.code}
                          </Link>
                          <span className={`badge ${band.cls}`} title={band.hint}>{band.label}</span>
                          {r.version === 'superseded'
                            ? <span className="badge badge-crit"><Icon name="alert" size={11} />Superseded</span>
                            : <span className="badge badge-ok"><Icon name="check" size={11} />Current</span>}
                          {cert?.mandatory && <span className="badge badge-accent"><Icon name="shield" size={11} />Certification</span>}
                        </div>
                        <p className="small" style={{ color: 'var(--ink-soft)' }}>{r.title}</p>
                        <p className="xs muted">{r.why}</p>
                        <div className="row wrap" style={{ gap: 5 }}>
                          {r.matched.map((m) => <span key={m} className="badge badge-neutral mono">{m}</span>)}
                        </div>
                      </div>
                    </div>

                    <div className="rec-foot">
                      <div className="row" style={{ gap: 'var(--s3)' }}>
                        <Link to={`/app/standard/${encodeURIComponent(r.code)}`} className="btn btn-ghost btn-sm">
                          Open detail <Icon name="chevronRight" size={13} />
                        </Link>
                        {det?.normative?.length > 0 && (
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => spec.addMany([
                              item,
                              ...det.normative.map((n) => ({ code: n.code, title: n.title, role: n.role, version: 'latest', addedFrom: `ref of ${r.code}` })),
                            ])}
                          >
                            + with references
                          </button>
                        )}
                      </div>
                      <div className="row" style={{ gap: 'var(--s2)' }}>
                        <button className="btn btn-secondary btn-sm" onClick={() => setDismissing(r.code)}>
                          Dismiss
                        </button>
                        <AddButton item={item} />
                      </div>
                    </div>

                    {dismissing === r.code && (
                      <div className="dismiss-panel fade-in">
                        <span className="xs strong">Why are you dismissing this?</span>
                        <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                          {DISMISS_REASONS.map((reason) => (
                            <button
                              key={reason}
                              className="example-chip"
                              onClick={() => { spec.dismiss(r.code, reason); setDismissing(null); }}
                            >
                              {reason}
                            </button>
                          ))}
                        </div>
                        <button className="btn btn-ghost btn-sm" onClick={() => setDismissing(null)}>Cancel</button>
                      </div>
                    )}
                  </article>
                );
              })}

              {weak.length > 0 && (
                <div className="card stack stack-3">
                  <div className="stack stack-2">
                    <span className="eyebrow">Below threshold</span>
                    <p className="xs muted">
                      Shown for reference only. These are <strong>not</strong> recommendations.
                    </p>
                  </div>
                  {weak.map((r) => (
                    <div key={r.id} className="weak-row">
                      <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                        <div className="row wrap" style={{ gap: 6 }}>
                          <span className="mono small strong">{r.code}</span>
                          <span className="badge badge-neutral">{BANDS.review.label}</span>
                          {r.version === 'superseded' && <span className="badge badge-crit">Superseded</span>}
                        </div>
                        <span className="xs muted">{r.why}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
