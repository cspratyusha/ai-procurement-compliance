import { useState } from 'react';
import Icon from './Icon';
import { ATTR_SUGGESTIONS } from '../data/catalogue';

/**
 * "What the system understood" — the parsed query as editable chips.
 *
 * If the engine read 1100V as 1100W, the officer corrects it here rather than
 * losing confidence in the whole result. Uncertain reads are marked, not hidden.
 */
export default function ParsedChips({ attrs, onChange, onRerun }) {
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState('');
  const [dirty, setDirty] = useState(false);

  const startEdit = (a) => { setEditing(a.id); setDraft(a.value); };

  const commit = (id) => {
    const next = attrs.map((a) => (a.id === id ? { ...a, value: draft, confident: true, edited: true } : a));
    onChange(next);
    setEditing(null);
    setDirty(true);
  };

  const uncertain = attrs.filter((a) => !a.confident).length;

  return (
    <div className="stack stack-3">
      <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
        <span className="eyebrow">What the system understood</span>
        {uncertain > 0 && (
          <span className="badge badge-warn">
            <Icon name="alert" size={11} />
            {uncertain} uncertain
          </span>
        )}
      </div>

      <div className="chip-list">
        {attrs.map((a) => {
          const isEditing = editing === a.id;
          const suggestions = ATTR_SUGGESTIONS[a.key] || [];

          if (isEditing) {
            return (
              <span key={a.id} className="chip" style={{ borderColor: 'var(--ink)' }}>
                <span className="chip-key">{a.key}</span>
                <input
                  className="chip-input"
                  value={draft}
                  autoFocus
                  list={`sug-${a.id}`}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commit(a.id);
                    if (e.key === 'Escape') setEditing(null);
                  }}
                  aria-label={`Edit ${a.key}`}
                />
                <datalist id={`sug-${a.id}`}>
                  {suggestions.map((s) => <option key={s} value={s} />)}
                </datalist>
                <span className="chip-actions">
                  <button className="btn-icon chip-edit" onClick={() => commit(a.id)} aria-label="Save">
                    <Icon name="check" size={12} />
                  </button>
                  <button className="btn-icon chip-edit" onClick={() => setEditing(null)} aria-label="Cancel">
                    <Icon name="x" size={12} />
                  </button>
                </span>
              </span>
            );
          }

          return (
            <span key={a.id} className={`chip ${!a.confident ? 'is-uncertain' : ''}`}>
              <span className="chip-key">{a.key}</span>
              <span className="chip-val">{a.value}</span>
              {a.edited && <span className="badge badge-ok" style={{ padding: '0 4px' }}>edited</span>}
              <button
                className="btn-icon chip-edit"
                onClick={() => startEdit(a)}
                aria-label={`Edit ${a.key}, currently ${a.value}`}
                title="Edit"
              >
                <Icon name="sliders" size={12} />
              </button>
            </span>
          );
        })}
      </div>

      {dirty && (
        <div className="notice notice-info fade-in">
          <Icon name="info" size={14} />
          <div className="row-between grow wrap" style={{ gap: 'var(--s2)' }}>
            <span className="xs">Attributes changed — re-run to update the recommendations.</span>
            <button className="btn btn-secondary btn-sm" onClick={() => { onRerun?.(); setDirty(false); }}>
              <Icon name="refresh" size={13} /> Re-run
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
