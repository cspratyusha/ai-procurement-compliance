import { useState, useEffect, useMemo, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Icon from '../components/Icon';
import ClusterGraph from '../components/ClusterGraph';
import { EmptyState } from '../components/Primitives';
import { useSpec } from '../state/SpecStore';
import { getRelated, listStandards, ApiError } from '../api/client';
import './map.css';
import './query.css';   // .notice — shared with the query screen

/**
 * The relationship cluster around one standard, from the engine.
 *
 * This screen rendered a hand-authored eight-node graph with fixed x/y
 * coordinates and a notice saying normative references "are not yet in the
 * dataset". That notice had gone stale: the relationship data was researched
 * in a later phase and `GET /standards/{id}/related` has served it since.
 *
 * Two honesty properties carry over from the standard-detail page, which
 * reads the same endpoint:
 *
 * **`researched: false` is not "no relationships".** It means nobody has read
 * this standard's referred-standards annexe. Relationships are recorded for
 * 16 standards; for the rest the honest answer is "unknown", and an empty
 * graph must say which of the two it is.
 *
 * **Citations outside the corpus are shown, not hidden.** A standard's annexe
 * cites standards the pilot corpus does not hold. Dropping them would
 * silently truncate the cluster and imply the standard depends on less than
 * it does, so they render dimmed and are not clickable.
 */

/** Relationship type -> graph kind, reusing the palette in NODE_KINDS. */
const TYPE_KIND = {
  material_spec: 'normative',
  test_method: 'test',
  terminology: 'terminology',
  installation: 'installation',
  related_product: 'overlap',
  certification: 'certification',
};

/** Graph kind -> spec-basket role. */
const KIND_ROLE = {
  primary: 'primary',
  normative: 'primary',
  test: 'test',
  terminology: 'terminology',
  installation: 'installation',
  overlap: 'safety',
  certification: 'certification',
};

/**
 * Lay the cluster out radially around the root.
 *
 * The fixture carried hand-placed x/y for eight nodes; real clusters vary in
 * size, so positions are computed. Angles start at -90° so the first branch
 * sits above the root rather than to its right, and the radius grows with the
 * node count so a large cluster spreads instead of overlapping.
 */
function layout(root, neighbours) {
  const nodes = [{
    id: root.number,
    label: root.number,
    title: root.title,
    kind: 'primary',
    x: 50,
    y: 50,
    outside: false,
  }];

  const count = neighbours.length;
  const radius = count <= 4 ? 28 : count <= 8 ? 31 : 34;

  neighbours.forEach((n, i) => {
    const angle = (-90 + (360 / Math.max(count, 1)) * i) * (Math.PI / 180);
    // Nodes are centred on their point (translate(-50%, -50%)), so one at
    // x: 97 hangs half its width outside the container. A label like
    // "IS 1489 (Part 1):2015" is wide, so the horizontal spread is modest
    // and both axes are clamped well inside the edges.
    const x = 50 + Math.cos(angle) * radius * 1.15;
    const y = 50 + Math.sin(angle) * radius;
    nodes.push({
      id: n.number,
      label: n.number,
      title: n.title || '',
      kind: TYPE_KIND[n.type] || 'normative',
      x: Math.min(82, Math.max(18, x)),
      y: Math.min(88, Math.max(12, y)),
      outside: !!n.outside_corpus,
      note: n.note || '',
    });
  });

  return {
    nodes,
    edges: neighbours.map((n) => ({
      from: root.number,
      to: n.number,
      kind: TYPE_KIND[n.type] || 'normative',
    })),
  };
}

export default function StandardsMap() {
  const spec = useSpec();
  const [params, setParams] = useSearchParams();
  const root = params.get('standard') || '';

  const [state, setState] = useState(root ? 'loading' : 'empty');
  const [related, setRelated] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [options, setOptions] = useState([]);

  // Standards that actually have relationships recorded are the only useful
  // starting points, but the engine does not expose that list -- so offer the
  // catalogue and let the empty state explain when one has none.
  useEffect(() => {
    const controller = new AbortController();
    listStandards({ signal: controller.signal })
      .then((data) => setOptions(Array.isArray(data) ? data : []))
      .catch(() => { /* selector is a convenience; the page works without it */ });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!root) { setState('empty'); return undefined; }

    const controller = new AbortController();
    setState('loading');
    setSelected(root);

    getRelated(root, { signal: controller.signal })
      .then((data) => { setRelated(data); setState('ready'); })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiError ? err : new ApiError('Could not load the cluster.'));
        setState('error');
      });

    return () => controller.abort();
  }, [root]);

  /** Every related standard, flattened out of its groups. */
  const neighbours = useMemo(() => {
    if (!related) return [];
    const out = [];
    (related.depends_on ?? []).forEach((group) => {
      (group.standards ?? []).forEach((s) => out.push({ ...s, type: s.type || group.type }));
    });
    (related.referenced_by ?? []).forEach((s) => {
      out.push({ ...s, type: s.type || 'related_product', inbound: true });
    });
    // One node per standard, even when two annexes cite it.
    const seen = new Set();
    return out.filter((s) => {
      const key = (s.number || '').toUpperCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [related]);

  const graph = useMemo(() => {
    if (!related) return { nodes: [], edges: [] };
    return layout({ number: related.number, title: related.title }, neighbours);
  }, [related, neighbours]);

  const selNode = graph.nodes.find((n) => n.id === selected);

  /** Groups as the API returned them, for the add-a-branch buttons. */
  const branches = useMemo(() => {
    if (!related) return [];
    return (related.depends_on ?? [])
      .map((group) => ({
        id: group.type,
        label: group.heading || group.type,
        explanation: group.explanation,
        // Only in-corpus standards can be added: the basket needs a record.
        items: (group.standards ?? []).filter((s) => !s.outside_corpus),
        outside: (group.standards ?? []).filter((s) => s.outside_corpus).length,
      }))
      .filter((b) => b.items.length || b.outside);
  }, [related]);

  const addBranch = useCallback((branch) => {
    const items = branch.items.map((s) => ({
      code: s.number,
      title: s.title || '',
      role: KIND_ROLE[TYPE_KIND[s.type] || 'normative'] || 'primary',
      version: 'latest',
      addedFrom: 'standards map',
    }));
    if (items.length) spec.addMany(items);
  }, [spec]);

  const pick = (value) => {
    if (value) setParams({ standard: value });
    else setParams({});
  };

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="map-title">Related standards map</h1>
          <p className="page-sub">
            The cluster around a standard, read from its referred-standards annexe.
            Allied standards are a relationship problem rather than a search problem —
            this is what makes that legible.
          </p>
        </div>
        <div className="field" style={{ minWidth: 260 }}>
          <label className="label sr-only" htmlFor="map-root">Standard</label>
          <select
            id="map-root"
            className="select"
            value={root}
            onChange={(e) => pick(e.target.value)}
          >
            <option value="">Choose a standard…</option>
            {options.map((s) => (
              <option key={s.id || s.number} value={s.number}>{s.number}</option>
            ))}
          </select>
        </div>
      </div>

      {state === 'empty' && (
        <div className="card">
          <EmptyState
            icon="graph"
            title="Choose a standard to map"
            body="Relationships have been researched for a small number of standards, read from their referred-standards annexes. Pick one above, or open any standard and use its allied-standards section."
            action={<Link to="/app/catalogue" className="btn btn-secondary btn-sm">Browse the catalogue</Link>}
          />
        </div>
      )}

      {state === 'loading' && (
        <div className="stack stack-3" aria-busy="true">
          <div className="skeleton" style={{ height: 320 }} />
          <div className="skeleton" style={{ height: 120 }} />
        </div>
      )}

      {state === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not load the cluster"
            body={error?.message ?? 'The standards engine did not respond.'}
            action={<button className="btn btn-primary btn-sm" onClick={() => pick(root)}>Retry</button>}
          />
        </div>
      )}

      {state === 'ready' && related && (
        <div className="stack stack-5">
          {!related.researched && (
            <div className="notice notice-warn" role="note">
              <Icon name="alert" size={15} />
              <div className="stack stack-2">
                <span className="small strong">No relationships recorded for {related.number}</span>
                <span className="xs">
                  Nobody has read this standard's referred-standards annexe yet. That is
                  not a statement that it has none — relationships have been researched
                  for a small number of standards, and this is not one of them.
                </span>
              </div>
            </div>
          )}

          {related.researched && neighbours.length === 0 && (
            <div className="notice notice-info" role="note">
              <Icon name="info" size={15} />
              <span className="xs">
                {related.number} was researched and no allied standards were recorded for it.
              </span>
            </div>
          )}

          {neighbours.length > 0 && (
            <div className="grid split" style={{ '--rail': '320px' }}>
              <div className="stack stack-4">
                <div className="card card-flush">
                  <div className="card-head">
                    <div className="stack stack-2">
                      <h2 className="card-title">
                        <span className="mono">{related.number}</span>
                      </h2>
                      <span className="xs faint">
                        {neighbours.length} allied standard{neighbours.length === 1 ? '' : 's'}
                        {' · '}
                        {neighbours.filter((n) => n.outside_corpus).length} outside this corpus
                      </span>
                    </div>
                  </div>
                  <div className="card-body">
                    <ClusterGraph
                      data={graph}
                      height={340}
                      selected={selected}
                      onSelect={setSelected}
                    />
                  </div>
                </div>

                {selNode && (
                  <div className="card stack stack-3">
                    <span className="eyebrow">Selected</span>
                    <h3 className="small strong">
                      <span className="mono">{selNode.id}</span>
                      {selNode.title ? ` — ${selNode.title}` : ''}
                    </h3>
                    {selNode.note && <p className="xs muted">{selNode.note}</p>}
                    {selNode.outside ? (
                      <div className="notice notice-warn" style={{ margin: 0 }}>
                        <Icon name="alert" size={14} />
                        <span className="xs">
                          Cited by {related.number} but not held in this corpus, so it cannot
                          be opened or added. Shown so the cluster is not silently truncated.
                        </span>
                      </div>
                    ) : (
                      <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                        <Link
                          to={`/app/standard/${encodeURIComponent(selNode.id)}`}
                          className="btn btn-secondary btn-sm"
                        >
                          Open detail <Icon name="chevronRight" size={13} />
                        </Link>
                        {selNode.id !== related.number && (
                          <button className="btn btn-ghost btn-sm" onClick={() => pick(selNode.id)}>
                            Centre the map here
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="stack stack-4">
                <div className="card card-flush">
                  <div className="card-head">
                    <h2 className="card-title">Add a branch</h2>
                  </div>
                  <div className="stack stack-3" style={{ padding: 'var(--s4)' }}>
                    {branches.map((b) => (
                      <div key={b.id} className="stack stack-2">
                        <div className="row-between">
                          <span className="small strong">{b.label}</span>
                          <span className="xs tabular faint">{b.items.length}</span>
                        </div>
                        {b.explanation && <span className="xs muted">{b.explanation}</span>}
                        {b.outside > 0 && (
                          <span className="xs faint">
                            {b.outside} more cited but outside this corpus, so not addable.
                          </span>
                        )}
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => addBranch(b)}
                          disabled={b.items.length === 0}
                        >
                          <Icon name="plus" size={13} />
                          Add {b.items.length} to spec
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {related.referenced_by?.length > 0 && (
                  <div className="card stack stack-3">
                    <span className="eyebrow">Cited by</span>
                    <p className="xs muted">
                      Standards whose annexes reference {related.number}.
                    </p>
                    {related.referenced_by.map((s) => (
                      <Link
                        key={s.number}
                        to={`/app/standard/${encodeURIComponent(s.number)}`}
                        className="alert-mini"
                      >
                        <Icon name="file" size={14} />
                        <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                          <span className="xs mono strong">{s.number}</span>
                          {s.title && <span className="xs faint">{s.title}</span>}
                        </span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
