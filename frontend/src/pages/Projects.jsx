import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { useSpec, ROLE_LABEL } from '../state/SpecStore';
import { getStats } from '../api/client';
import './query.css';   // .notice — shared with the query screen

/**
 * The work in progress on this machine.
 *
 * This screen listed five saved tenders with owners, statuses and "updated
 * 18 min ago" — none of which existed. There is no project storage and no
 * user accounts, so a multi-user project list cannot be made real.
 *
 * What *is* real is the spec basket: SpecStore persists to localStorage, so
 * the standards an officer has collected, the role each plays, the gaps in
 * the set and the freeze record all survive a reload and are genuinely
 * theirs. That is a smaller claim than "my projects" and it is the true one,
 * so the screen makes it instead.
 *
 * The limit is stated rather than implied: this is one browser on one
 * machine. Nothing here is shared with a colleague, and clearing site data
 * loses it. A screen that quietly looked like server-side storage would set
 * up exactly the wrong expectation about where the work lives.
 */

const STATUS = {
  frozen: { label: 'Frozen', cls: 'badge-ok' },
  draft:  { label: 'Draft',  cls: 'badge-warn' },
};

export default function Projects() {
  const spec = useSpec();
  const [stats, setStats] = useState(null);

  // Recent searches come from the engine's own log, so this screen shows the
  // real trail of what was searched rather than a fabricated history.
  useEffect(() => {
    const controller = new AbortController();
    getStats({ signal: controller.signal })
      .then(setStats)
      .catch(() => { /* engine down: the basket half of this page still works */ });
    return () => controller.abort();
  }, []);

  const { list, grouped, gaps, frozen, project, count } = spec;
  const recent = stats?.recent_queries ?? [];

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="projects-title">My work</h1>
          <p className="page-sub">
            The specification you are assembling, and the searches that fed it. Saved in
            this browser only — there are no accounts, so nothing here is shared with a
            colleague or synced to another machine.
          </p>
        </div>
        <Link to="/app/query" className="btn btn-primary">
          <Icon name="plus" size={15} /> New query
        </Link>
      </div>

      <div className="grid split" style={{ '--rail': '340px' }}>
        <div className="stack stack-4">
          <section className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title">
                  {project || 'Current specification'}
                </h2>
                {frozen && (
                  <span className="xs faint">
                    Frozen {new Date(frozen.at).toLocaleString('en-IN')}
                    {frozen.label ? ` · ${frozen.label}` : ''}
                  </span>
                )}
              </div>
              <div className="row" style={{ gap: 'var(--s2)' }}>
                <span className={`badge ${frozen ? STATUS.frozen.cls : STATUS.draft.cls}`}>
                  {frozen ? STATUS.frozen.label : STATUS.draft.label}
                </span>
                <span className="badge badge-neutral">{count}</span>
              </div>
            </div>

            {count === 0 ? (
              <EmptyState
                icon="layers"
                title="No standards collected yet"
                body="Standards you add from the search, catalogue or map screens collect here, grouped by the role they play in a specification."
                action={<Link to="/app/query" className="btn btn-secondary btn-sm">Start a search</Link>}
              />
            ) : (
              <div className="stack" style={{ padding: 'var(--s3)' }}>
                {Object.entries(grouped)
                  .filter(([, roleItems]) => roleItems.length > 0)
                  .map(([role, roleItems]) => (
                  <div key={role} className="stack stack-2" style={{ padding: 'var(--s3)' }}>
                    <div className="row-between">
                      <span className="eyebrow">{ROLE_LABEL[role] ?? role}</span>
                      <span className="xs tabular faint">{roleItems.length}</span>
                    </div>
                    {roleItems.map((item) => (
                      <Link
                        key={item.code}
                        to={`/app/standard/${encodeURIComponent(item.code)}`}
                        className="alert-mini"
                      >
                        <Icon name="file" size={14} />
                        <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                          <span className="xs mono strong">{item.code}</span>
                          <span className="xs faint">
                            {item.title || ''}
                            {item.addedFrom ? ` · from ${item.addedFrom}` : ''}
                          </span>
                        </span>
                        {item.version === 'superseded' && (
                          <span className="badge badge-warn">Superseded</span>
                        )}
                      </Link>
                    ))}
                  </div>
                  ))}
              </div>
            )}
          </section>

          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Recent searches</h2>
              <Link to="/app/query" className="btn btn-ghost btn-sm">
                New <Icon name="chevronRight" size={13} />
              </Link>
            </div>
            {recent.length === 0 ? (
              <div className="card-body">
                <span className="xs muted">
                  {stats
                    ? 'No searches recorded yet. Searches you run appear here.'
                    : 'The engine is not reachable, so the search history cannot be shown.'}
                </span>
              </div>
            ) : (
              <div className="stack" style={{ padding: 'var(--s2)' }}>
                {recent.slice(0, 5).map((q, i) => (
                  <Link key={`${q.timestamp}-${i}`} to="/app/query" className="alert-mini">
                    <Icon name="search" size={14} />
                    <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <span className="xs">{q.query}</span>
                      <span className="xs faint">
                        {q.standard ? `${q.standard}` : 'No match in corpus'}
                      </span>
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="stack stack-4">
          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Gaps in this set</h2>
              {gaps.length > 0 && <span className="badge badge-warn">{gaps.length}</span>}
            </div>
            <div className="card-body stack stack-3">
              {count === 0 ? (
                <span className="xs muted">
                  Checked once the specification has standards in it.
                </span>
              ) : gaps.length === 0 ? (
                <span className="xs muted">
                  No gaps flagged. This checks the shape of the set — whether a test method
                  or certification clause is missing — not whether these are the right
                  standards for the goods.
                </span>
              ) : (
                gaps.map((g, i) => (
                  <div
                    key={i}
                    className={`notice ${g.severity === 'critical' ? 'notice-crit' : 'notice-warn'}`}
                    style={{ margin: 0 }}
                  >
                    <Icon name="alert" size={14} />
                    <span className="xs">{g.text}</span>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Continue</h2>
            </div>
            <div className="stack" style={{ padding: 'var(--s2)' }}>
              {[
                { to: '/app/builder', icon: 'layers', label: 'Spec builder', hint: 'Assemble clause text and freeze the set' },
                { to: '/app/boq', icon: 'upload', label: 'Upload a BOQ', hint: 'Match every line item at once' },
                { to: '/app/audit', icon: 'audit', label: 'Audit a tender', hint: 'Check the citations a draft already makes' },
                { to: '/app/map', icon: 'graph', label: 'Standards map', hint: 'Add allied standards as a branch' },
              ].map((a) => (
                <Link key={a.to} to={a.to} className="alert-mini">
                  <Icon name={a.icon} size={14} />
                  <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <span className="xs strong">{a.label}</span>
                    <span className="xs faint">{a.hint}</span>
                  </span>
                  <Icon name="chevronRight" size={13} />
                </Link>
              ))}
            </div>
          </section>

          <div className="card stack stack-3">
            <span className="eyebrow">Where this is stored</span>
            <p className="xs muted">
              In this browser, via local storage. It survives a reload and a restart, but
              it is not on a server: clearing site data loses it, and it is not visible on
              another machine or to anyone else. Shared projects need user accounts, which
              are not built.
            </p>
            {count > 0 && (
              <button className="btn btn-ghost btn-sm" onClick={spec.clear}>
                Clear this specification
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
