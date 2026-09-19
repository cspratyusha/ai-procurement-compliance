import { useState, useId } from 'react';
import { NODE_KINDS } from '../data/mock';
import './graph.css';

/**
 * Node-link view of a standards cluster.
 * Inline SVG on a 100x100 percentage grid — keeps the bundle small and
 * lets node styling inherit the matte theme tokens directly.
 * A data table alternative is always rendered for assistive tech.
 */
export default function ClusterGraph({ data, height = 320, onSelect, selected }) {
  const [hover, setHover] = useState(null);
  const tableId = useId();

  const byId = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
  const active = hover || selected;

  const isDim = (id) => {
    if (!active) return false;
    if (id === active) return false;
    return !data.edges.some(
      (e) => (e.from === active && e.to === id) || (e.to === active && e.from === id)
    );
  };

  return (
    <div className="graph-wrap">
      <div className="graph-canvas" style={{ height }}>
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="graph-edges"
          aria-hidden="true"
        >
          {data.edges.map((e, i) => {
            const a = byId[e.from];
            const b = byId[e.to];
            if (!a || !b) return null;
            const dim = active && ![e.from, e.to].includes(active);
            return (
              <line
                key={i}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={NODE_KINDS[e.kind]?.color || 'var(--line-strong)'}
                strokeWidth="0.28"
                strokeDasharray={e.kind === 'overlap' ? '1.4 1' : undefined}
                opacity={dim ? 0.12 : 0.42}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>

        {data.nodes.map((n) => {
          const kind = NODE_KINDS[n.kind];
          return (
            <button
              key={n.id}
              type="button"
              className={`graph-node ${n.kind === 'primary' ? 'is-primary' : ''} ${selected === n.id ? 'is-selected' : ''}`}
              style={{
                left: `${n.x}%`,
                top: `${n.y}%`,
                opacity: isDim(n.id) ? 0.3 : 1,
                borderColor: kind.color,
              }}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(n.id)}
              onBlur={() => setHover(null)}
              onClick={() => onSelect?.(n.id)}
              title={`${n.label} — ${n.title}`}
            >
              <span className="graph-dot" style={{ background: kind.color }} />
              <span className="graph-label mono">{n.label}</span>
            </button>
          );
        })}
      </div>

      <div className="graph-legend">
        {Object.entries(NODE_KINDS).map(([k, v]) => (
          <span key={k} className="legend-item">
            <span className="legend-dot" style={{ background: v.color }} />
            <span className="xs faint">{v.label}</span>
          </span>
        ))}
      </div>

      {/* Accessible equivalent of the graph (chart a11y guideline). */}
      <details className="graph-table">
        <summary className="xs muted">View cluster as a table</summary>
        <div className="scroll-x" tabIndex={0} role="region" aria-label="Cluster relationships" style={{ marginTop: 'var(--s3)' }}>
          <table className="table" id={tableId}>
            <caption className="sr-only">Standards cluster relationships</caption>
            <thead>
              <tr>
                <th scope="col">Standard</th>
                <th scope="col">Title</th>
                <th scope="col">Relationship</th>
              </tr>
            </thead>
            <tbody>
              {data.nodes.map((n) => (
                <tr key={n.id}>
                  <td className="mono small nowrap">{n.label}</td>
                  <td className="small">{n.title}</td>
                  <td className="small">{NODE_KINDS[n.kind].label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
