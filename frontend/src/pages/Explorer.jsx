import { useState, useMemo } from 'react';
import Icon from '../components/Icon';
import ClusterGraph from '../components/ClusterGraph';
import { VersionBadge, EmptyState } from '../components/Primitives';
import { EXPLORER_STANDARDS, GRAPH, NODE_KINDS } from '../data/mock';

const CATEGORIES = ['All categories', ...new Set(EXPLORER_STANDARDS.map((s) => s.category))];

export default function Explorer() {
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('All categories');
  const [selected, setSelected] = useState('IS 694:2010');

  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    return EXPLORER_STANDARDS.filter((s) => {
      const matchesCat = cat === 'All categories' || s.category === cat;
      const matchesTerm = !term
        || s.code.toLowerCase().includes(term)
        || s.title.toLowerCase().includes(term);
      return matchesCat && matchesTerm;
    });
  }, [q, cat]);

  const node = GRAPH.nodes.find((n) => n.id === selected);
  const related = GRAPH.edges
    .filter((e) => e.from === selected || e.to === selected)
    .map((e) => ({ id: e.from === selected ? e.to : e.from, kind: e.kind }));

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Standards explorer</h1>
          <p className="page-sub">
            Search the registry or open any standard to see its relationship graph — normative
            references, test methods, supersession chain and certification linkage.
          </p>
        </div>
      </div>

      <div className="grid split split-left" style={{ "--rail": "340px" }}>
        {/* ---- Search column ---- */}
        <div className="card card-flush">
          <div className="card-body stack stack-3">
            <div className="field">
              <label className="label sr-only" htmlFor="std-search">Search standards</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-faint)' }}>
                  <Icon name="search" size={15} />
                </span>
                <input
                  id="std-search"
                  className="input"
                  style={{ paddingLeft: 34 }}
                  placeholder="IS number or title…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
            </div>

            <div className="field">
              <label className="label sr-only" htmlFor="std-cat">Category</label>
              <select id="std-cat" className="select" value={cat} onChange={(e) => setCat(e.target.value)}>
                {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>

            <span className="xs faint">{results.length} standard{results.length === 1 ? '' : 's'}</span>
          </div>

          <hr className="divider" />

          <div className="stack" style={{ padding: 'var(--s2)', maxHeight: 520, overflowY: 'auto' }}>
            {results.length === 0 ? (
              <EmptyState icon="search" title="No matches" body="Try a different IS number, title keyword, or category." />
            ) : (
              results.map((s) => (
                <button
                  key={s.code}
                  className={`alert-mini ${selected === s.code ? 'is-active-row' : ''}`}
                  style={{ textAlign: 'left', width: '100%' }}
                  onClick={() => setSelected(s.code)}
                  aria-pressed={selected === s.code}
                >
                  <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <span className="row wrap" style={{ gap: 6 }}>
                      <span className="mono xs strong">{s.code}</span>
                      {s.version === 'superseded' && <span className="badge badge-crit">Superseded</span>}
                      {s.cert && <span className="badge badge-accent">{s.cert}</span>}
                    </span>
                    <span className="xs faint" style={{ lineHeight: 1.45 }}>{s.title}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* ---- Graph column ---- */}
        <div className="stack stack-4">
          <div className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title mono">{selected}</h2>
                <span className="xs faint">{node?.title || 'Relationship graph'}</span>
              </div>
              <button className="btn btn-secondary btn-sm">
                <Icon name="external" size={13} />
                Open record
              </button>
            </div>
            <div className="card-body">
              <ClusterGraph data={GRAPH} height={330} selected={selected} onSelect={setSelected} />
            </div>
          </div>

          <div className="grid grid-2">
            <div className="card stack stack-4">
              <span className="eyebrow">Node detail</span>
              {node ? (
                <div className="stack stack-3">
                  <div className="row-between">
                    <span className="xs faint">Type</span>
                    <span className="badge badge-neutral">{NODE_KINDS[node.kind].label}</span>
                  </div>
                  <hr className="divider" />
                  <div className="row-between">
                    <span className="xs faint">Version state</span>
                    <VersionBadge version="latest" />
                  </div>
                  <hr className="divider" />
                  <div className="row-between">
                    <span className="xs faint">Relationships</span>
                    <span className="small tabular">{related.length}</span>
                  </div>
                  <hr className="divider" />
                  <p className="xs muted">
                    Graph sub-queries load incrementally from Neo4j; metadata resolves from
                    PostgreSQL on node expansion.
                  </p>
                </div>
              ) : (
                <p className="small muted">Select a node in the graph to inspect it.</p>
              )}
            </div>

            <div className="card stack stack-4">
              <span className="eyebrow">Connected standards</span>
              <div className="stack stack-2">
                {related.map((r) => (
                  <button
                    key={r.id}
                    className="connected-row"
                    onClick={() => GRAPH.nodes.some((n) => n.id === r.id) && setSelected(r.id)}
                  >
                    <span className="legend-dot" style={{ background: NODE_KINDS[r.kind].color }} />
                    <span className="mono xs grow" style={{ textAlign: 'left' }}>{r.id}</span>
                    <span className="xs faint nowrap">{NODE_KINDS[r.kind].label}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
