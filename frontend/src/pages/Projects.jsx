import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { useSpec } from '../state/SpecStore';
import { PROJECTS, PROJECT_STATUS, TEMPLATES } from '../data/catalogue';
import { AUDITED_TENDERS, RECENT_QUERIES } from '../data/mock';

export default function Projects() {
  const spec = useSpec();

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">My projects</h1>
          <p className="page-sub">
            Saved tenders, reusable spec sets and department templates. A spec set can be reopened,
            amended and re-exported without starting from a blank query.
          </p>
        </div>
        <Link to="/app/query" className="btn btn-primary">
          <Icon name="plus" size={15} /> New project
        </Link>
      </div>

      <div className="grid split" style={{ "--rail": "1fr" }}>
        <div className="stack stack-4">
          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Tenders</h2>
              <span className="badge badge-neutral">{PROJECTS.length}</span>
            </div>
            <div className="scroll-x" tabIndex={0} role="region" aria-label="Saved tender projects">
              <table className="table table-hover">
                <caption className="sr-only">Saved tender projects</caption>
                <thead>
                  <tr>
                    <th scope="col">Project</th>
                    <th scope="col">Standards</th>
                    <th scope="col">Status</th>
                    <th scope="col">Owner</th>
                    <th scope="col">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {PROJECTS.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <button
                          className="build-link small strong"
                          style={{ textAlign: 'left' }}
                          onClick={() => spec.setProject(p.name)}
                        >
                          {p.name}
                        </button>
                      </td>
                      <td className="small tabular">{p.items}</td>
                      <td><span className={`badge ${PROJECT_STATUS[p.status].cls}`}>{PROJECT_STATUS[p.status].label}</span></td>
                      <td className="xs muted nowrap">{p.owner}</td>
                      <td className="xs faint nowrap">{p.updated}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Recent queries</h2>
              <Link to="/app/query" className="btn btn-ghost btn-sm">New <Icon name="chevronRight" size={13} /></Link>
            </div>
            <div className="stack" style={{ padding: 'var(--s2)' }}>
              {RECENT_QUERIES.slice(0, 4).map((q) => (
                <Link key={q.id} to="/app/query" className="alert-mini">
                  <Icon name="search" size={14} />
                  <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <span className="xs">{q.text}</span>
                    <span className="xs faint">
                      {q.standard ? `${q.standard} · ` : ''}{q.time}
                    </span>
                  </span>
                </Link>
              ))}
            </div>
          </section>
        </div>

        <div className="stack stack-4">
          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Reusable templates</h2>
            </div>
            <div className="stack" style={{ padding: 'var(--s2)' }}>
              {TEMPLATES.map((t) => (
                <button key={t.id} className="alert-mini" style={{ width: '100%', textAlign: 'left' }}>
                  <Icon name="layers" size={14} />
                  <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <span className="xs strong">{t.name}</span>
                    <span className="xs faint">{t.items} standards · used {t.uses} times</span>
                  </span>
                  <Icon name="plus" size={13} />
                </button>
              ))}
            </div>
          </section>

          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Audited tenders</h2>
            </div>
            <div className="stack" style={{ padding: 'var(--s2)' }}>
              {AUDITED_TENDERS.map((t) => (
                <Link key={t.id} to="/app/audit" className="alert-mini">
                  <Icon name="audit" size={14} />
                  <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <span className="xs strong" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</span>
                    <span className="xs faint">{t.findings} findings · {t.time}</span>
                  </span>
                  {t.critical > 0 && <span className="badge badge-crit">{t.critical}</span>}
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
