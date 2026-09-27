import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { AddButton } from '../components/SpecBasket';
import { simulateScenario, ApiError } from '../api/client';
import './simulator.css';
import './query.css';   // .notice

/**
 * What changes if the requirement changes.
 *
 * The officer describes the item, picks the conditions of a scenario (where it
 * is installed, what it must withstand), and the engine runs the full search
 * twice: once on the description and once with the conditions added. The
 * screen shows the difference: standards that enter the top results, drop out
 * or move. Every standard shown came from a real search over the corpus, so a
 * scenario can only surface standards the catalogue actually holds.
 */

const PRESETS = [
  {
    group: 'Where it is used',
    options: [
      'installed outdoors, exposed to sun and rain',
      'marine or coastal environment, saline atmosphere',
      'buried underground',
      'in a hazardous area with flammable gas or dust',
    ],
  },
  {
    group: 'What it must withstand',
    options: [
      'high operating temperature',
      'corrosive chemicals',
      'fire: flame retardant, low smoke',
      'earthquake loads in a seismic zone',
    ],
  },
  {
    group: 'What it is for',
    options: [
      'in contact with drinking water',
      'in contact with food',
      'for use in hospitals',
      'for heavy industrial duty',
    ],
  },
];

const EXAMPLES = [
  'PVC insulated copper cable for panel wiring',
  'Ordinary Portland cement for concrete',
  'Steel pipes for water supply',
];

function shortLabel(text) {
  return text.split(',')[0];
}

