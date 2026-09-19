import Icon from '../components/Icon';
import { CATALOGUE_SYNC } from '../data/catalogue';

const SOURCE_STATUS = {
  ok:    { label: 'Synced', cls: 'badge-ok',   icon: 'check' },
  stale: { label: 'Stale',  cls: 'badge-warn', icon: 'alert' },
  error: { label: 'Failed', cls: 'badge-crit', icon: 'x' },
};

/**
 * Admin console — one screen, deliberately. Catalogue freshness is the
 * credibility question ("is this data current?"); acceptance rates are the
 * feedback loop that trains the ranker.
 */
export default function Admin() {
  const s = CATALOGUE_SYNC;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Admin console</h1>
          <p className="page-sub">
            Catalogue sync state, the amendment feed, items flagged by users, and the
            accept/reject signal that retrains the ranking model.
          </p>
        </div>
        <button className="btn btn-secondary">
          <Icon name="refresh" size={15} /> Force resync
        </button>
      </div>

      <div className="stack stack-5">
        <section className="grid grid-4">
          {[
            { label: 'Standards indexed', value: s.totalStandards.toLocaleString('en-IN') },
            { label: 'New this month', value: s.newThisMonth },
            { label: 'Amended this month', value: s.amendedThisMonth },
            { label: 'Withdrawn this month', value: s.withdrawnThisMonth },
          ].map((t) => (
            <div key={t.label} className="card stack stack-3">
              <span className="xs faint">{t.label}</span>
              <span className="tabular" style={{ fontSize: 'var(--fs-xl)', fontWeight: 600, letterSpacing: '-0.03em' }}>
                {t.value}
              </span>
            </div>
          ))}
        </section>

        <div className="grid split" style={{ "--rail": "1fr" }}>
          <section className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title">Data sources</h2>
                <span className="xs faint">Last full sync: {s.lastSync}</span>
              </div>
            </div>
            <div className="scroll-x" tabIndex={0} role="region" aria-label="Data source sync status">
              <table className="table">
                <caption className="sr-only">Catalogue data source sync status</caption>
                <thead>
                  <tr>
                    <th scope="col">Source</th>
                    <th scope="col">Status</th>
                    <th scope="col">Last update</th>
                  </tr>
                </thead>
                <tbody>
                  {s.sources.map((src) => {
                    const st = SOURCE_STATUS[src.status];
                    return (
                      <tr key={src.name}>
                        <td className="small">{src.name}</td>
                        <td><span className={`badge ${st.cls}`}><Icon name={st.icon} size={11} />{st.label}</span></td>
                        <td className="xs muted nowrap">{src.last}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="card-body" style={{ borderTop: '1px solid var(--line)' }}>
              <div className="notice notice-warn">
                <Icon name="alert" size={14} />
                <span className="xs">
                  The QCO / Gazette feed is 3 days stale. Certification mappings may not reflect
                  orders notified this week.
                </span>
              </div>
            </div>
          </section>

          <section className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title">Ranking feedback</h2>
                <span className="xs faint">Accept rate by match band</span>
              </div>
            </div>
            <div className="card-body stack stack-4">
              {s.acceptance.map((a) => (
                <div key={a.band} className="stack stack-2">
                  <div className="row-between">
                    <span className="small">{a.band}</span>
                    <span className="small strong tabular">{a.accepted}% accepted</span>
                  </div>
                  <div className="meter" role="meter" aria-valuenow={a.accepted} aria-valuemin={0} aria-valuemax={100} aria-label={`${a.band} accept rate`}>
                    <div
                      className="meter-fill"
                      style={{ width: `${a.accepted}%`, background: a.accepted >= 80 ? 'var(--ok)' : a.accepted >= 60 ? 'var(--warn)' : 'var(--crit)' }}
                    />
                  </div>
                </div>
              ))}
              <hr className="divider" />
              <p className="xs muted">
                Bands behaving as intended: strong matches are accepted almost always, and
                needs-review items are rejected more than half the time — which is the point of
                labelling them separately rather than showing one number.
              </p>
            </div>
          </section>
        </div>

        <section className="card card-flush">
          <div className="card-head">
            <h2 className="card-title">Flagged by users</h2>
            <span className="badge badge-warn">{s.flagged.length} open</span>
          </div>
          <div className="stack" style={{ padding: 'var(--s3)' }}>
            {s.flagged.map((f) => (
              <div key={f.id} className="row" style={{ gap: 'var(--s3)', padding: 'var(--s3)', alignItems: 'flex-start' }}>
                <Icon name="alert" size={15} style={{ color: 'var(--warn)', flexShrink: 0, marginTop: 2 }} />
                <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                  <div className="row wrap" style={{ gap: 6 }}>
                    <span className="mono xs strong">{f.code}</span>
                    <span className="badge badge-neutral">{f.count} reports</span>
                  </div>
                  <span className="xs muted">{f.issue}</span>
                </div>
                <div className="row" style={{ gap: 'var(--s2)', flexShrink: 0 }}>
                  <button className="btn btn-secondary btn-sm">Accept</button>
                  <button className="btn btn-ghost btn-sm">Dismiss</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
