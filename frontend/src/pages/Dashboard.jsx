import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { StatTile } from '../components/Primitives';
import { USER, SUMMARY_TILES, RECENT_QUERIES, AUDITED_TENDERS, ALERTS } from '../data/mock';
import DemoDataNotice from '../components/DemoDataNotice';

const ACTIONS = [
  { to: '/app/query', icon: 'search', title: 'New specification', body: 'Describe a product and get the applicable standards cluster.' },
  { to: '/app/audit', icon: 'audit', title: 'Audit a tender', body: 'Upload a draft and get a severity-tagged gap report.' },
  { to: '/app/explorer', icon: 'graph', title: 'Standards explorer', body: 'Browse the relationship graph around any standard.' },
  { to: '/app/simulator', icon: 'sliders', title: 'Scenario simulator', body: 'See how the cluster shifts when requirements change.' },
];

const STATUS = {
  accepted:  { label: 'Accepted',  cls: 'badge-ok' },
  corrected: { label: 'Corrected', cls: 'badge-warn' },
  orphan:    { label: 'No match',  cls: 'badge-crit' },
};

export default function Dashboard() {
  const unread = ALERTS.filter((a) => a.unread);
  // Greet by the first name, not the last token — "Demo User" should not
  // become "User". Falls back to the whole name for single-word names.
  const firstName = USER.name.trim().split(/\s+/)[0];

  return (
    <div className="container page">
      <DemoDataNotice
        what="Query counts, compliance rates and activity figures are sample data."
        next="They would come from stored query history once the engine logs searches."
      />
      <div className="page-head">
        <div>
          <h1 className="page-title">Good afternoon, {firstName}</h1>
          <p className="page-sub">
            {unread.length} standard{unread.length === 1 ? '' : 's'} affecting your subscribed
            categories changed recently. Review before your next tender goes out.
          </p>
        </div>
        <Link to="/app/query" className="btn btn-primary">
          <Icon name="plus" size={15} />
          New query
        </Link>
      </div>

      <div className="stack stack-6">
        <section className="grid grid-4">
          {SUMMARY_TILES.map((t) => <StatTile key={t.id} {...t} />)}
        </section>

        <section>
          <h2 className="eyebrow" style={{ marginBottom: 'var(--s4)' }}>Quick actions</h2>
          <div className="grid grid-4">
            {ACTIONS.map((a) => (
              <Link key={a.to} to={a.to} className="card card-link stack stack-3">
                <span style={{ color: 'var(--ink-soft)' }}><Icon name={a.icon} size={19} /></span>
                <span className="small strong">{a.title}</span>
                <span className="xs muted">{a.body}</span>
              </Link>
            ))}
          </div>
        </section>

        <section className="grid split" style={{ "--rail": "1fr" }}>
          <div className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Recent queries</h2>
              <Link to="/app/query" className="btn btn-ghost btn-sm">
                View all <Icon name="chevronRight" size={13} />
              </Link>
            </div>
            <div className="scroll-x" tabIndex={0} role="region" aria-label="Recent queries">
              <table className="table table-hover">
                <caption className="sr-only">Your most recent specification queries</caption>
                <thead>
                  <tr>
                    <th scope="col">Query</th>
                    <th scope="col">Top standard</th>
                    <th scope="col">Confidence</th>
                    <th scope="col">Status</th>
                    <th scope="col">When</th>
                  </tr>
                </thead>
                <tbody>
                  {RECENT_QUERIES.map((q) => (
                    <tr key={q.id}>
                      <td style={{ minWidth: 230 }}>
                        <span className="small">{q.text}</span>
                      </td>
                      <td>
                        {q.standard
                          ? <span className="mono small strong nowrap">{q.standard}</span>
                          : <span className="xs faint">—</span>}
                      </td>
                      <td className="tabular small">{Math.round(q.confidence * 100)}%</td>
                      <td><span className={`badge ${STATUS[q.status].cls}`}>{STATUS[q.status].label}</span></td>
                      <td className="xs faint nowrap">{q.time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="stack stack-4">
            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Pending alerts</h2>
                <Link to="/app/alerts" className="btn btn-ghost btn-sm">All</Link>
              </div>
              <div className="stack" style={{ padding: 'var(--s2)' }}>
                {unread.map((a) => (
                  <Link key={a.id} to="/app/alerts" className="alert-mini">
                    <Icon
                      name={a.kind === 'revision' ? 'refresh' : a.kind === 'certification' ? 'shield' : 'alert'}
                      size={15}
                    />
                    <span className="stack stack-2 grow">
                      <span className="xs strong">{a.title}</span>
                      <span className="xs faint">{a.category} · {a.time}</span>
                    </span>
                  </Link>
                ))}
              </div>
            </div>

            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Audited tenders</h2>
              </div>
              <div className="stack" style={{ padding: 'var(--s2)' }}>
                {AUDITED_TENDERS.map((t) => (
                  <Link key={t.id} to="/app/audit" className="alert-mini">
                    <Icon name="file" size={15} />
                    <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <span className="xs strong" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {t.name}
                      </span>
                      <span className="xs faint">{t.findings} findings · {t.time}</span>
                    </span>
                    {t.critical > 0 && <span className="badge badge-crit">{t.critical}</span>}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