export default function Simulator() {
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState([]);
  const [custom, setCustom] = useState('');
  const [phase, setPhase] = useState('idle');   // idle | running | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const conditions = [...picked, ...(custom.trim() ? [custom.trim()] : [])];
  const toggle = (c) => setPicked((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]));

  const run = async (e) => {
    e?.preventDefault();
    if (!query.trim() || conditions.length === 0) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase('running');
    setError(null);
    try {
      const data = await simulateScenario({ query: query.trim(), conditions, topK: 10, signal: controller.signal });
      setResult(data);
      setPhase('done');
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err instanceof ApiError ? err.message : 'The comparison failed.');
      setPhase('error');
    }
  };

  const reset = () => { setPicked([]); setCustom(''); setResult(null); setPhase('idle'); };
  const unchangedList = result ? result.scenario.filter((r) => r.base_rank === r.scenario_rank) : [];

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Scenario simulator</h1>
          <p className="page-sub">
            Describe an item, add the conditions of a use case, and see which standards come into
            play, drop out or change priority. Both sides are live searches over the full catalogue.
          </p>
        </div>
        {(picked.length > 0 || custom || result) && (
          <button className="btn btn-secondary" onClick={reset}>
            <Icon name="refresh" size={15} />
            Start over
          </button>
        )}
      </div>

      <div className="grid split split-left" style={{ '--rail': '340px' }}>
        <form className="card stack stack-5" onSubmit={run}>
          <div className="field">
            <label className="label" htmlFor="sim-query">Base description</label>
            <textarea id="sim-query" className="textarea" rows={3} value={query} maxLength={500}
              placeholder="What is being procured, in the words of the tender"
              onChange={(e) => setQuery(e.target.value)} required />
            <span className="row wrap" style={{ gap: 'var(--s2)' }}>
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" className="btn btn-ghost btn-sm" onClick={() => setQuery(ex)}>{ex}</button>
              ))}
            </span>
          </div>

          <hr className="divider" />

          {PRESETS.map((g) => (
            <fieldset key={g.group} className="stack stack-2" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="label" style={{ marginBottom: 'var(--s2)' }}>{g.group}</legend>
              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                {g.options.map((c) => (
                  <button key={c} type="button" className={`sim-chip ${picked.includes(c) ? 'is-on' : ''}`}
                    aria-pressed={picked.includes(c)} onClick={() => toggle(c)} title={c}>
                    {picked.includes(c) && <Icon name="check" size={12} />}
                    {shortLabel(c)}
                  </button>
                ))}
              </div>
            </fieldset>
          ))}

          <div className="field">
            <label className="label" htmlFor="sim-custom">Another condition</label>
            <input id="sim-custom" className="input" value={custom} maxLength={200}
              placeholder="e.g. rated for 11 kV" onChange={(e) => setCustom(e.target.value)} />
          </div>

          <button className="btn btn-primary" type="submit"
            disabled={phase === 'running' || !query.trim() || conditions.length === 0}>
            {phase === 'running' ? <><span className="spinner" /> Comparing</> : 'Compare'}
          </button>
          {query.trim() && conditions.length === 0 && (
            <span className="xs muted">Pick at least one condition to compare against.</span>
          )}
        </form>

        <div className="stack stack-4">
          {phase === 'error' && (
            <div className="notice notice-crit" role="alert"><Icon name="alert" size={15} /><span className="xs">{error}</span></div>
          )}

          {phase === 'running' && (
            <div className="card"><div className="empty">
              <span className="spinner" />
              <p className="small" style={{ marginTop: 'var(--s3)' }}>Running both searches…</p>
            </div></div>
          )}

          {phase !== 'running' && !result && phase !== 'error' && (
            <div className="card">
              <div className="empty">
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 'var(--s4)', color: 'var(--ink-faint)' }}>
                  <Icon name="sliders" size={28} strokeWidth={1.4} />
                </div>
                <p className="empty-title">Nothing compared yet</p>
                <p className="small" style={{ maxWidth: '46ch', margin: '0 auto' }}>
                  Describe the item, pick conditions such as <strong>marine</strong> or
                  <strong> buried underground</strong>, then compare.
                </p>
              </div>
            </div>
          )}

          {result && phase !== 'running' && (
            <>
              <div className="notice notice-info">
                <Icon name="info" size={15} />
                <span className="xs">
                  Searched <strong>{result.query}</strong>, then <strong>{result.scenario_query}</strong>.
                  {' '}Top {result.scenario.length} compared.
                  {(result.base_confidence === 'none' || result.scenario_confidence === 'none') &&
                    ' One side found no close match in the catalogue, so treat its list as nearest text matches only.'}
                </span>
              </div>

              {result.added.length === 0 && result.removed.length === 0 && result.moved.length === 0 && (
                <div className="notice notice-ok"><Icon name="checkCircle" size={15} />
                  <span className="xs">These conditions do not change the top standards for this item.</span>
                </div>
              )}

              {result.added.length > 0 && (
                <DeltaGroup kind="added" icon="plus" title="Come into play" items={result.added}
                  note={(r) => `Rank ${r.scenario_rank} with the conditions; not in the top ${result.base.length} without them.`} />
              )}
              {result.removed.length > 0 && (
                <DeltaGroup kind="removed" icon="minus" title="Drop out" items={result.removed}
                  note={(r) => `Rank ${r.base_rank} for the base description; out of the top ${result.scenario.length} with the conditions.`} />
              )}
              {result.moved.length > 0 && (
                <DeltaGroup kind="changed" icon="refresh" title="Change priority" items={result.moved}
                  note={(r) => `Rank ${r.base_rank} to ${r.scenario_rank}.`} />
              )}

              {unchangedList.length > 0 && (
                <div className="card card-flush">
                  <div className="card-head">
                    <h2 className="card-title">Unchanged</h2>
                    <span className="badge badge-neutral">{unchangedList.length}</span>
                  </div>
                  <div className="card-body row wrap" style={{ gap: 'var(--s2)' }}>
                    {unchangedList.map((r) => (
                      <Link key={r.number} className="badge badge-neutral mono" to={`/app/standard/${encodeURIComponent(r.number)}`}>
                        {r.number}
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function DeltaGroup({ kind, icon, title, items, note }) {
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
        {items.map((r) => (
          <div key={r.number} className="delta-row delta-row-actions">
            <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
              <Link to={`/app/standard/${encodeURIComponent(r.number)}`} className="mono small strong">{r.number}</Link>
              <span className="xs">{r.title}</span>
              <span className="xs muted">
                {note(r)}{r.status === 'superseded' ? ' This edition has been replaced.' : ''}
              </span>
            </span>
            {kind !== 'removed' && (
              <AddButton item={{ code: r.number, title: r.title, role: 'primary', version: r.status === 'superseded' ? 'superseded' : 'latest', addedFrom: 'Simulator' }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
