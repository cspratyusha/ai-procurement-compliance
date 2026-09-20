import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import ClusterGraph from '../components/ClusterGraph';
import { useSpec } from '../state/SpecStore';
import { GRAPH, NODE_KINDS } from '../data/mock';
import { STANDARD_DETAIL } from '../data/catalogue';
import './map.css';

/** Graph kind -> basket role. */
const KIND_ROLE = {
  primary: 'primary',
  normative: 'primary',
  test: 'test',
  terminology: 'terminology',
  installation: 'installation',
  overlap: 'safety',
  certification: 'certification',
};

/** Branches group the cluster so a whole category can be added in one action. */
const BRANCHES = [
  { id: 'normative', label: 'Normative references', kinds: ['normative'] },
  { id: 'test', label: 'Test methods', kinds: ['test'] },
  { id: 'installation', label: 'Installation', kinds: ['installation'] },
  { id: 'terminology', label: 'Terminology', kinds: ['terminology'] },
  { id: 'overlap', label: 'Overlapping scope', kinds: ['overlap'] },
];

export default function StandardsMap() {
  const spec = useSpec();
  const [root] = useState('IS 694:2010');
  const [depth, setDepth] = useState(1);
  const [selected, setSelected] = useState(root);
  const [view, setView] = useState('graph');

  /** Hop-limited subgraph. At depth 1 only direct neighbours of the root show. */
  const visible = useMemo(() => {
    const keep = new Set([root]);
    let frontier = [root];
    for (let hop = 0; hop < depth; hop++) {
      const next = [];
      GRAPH.edges.forEach((e) => {
        if (frontier.includes(e.from) && !keep.has(e.to)) { keep.add(e.to); next.push(e.to); }
        if (frontier.includes(e.to) && !keep.has(e.from)) { keep.add(e.from); next.push(e.from); }
      });
      frontier = next;
    }
    return {
      nodes: GRAPH.nodes.filter((n) => keep.has(n.id)),
      edges: GRAPH.edges.filter((e) => keep.has(e.from) && keep.has(e.to)),
    };
  }, [root, depth]);

  const nodeToItem = (n) => ({
    code: n.id,
    title: n.title,
    role: KIND_ROLE[n.kind] || 'primary',
    version: 'latest',
    addedFrom: 'standards map',
  });

  const addBranch = (branch) => {
    const items = visible.nodes
      .filter((n) => branch.kinds.includes(n.kind))
      .map(nodeToItem);
    if (items.length) spec.addMany(items);
  };

  const branchCounts = useMemo(() => {
    const c = {};
    BRANCHES.forEach((b) => {
      c[b.id] = visible.nodes.filter((n) => b.kinds.includes(n.kind)).length;
    });
    return c;
  }, [visible]);

  const selNode = visible.nodes.find((n) => n.id === selected);
  const detail = selNode ? STANDARD_DETAIL[selNode.id] : null;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Related standards map</h1>
          <p className="page-sub">
            The cluster around <span className="mono strong">{root}</span>. Allied and normative
            standards are a relationship problem, not a search problem — this is what makes that
            legible. Select a branch to add a whole category at once.
          </p>
        </div>
        <div className="row" style={{ gap: 'var(--s2)' }}>
          <div className="seg" role="group" aria-label="Traversal depth">
            <button onClick={() => setDepth(1)} aria-pressed={depth === 1}>1 hop</button>
            <button onClick={() => setDepth(2)} aria-pressed={depth === 2}>2 hops</button>
          </div>
          <div className="seg" role="group" aria-label="View mode">
            <button onClick={() => setView('graph')} aria-pressed={view === 'graph'}>Graph</button>
            <button onClick={() => setView('list')} aria-pressed={view === 'list'}>List</button>
          </div>
        </div>
      </div>

      <div className="grid split" style={{ "--rail": "320px" }}>
        <div className="stack stack-4">
          <div className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">
                {visible.nodes.length} standards · {depth} hop{depth === 1 ? '' : 's'}
              </h2>
              <span className="xs faint">Click a node to inspect</span>
            </div>
            <div className="card-body">
              {view === 'graph' ? (
                <ClusterGraph data={visible} height={380} selected={selected} onSelect={setSelected} />
              ) : (
                <div className="scroll-x" tabIndex={0} role="region" aria-label="Standards in the cluster">
                  <table className="table table-hover">
                    <caption className="sr-only">Standards in the cluster</caption>
                    <thead>
                      <tr>
                        <th scope="col">Standard</th>
                        <th scope="col">Title</th>
                        <th scope="col">Relationship</th>
                        <th scope="col"><span className="sr-only">Add</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.nodes.map((n) => (
                        <tr key={n.id}>
                          <td className="mono xs strong nowrap">{n.label}</td>
                          <td className="small">{n.title}</td>
                          <td>
                            <span className="legend-item">
                              <span className="legend-dot" style={{ background: NODE_KINDS[n.kind].color }} />
                              <span className="xs">{NODE_KINDS[n.kind].label}</span>
                            </span>
                          </td>
                          <td>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => spec.add(nodeToItem(n))}
                              disabled={spec.has(n.id)}
                            >
                              {spec.has(n.id) ? 'Added' : 'Add'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="stack stack-4">
          <div className="card stack stack-4">
            <span className="eyebrow">Add a whole branch</span>
            <p className="xs muted">
              One action adds every standard in a category, so the officer does not assemble the
              cluster by hand.
            </p>
            <div className="stack stack-2">
              {BRANCHES.filter((b) => branchCounts[b.id] > 0).map((b) => (
                <button key={b.id} className="branch-row" onClick={() => addBranch(b)}>
                  <span className="legend-dot" style={{ background: NODE_KINDS[b.kinds[0]].color }} />
                  <span className="stack stack-2 grow" style={{ textAlign: 'left' }}>
                    <span className="xs strong">{b.label}</span>
                    <span className="xs faint">{branchCounts[b.id]} standard{branchCounts[b.id] === 1 ? '' : 's'}</span>
                  </span>
                  <Icon name="plus" size={14} />
                </button>
              ))}
            </div>
            <hr className="divider" />
            <button
              className="btn btn-primary btn-sm"
              onClick={() => spec.addMany(visible.nodes.map(nodeToItem))}
            >
              <Icon name="layers" size={14} />
              Add entire cluster ({visible.nodes.length})
            </button>
          </div>

          {selNode && (
            <div className="card stack stack-3 fade-in">
              <span className="eyebrow">Selected node</span>
              <div className="stack stack-2">
                <span className="mono small strong">{selNode.label}</span>
                <span className="xs muted">{selNode.title}</span>
              </div>
              <span className="legend-item">
                <span className="legend-dot" style={{ background: NODE_KINDS[selNode.kind].color }} />
                <span className="xs faint">{NODE_KINDS[selNode.kind].label}</span>
              </span>
              <hr className="divider" />
              <div className="row" style={{ gap: 'var(--s2)' }}>
                <button
                  className="btn btn-secondary btn-sm grow"
                  onClick={() => spec.add(nodeToItem(selNode))}
                  disabled={spec.has(selNode.id)}
                >
                  {spec.has(selNode.id) ? 'In spec' : 'Add'}
                </button>
                {detail && (
                  <Link to={`/app/standard/${encodeURIComponent(selNode.id)}`} className="btn btn-ghost btn-sm">
                    Detail <Icon name="chevronRight" size={13} />
                  </Link>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
