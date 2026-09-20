import Icon from './Icon';

/** Confidence meter with numeric + textual label (colour is never the only cue). */
export function Confidence({ value, showBar = true }) {
  const pct = Math.round(value * 100);
  const band = value >= 0.85 ? 'High' : value >= 0.6 ? 'Moderate' : 'Low';
  const tone = value >= 0.85 ? 'var(--ok)' : value >= 0.6 ? 'var(--warn)' : 'var(--crit)';

  return (
    <div className="stack stack-2" style={{ minWidth: 132 }}>
      <div className="row-between">
        <span className="xs faint">Confidence</span>
        <span className="xs strong tabular" style={{ color: tone }}>
          {pct}% · {band}
        </span>
      </div>
      {showBar && (
        <div
          className="meter"
          role="meter"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Confidence ${pct} percent, ${band}`}
        >
          <div className="meter-fill" style={{ width: `${pct}%`, background: tone }} />
        </div>
      )}
    </div>
  );
}

/** Version badge — carries an icon so it reads without colour. */
export function VersionBadge({ version, supersededBy }) {
  if (version === 'superseded') {
    return (
      <span className="badge badge-crit" title={supersededBy ? `Superseded by ${supersededBy}` : 'Superseded'}>
        <Icon name="alert" size={12} />
        Superseded
      </span>
    );
  }
  return (
    <span className="badge badge-ok">
      <Icon name="check" size={12} />
      Latest
    </span>
  );
}

export function SeverityBadge({ severity, map }) {
  const s = map[severity];
  const icon = severity === 'critical' ? 'alert' : severity === 'minor' ? 'info' : 'info';
  return (
    <span className={`badge ${s.badge}`}>
      <Icon name={icon} size={12} />
      {s.label}
    </span>
  );
}

export function StatTile({ label, value, delta, trend }) {
  const good = trend === 'down';
  return (
    <div className="card stack stack-3">
      <span className="xs faint">{label}</span>
      <span className="tabular" style={{ fontSize: 'var(--fs-xl)', fontWeight: 600, letterSpacing: '-0.03em' }}>
        {value.toLocaleString('en-IN')}
      </span>
      {delta && (
        <span className="xs" style={{ color: good ? 'var(--ok)' : 'var(--ink-muted)' }}>
          {delta} vs last month
        </span>
      )}
    </div>
  );
}

export function EmptyState({ icon = 'search', title, body, action }) {
  return (
    <div className="empty">
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 'var(--s4)', color: 'var(--ink-faint)' }}>
        <Icon name={icon} size={28} strokeWidth={1.4} />
      </div>
      <p className="empty-title">{title}</p>
      <p className="small" style={{ maxWidth: '46ch', margin: '0 auto' }}>{body}</p>
      {action && <div style={{ marginTop: 'var(--s5)' }}>{action}</div>}
    </div>
  );
}

/** Copy-to-clipboard button with transient confirmation. */
export function CopyButton({ text, label = 'Copy clause' }) {
  const onCopy = async (e) => {
    const btn = e.currentTarget;
    try {
      await navigator.clipboard.writeText(text);
      const prev = btn.dataset.label || label;
      btn.dataset.label = prev;
      btn.textContent = 'Copied';
      setTimeout(() => { btn.textContent = prev; }, 1600);
    } catch {
      /* Clipboard unavailable (insecure context) — silently no-op. */
    }
  };

  return (
    <button type="button" className="btn btn-secondary btn-sm" onClick={onCopy}>
      {label}
    </button>
  );
}
