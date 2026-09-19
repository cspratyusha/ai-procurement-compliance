import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from './Icon';
import { useSpec, ROLE_ORDER, ROLE_LABEL } from '../state/SpecStore';
import './basket.css';

/**
 * Persistent spec basket. Docked to the right of the workbench so standards
 * collected on any screen stay visible — the officer is assembling, not browsing.
 */
export default function SpecBasket() {
  const spec = useSpec();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const { count, grouped, gaps } = spec;
  const critical = gaps.filter((g) => g.severity === 'critical').length;

  return (
    <>
      <button
        className={`basket-tab ${count > 0 ? 'has-items' : ''}`}
        onClick={() => setOpen(true)}
        aria-label={`Open spec basket, ${count} standard${count === 1 ? '' : 's'}`}
      >
        <Icon name="layers" size={17} />
        <span className="basket-tab-count tabular">{count}</span>
        {critical > 0 && <span className="basket-tab-dot" aria-hidden="true" />}
      </button>

      {open && <button className="scrim" aria-label="Close basket" onClick={() => setOpen(false)} />}

      <aside className={`basket ${open ? 'is-open' : ''}`} aria-label="Specification basket">
        <div className="basket-head">
          <div className="stack stack-2">
            <span className="strong small">Spec basket</span>
            <span className="xs faint">
              {count} standard{count === 1 ? '' : 's'}
              {spec.project ? ` · ${spec.project}` : ''}
            </span>
          </div>
          <button className="btn-icon" onClick={() => setOpen(false)} aria-label="Close basket">
            <Icon name="x" size={17} />
          </button>
        </div>

        <div className="basket-body">
          {count === 0 ? (
            <div className="empty" style={{ padding: 'var(--s7) var(--s4)' }}>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 'var(--s3)', color: 'var(--ink-faint)' }}>
                <Icon name="layers" size={24} strokeWidth={1.4} />
              </div>
              <p className="empty-title">Nothing collected yet</p>
              <p className="xs" style={{ maxWidth: '30ch', margin: '0 auto' }}>
                Add standards from the recommendations, the detail page, or the related-standards map.
              </p>
            </div>
          ) : (
            <>
              {gaps.length > 0 && (
                <div className="stack stack-2" style={{ marginBottom: 'var(--s4)' }}>
                  {gaps.map((g, i) => (
                    <div key={i} className={`notice ${g.severity === 'critical' ? 'notice-crit' : 'notice-warn'}`}>
                      <Icon name="alert" size={14} />
                      <span className="xs">{g.text}</span>
                    </div>
                  ))}
                </div>
              )}

              {ROLE_ORDER.filter((r) => grouped[r]?.length).map((role) => (
                <section key={role} className="basket-group">
                  <span className="eyebrow">{ROLE_LABEL[role]}</span>
                  <div className="stack stack-2" style={{ marginTop: 'var(--s2)' }}>
                    {grouped[role].map((it, idx) => (
                      <div key={it.code} className="basket-item">
                        <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                          <div className="row wrap" style={{ gap: 6 }}>
                            <span className="mono xs strong">{it.code}</span>
                            {it.version === 'superseded' && (
                              <span className="badge badge-crit">Superseded</span>
                            )}
                          </div>
                          <span className="xs faint basket-item-title">{it.title}</span>
                        </div>
                        <div className="basket-item-actions">
                          <button
                            className="btn-icon basket-mini"
                            onClick={() => spec.move(it.code, -1)}
                            disabled={idx === 0 && role === ROLE_ORDER.find((r) => grouped[r]?.length)}
                            aria-label={`Move ${it.code} up`}
                          >
                            <Icon name="chevronDown" size={13} style={{ transform: 'rotate(180deg)' }} />
                          </button>
                          <button
                            className="btn-icon basket-mini"
                            onClick={() => spec.move(it.code, 1)}
                            aria-label={`Move ${it.code} down`}
                          >
                            <Icon name="chevronDown" size={13} />
                          </button>
                          <button
                            className="btn-icon basket-mini"
                            onClick={() => spec.remove(it.code)}
                            aria-label={`Remove ${it.code}`}
                          >
                            <Icon name="x" size={13} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </>
          )}
        </div>

        <div className="basket-foot">
          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            disabled={count === 0}
            onClick={() => { setOpen(false); navigate('/app/builder'); }}
          >
            Open spec builder
            <Icon name="arrowRight" size={15} />
          </button>
          {count > 0 && (
            <button className="btn btn-ghost btn-sm" style={{ width: '100%' }} onClick={spec.clear}>
              Clear basket
            </button>
          )}
        </div>
      </aside>
    </>
  );
}

/** Add/added toggle used on recommendation cards, detail pages and the map. */
export function AddButton({ item, size = 'sm', block = false }) {
  const spec = useSpec();
  const added = spec.has(item.code);

  return (
    <button
      className={`btn btn-${size} ${added ? 'btn-secondary' : 'btn-primary'}`}
      style={block ? { width: '100%' } : undefined}
      onClick={() => (added ? spec.remove(item.code) : spec.add(item))}
      aria-pressed={added}
    >
      <Icon name={added ? 'check' : 'plus'} size={14} />
      {added ? 'In spec' : 'Add to spec'}
    </button>
  );
}
