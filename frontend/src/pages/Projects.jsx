import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { useSpec, ROLE_LABEL } from '../state/SpecStore';
import { listProjects, deleteProject, getActivity } from '../api/client';
import './query.css';   // .notice, shared with the query screen

/**
 * The signed-in user's specifications.
 *
 * Every project is saved on the server under the user's account. One of them
 * is active: it is the spec basket that the search, catalogue and map screens
 * add to. Opening another project here makes it the basket.
 */

const STATUS = {
  frozen: { label: 'Frozen', cls: 'badge-ok' },
  draft:  { label: 'Draft',  cls: 'badge-warn' },
};

const SAVE_LABEL = {
  saved: 'Saved',
  saving: 'Saving',
  error: 'Not saved, check the connection',
};

function when(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

export default function Projects() {
  const spec = useSpec();
  const [projects, setProjects] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [recent, setRecent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [renaming, setRenaming] = useState(null);

  const { list, grouped, gaps, frozen, project, count, projectId, saveState } = spec;

  const loadProjects = useCallback(async (signal) => {
    try {
      const data = await listProjects({ signal });
      setProjects(data.projects);
      setLoadError('');
    } catch (err) {
      if (err.name !== 'AbortError') setLoadError(err.message);
    }
  }, []);

  // Reload the list when the active project changes or finishes saving, so
  // counts and "updated" times match what is on the server.
  useEffect(() => {
    const controller = new AbortController();
    loadProjects(controller.signal);
    return () => controller.abort();
  }, [loadProjects, projectId, saveState]);

  useEffect(() => {
    const controller = new AbortController();
    getActivity({ action: 'search.', limit: 5, signal: controller.signal })
      .then((data) => setRecent(data.items))
      .catch(() => setRecent([]));
    return () => controller.abort();
  }, []);

  const run = async (fn) => {
    setBusy(true);
    setActionError('');
    try { await fn(); await loadProjects(); } catch (err) { setActionError(err.message); } finally { setBusy(false); }
  };

  const createNew = () => run(() => spec.newProject('Untitled specification'));
  const open = (id) => run(() => spec.switchProject(id));
  const remove = (p) => {
    if (!window.confirm(`Delete "${p.name}"? This cannot be undone.`)) return;
    run(async () => {
      await deleteProject(p.id);
      if (p.id === projectId) await spec.reloadActive();
    });
  };
  const saveName = (e) => {
    e.preventDefault();
    const name = renaming.trim();
    if (name) spec.setProject(name);
    setRenaming(null);
  };

  const others = (projects ?? []).filter((p) => p.id !== projectId);

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="projects-title">My projects</h1>
          <p className="page-sub">
            Each project is one specification you are assembling, saved to your account. The
            active project is the basket that search, the catalogue and the map add to.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={createNew} disabled={busy}>
          <Icon name="plus" size={15} /> New project
        </button>
      </div>

      {actionError && (
        <div className="notice notice-crit" role="alert"><Icon name="alert" size={14} /><span className="xs">{actionError}</span></div>
      )}

      <div className="grid split" style={{ '--rail': '340px' }}>
        <div className="stack stack-4">
          <section className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2" style={{ minWidth: 0 }}>
                {renaming !== null ? (
                  <form className="row" style={{ gap: 'var(--s2)' }} onSubmit={saveName}>
                    <label className="sr-only" htmlFor="project-name">Project name</label>
                    <input id="project-name" className="input" value={renaming} autoFocus maxLength={120}
                      onChange={(e) => setRenaming(e.target.value)} />
                    <button className="btn btn-primary btn-sm" type="submit">Save</button>
                    <button className="btn btn-ghost btn-sm" type="button" onClick={() => setRenaming(null)}>Cancel</button>
                  </form>
                ) : (
                  <div className="row" style={{ gap: 'var(--s2)' }}>
                    <h2 className="card-title">{project || 'Current specification'}</h2>
                    {spec.loaded && (
                      <button type="button" className="btn-icon" aria-label="Rename project" title="Rename"
                        onClick={() => setRenaming(project || '')}>
                        <Icon name="edit" size={14} />
                      </button>
                    )}
                  </div>
                )}
                <span className="xs faint">
                  Active project · {SAVE_LABEL[saveState]}
                  {frozen && ` · Frozen ${new Date(frozen.at).toLocaleString('en-IN')}${frozen.label ? `, ${frozen.label}` : ''}`}
                </span>
              </div>
              <div className="row" style={{ gap: 'var(--s2)' }}>
                <span className={`badge ${frozen ? STATUS.frozen.cls : STATUS.draft.cls}`}>
                  {frozen ? STATUS.frozen.label : STATUS.draft.label}
                </span>
                <span className="badge badge-neutral">{count}</span>
              </div>
            </div>

            {!spec.loaded ? (
              <div className="card-body"><span className="xs muted">
                {saveState === 'error' ? 'Your projects could not be loaded. Check that the engine is running.' : 'Loading your project…'}
              </span></div>
            ) : count === 0 ? (
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
                {list.length > 0 && (
                  <div className="row" style={{ gap: 'var(--s2)', padding: 'var(--s3)' }}>
                    <Link to="/app/builder" className="btn btn-secondary btn-sm">Open in spec builder</Link>
                    <button type="button" className="btn btn-ghost btn-sm"
                      onClick={() => { if (window.confirm('Remove every standard from this project?')) spec.clear(); }}>
                      Empty this project
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>

          <section className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Other projects</h2>
              {projects && <span className="badge badge-neutral">{others.length}</span>}
            </div>
            {loadError ? (
              <div className="card-body"><span className="xs muted">{loadError}</span></div>
            ) : !projects ? (
              <div className="card-body"><span className="xs muted">Loading…</span></div>
            ) : others.length === 0 ? (
              <div className="card-body">
                <span className="xs muted">
                  No other projects. Start a new one for each tender, so each keeps its own
                  standards and freeze record.
                </span>
              </div>
            ) : (
              <div className="stack" style={{ padding: 'var(--s2)' }}>
                {others.map((p) => (
                  <div key={p.id} className="alert-mini" style={{ cursor: 'default' }}>
                    <Icon name="layers" size={14} />
                    <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <span className="xs strong">{p.name}</span>
                      <span className="xs faint">
                        {p.item_count} standard{p.item_count === 1 ? '' : 's'}
                        {p.frozen ? ' · Frozen' : ''} · Updated {when(p.updated_at)}
                      </span>
                    </span>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => open(p.id)}>
                      Open
                    </button>
                    <button type="button" className="btn-icon" disabled={busy} aria-label={`Delete ${p.name}`}
                      title="Delete" onClick={() => remove(p)}>
                      <Icon name="trash" size={14} />
                    </button>
                  </div>
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
                  No gaps flagged. This checks the shape of the set, whether a test method
                  or certification clause is missing, not whether these are the right
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
              <h2 className="card-title">Your recent searches</h2>
              <Link to="/app/query" className="btn btn-ghost btn-sm">
                New <Icon name="chevronRight" size={13} />
              </Link>
            </div>
            {!recent || recent.length === 0 ? (
              <div className="card-body">
                <span className="xs muted">
                  {recent ? 'No searches yet. Searches you run appear here.' : 'Loading…'}
                </span>
              </div>
            ) : (
              <div className="stack" style={{ padding: 'var(--s2)' }}>
                {recent.map((q) => (
                  <Link key={q.id} to={`/app/query?q=${encodeURIComponent(q.meta?.query ?? '')}`} className="alert-mini">
                    <Icon name="search" size={14} />
                    <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                      <span className="xs">{q.meta?.query ?? q.detail}</span>
                      <span className="xs faint">
                        {q.meta?.top ? q.meta.top : 'No match'} · {when(q.at)}
                      </span>
                    </span>
                  </Link>
                ))}
              </div>
            )}
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
        </div>
      </div>
    </div>
  );
}
