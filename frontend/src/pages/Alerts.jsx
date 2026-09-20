import { useState } from 'react';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { ALERTS, SUBSCRIPTIONS } from '../data/mock';

const KIND = {
  revision:      { icon: 'refresh', label: 'Revision',      cls: 'badge-crit' },
  amendment:     { icon: 'file',    label: 'Amendment',     cls: 'badge-warn' },
  certification: { icon: 'shield',  label: 'Certification', cls: 'badge-accent' },
  gap:           { icon: 'alert',   label: 'Standards gap', cls: 'badge-info' },
};

export default function Alerts() {
  const [read, setRead] = useState({});
  const [subs, setSubs] = useState(
    Object.fromEntries(SUBSCRIPTIONS.map((s) => [s.id, s.active]))
  );
  const [filter, setFilter] = useState('all');

  const isUnread = (a) => a.unread && !read[a.id];
  const shown = filter === 'unread' ? ALERTS.filter(isUnread) : ALERTS;
  const unreadCount = ALERTS.filter(isUnread).length;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Alerts &amp; subscriptions</h1>
          <p className="page-sub">
            A background job matches newly detected revisions and amendments against your subscribed
            categories and notifies you before an outdated citation reaches a live tender.
          </p>
        </div>
        {unreadCount > 0 && (
          <button
            className="btn btn-secondary"
            onClick={() => setRead(Object.fromEntries(ALERTS.map((a) => [a.id, true])))}
          >
            <Icon name="check" size={15} />
            Mark all read
          </button>
        )}
      </div>

      <div className="grid split" style={{ "--rail": "1fr" }}>
        <div className="stack stack-4">
          <div className="row wrap" style={{ gap: 'var(--s2)' }}>
            <div className="seg" role="group" aria-label="Filter alerts">
              <button onClick={() => setFilter('all')} aria-pressed={filter === 'all'}>
                All ({ALERTS.length})
              </button>
              <button onClick={() => setFilter('unread')} aria-pressed={filter === 'unread'}>
                Unread ({unreadCount})
              </button>
            </div>
          </div>

          {shown.length === 0 ? (
            <div className="card">
              <EmptyState
                icon="checkCircle"
                title="You are all caught up"
                body="No unread alerts. New revisions affecting your subscribed categories will appear here."
              />
            </div>
          ) : (
            <div className="stack stack-3">
              {shown.map((a) => {
                const k = KIND[a.kind];
                const unread = isUnread(a);
                return (
                  <article key={a.id} className={`card alert-card ${unread ? 'is-unread' : ''}`}>
                    <div className="row" style={{ alignItems: 'flex-start', gap: 'var(--s4)' }}>
                      <span className="alert-icon"><Icon name={k.icon} size={17} /></span>

                      <div className="stack stack-3 grow" style={{ minWidth: 0 }}>
                        <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                          <span className={`badge ${k.cls}`}>{k.label}</span>
                          <span className="badge badge-neutral">{a.category}</span>
                          {unread && <span className="badge badge-neutral">Unread</span>}
                        </div>

                        <h2 className="small strong">{a.title}</h2>
                        <p className="small muted">{a.body}</p>

                        <div className="row-between wrap" style={{ gap: 'var(--s3)' }}>
                          <span className="xs faint">{a.time}</span>
                          <div className="row" style={{ gap: 'var(--s2)' }}>
                            {unread && (
                              <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => setRead((p) => ({ ...p, [a.id]: true }))}
                              >
                                Mark read
                              </button>
                            )}
                            <button className="btn btn-secondary btn-sm">
                              View affected tenders
                              <Icon name="chevronRight" size={13} />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>

        <div className="stack stack-4">
          <div className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Subscribed categories</h2>
            </div>
            <div className="stack" style={{ padding: 'var(--s3)' }}>
              {SUBSCRIPTIONS.map((s) => (
                <label key={s.id} className="sub-row">
                  <input
                    type="checkbox"
                    checked={!!subs[s.id]}
                    onChange={() => setSubs((p) => ({ ...p, [s.id]: !p[s.id] }))}
                  />
                  <span className="stack stack-2 grow">
                    <span className="small">{s.category}</span>
                    <span className="xs faint">{s.standards} standards monitored</span>
                  </span>
                </label>
              ))}
            </div>
            <div className="card-body" style={{ borderTop: '1px solid var(--line)' }}>
              <button className="btn btn-secondary btn-sm" style={{ width: '100%' }}>
                <Icon name="plus" size={14} />
                Add category
              </button>
            </div>
          </div>

          <div className="card stack stack-4">
            <span className="eyebrow">Notification channels</span>
            {[
              { id: 'inapp', label: 'In-app notifications', hint: 'Bell icon and dashboard queue', on: true },
              { id: 'email', label: 'Email digest', hint: 'Daily summary at 09:00 IST', on: true },
              { id: 'critical', label: 'Immediate email on revision', hint: 'Sent the moment a subscribed standard is superseded', on: false },
            ].map((c) => (
              <label key={c.id} className="check">
                <input type="checkbox" defaultChecked={c.on} />
                <span className="stack stack-2">
                  <span className="small">{c.label}</span>
                  <span className="xs faint">{c.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
