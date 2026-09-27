import { useState, useEffect, useCallback } from 'react';
import Icon from '../components/Icon';
import { useAuth } from '../state/Auth';
import {
  updateProfile, changePassword, updateOrg, listMembers, inviteMember, updateMember,
  listApiKeys, createApiKey, revokeApiKey, getActivity, listLanguages, getAuthStatus, BASE_URL,
} from '../api/client';
import './settings.css';
import './query.css';   // .notice

/**
 * Account, organisation, API keys and the activity trail. Every value on this
 * screen is read from and saved to the engine's accounts store.
 */

const KEY_ROLES = new Set(['admin', 'integrator']);

const ACTION_LABEL = {
  'account.setup': 'Set up the installation',
  'account.sign_in': 'Signed in',
  'account.sign_out': 'Signed out',
  'account.profile': 'Updated profile',
  'account.password': 'Changed password',
  'org.update': 'Updated organisation',
  'org.invite': 'Added a member',
  'org.member': 'Changed a member',
  'api_key.create': 'Created an API key',
  'api_key.revoke': 'Revoked an API key',
  'search.query': 'Searched',
  'search.scenario': 'Compared a scenario',
  'document.audit': 'Audited a tender',
  'document.boq': 'Matched a BOQ',
  'result.accept': 'Accepted a result',
  'result.reject': 'Dismissed a result',
  'result.correct': 'Corrected a result',
  'project.create': 'Created a project',
  'project.rename': 'Renamed a project',
  'project.delete': 'Deleted a project',
  'project.freeze': 'Froze a specification',
  'export.doc': 'Downloaded a Word specification',
  'export.pdf': 'Printed a specification',
  'export.clip': 'Copied clause text',
  'export.json': 'Downloaded a JSON record',
};

const ACTIVITY_FILTERS = [
  { id: '', label: 'Everything' },
  { id: 'search.', label: 'Searches' },
  { id: 'document.', label: 'Documents' },
  { id: 'result.', label: 'Decisions on results' },
  { id: 'project.', label: 'Projects' },
  { id: 'export.', label: 'Exports' },
  { id: 'account.', label: 'Sign-in and account' },
];

function when(iso) {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

function Status({ state }) {
  if (!state) return null;
  const ok = state.kind === 'ok';
  return (
    <div className={`notice ${ok ? 'notice-ok' : 'notice-crit'}`} role={ok ? 'status' : 'alert'} style={{ margin: 0 }}>
      <Icon name={ok ? 'checkCircle' : 'alert'} size={14} />
      <span className="xs">{state.text}</span>
    </div>
  );
}

/** A secret shown exactly once, with a copy button. */
function OneTimeSecret({ label, value, note, onDone }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setCopied(true); } catch { /* select it by hand */ }
  };
  return (
    <div className="notice notice-warn stack stack-3" style={{ margin: 0, alignItems: 'stretch' }}>
      <span className="small strong">{label}</span>
      <code className="mono small secret-value">{value}</code>
      <span className="xs">{note}</span>
      <div className="row" style={{ gap: 'var(--s2)' }}>
        <button type="button" className="btn btn-secondary btn-sm" onClick={copy}>
          <Icon name={copied ? 'check' : 'copy'} size={13} /> {copied ? 'Copied' : 'Copy'}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onDone}>I have saved it</button>
      </div>
    </div>
  );
}

/* ------------------------------ Profile ------------------------------ */

function ProfileTab() {
  const { user, org, setAccount } = useAuth();
  const [name, setName] = useState(user.name);
  const [language, setLanguage] = useState(user.language || 'auto');
  const [languages, setLanguages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  useEffect(() => { listLanguages().then(setLanguages); }, []);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setStatus(null);
    try {
      setAccount(await updateProfile({ name, language }));
      setStatus({ kind: 'ok', text: 'Profile saved.' });
    } catch (err) {
      setStatus({ kind: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-2" style={{ alignItems: 'start' }}>
      <form className="card stack stack-5" onSubmit={save}>
        <span className="eyebrow">Profile</span>
        <div className="field">
          <label className="label" htmlFor="p-name">Full name</label>
          <input id="p-name" className="input" value={name} maxLength={120} required
            onChange={(e) => setName(e.target.value)} autoComplete="name" />
        </div>
        <div className="field">
          <label className="label" htmlFor="p-email">Official email</label>
          <input id="p-email" className="input" type="email" value={user.email} readOnly disabled />
          <span className="hint">Your email is your sign-in name. An administrator can change who has access.</span>
        </div>
        <div className="field">
          <label className="label" htmlFor="p-lang">Default query language</label>
          <select id="p-lang" className="select" value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="auto">Detect from the text</option>
            {languages.map((l) => (
              <option key={l.code} value={l.code}>{l.native && l.native !== l.name ? `${l.native} (${l.name})` : l.name}</option>
            ))}
          </select>
          <span className="hint">The search box starts on this language. Queries are translated to English before searching.</span>
        </div>
        <Status state={status} />
        <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }} disabled={busy}>
          {busy ? <><span className="spinner" /> Saving</> : 'Save changes'}
        </button>
      </form>

      <div className="card stack stack-4">
        <span className="eyebrow">Role and access</span>
        <div className="sunk stack stack-2">
          <span className="small strong">{user.role_label}</span>
          <span className="xs muted">
            {{
              admin: 'Manages members, the organisation profile and API keys, and sees the organisation-wide activity trail and engine status.',
              officer: 'Searches, audits tenders, matches BOQs and assembles specifications.',
              integrator: 'Everything an officer can do, plus API keys for connecting portals.',
              private: 'Search, audit and certification lookup.',
            }[user.role]}
          </span>
        </div>
        <p className="xs muted">Roles are changed by your organisation&rsquo;s administrator.</p>
        <hr className="divider" />
        <div className="row-between"><span className="xs faint">Organisation</span><span className="small">{org?.name}</span></div>
        <div className="row-between"><span className="xs faint">Member since</span><span className="small">{when(user.created_at)}</span></div>
        <div className="row-between"><span className="xs faint">Last sign-in</span><span className="small">{when(user.last_login_at)}</span></div>
      </div>
    </div>
  );
}

/* ------------------------------ Security ------------------------------ */

function SecurityTab() {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [minLength, setMinLength] = useState(10);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  useEffect(() => { getAuthStatus().then((s) => setMinLength(s.min_password_length)).catch(() => {}); }, []);

  const save = async (e) => {
    e.preventDefault();
    setStatus(null);
    if (form.next !== form.confirm) {
      setStatus({ kind: 'error', text: 'The two new passwords do not match.' });
      return;
    }
    setBusy(true);
    try {
      await changePassword(form.current, form.next);
      setForm({ current: '', next: '', confirm: '' });
      setStatus({ kind: 'ok', text: 'Password changed. Your other sessions have been signed out.' });
    } catch (err) {
      setStatus({ kind: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card stack stack-5" style={{ maxWidth: 520 }} onSubmit={save}>
      <span className="eyebrow">Change password</span>
      <div className="field">
        <label className="label" htmlFor="c-current">Current password</label>
        <input id="c-current" className="input" type="password" autoComplete="current-password" required
          value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} />
      </div>
      <div className="field">
        <label className="label" htmlFor="c-new">New password</label>
        <input id="c-new" className="input" type="password" autoComplete="new-password" required minLength={minLength}
          value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} />
        <span className="hint">At least {minLength} characters, with upper and lower case letters and a number.</span>
      </div>
      <div className="field">
        <label className="label" htmlFor="c-confirm">Confirm new password</label>
        <input id="c-confirm" className="input" type="password" autoComplete="new-password" required
          value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
      </div>
      <Status state={status} />
      <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }} disabled={busy}>
        {busy ? <><span className="spinner" /> Saving</> : 'Change password'}
      </button>
    </form>
  );
}

/* ---------------------------- Organisation ---------------------------- */

function OrgTab() {
  const { user, org, isAdmin, refresh } = useAuth();
  const [meta, setMeta] = useState(null);
  const [orgForm, setOrgForm] = useState({ name: org.name, type: org.type });
  const [orgStatus, setOrgStatus] = useState(null);
  const [members, setMembers] = useState(null);
  const [membersError, setMembersError] = useState('');
  const [invite, setInvite] = useState({ name: '', email: '', role: 'officer' });
  const [inviteStatus, setInviteStatus] = useState(null);
  const [secret, setSecret] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setMembers((await listMembers()).members); setMembersError(''); } catch (err) { setMembersError(err.message); }
  }, []);

  useEffect(() => {
    load();
    getAuthStatus().then(setMeta).catch(() => {});
  }, [load]);

  const saveOrg = async (e) => {
    e.preventDefault();
    setBusy(true);
    setOrgStatus(null);
    try {
      await updateOrg(orgForm);
      await refresh();
      setOrgStatus({ kind: 'ok', text: 'Organisation saved.' });
    } catch (err) {
      setOrgStatus({ kind: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    setInviteStatus(null);
    try {
      const data = await inviteMember(invite);
      setSecret({ label: `Temporary password for ${data.user.name}`, value: data.temporary_password });
      setInvite({ name: '', email: '', role: 'officer' });
      await load();
    } catch (err) {
      setInviteStatus({ kind: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const change = async (m, changes, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setInviteStatus(null);
    try {
      const data = await updateMember(m.id, changes);
      if (data.temporary_password) {
        setSecret({ label: `New temporary password for ${m.name}`, value: data.temporary_password });
      }
      await load();
    } catch (err) {
      setInviteStatus({ kind: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const roles = meta?.roles ?? {};
  const orgTypes = meta?.org_types ?? {};

  return (
    <div className="grid grid-2" style={{ alignItems: 'start' }}>
      <div className="stack stack-4">
        <form className="card stack stack-5" onSubmit={saveOrg}>
          <span className="eyebrow">Organisation profile</span>
          <div className="field">
            <label className="label" htmlFor="o-name">Organisation name</label>
            <input id="o-name" className="input" value={orgForm.name} disabled={!isAdmin} required maxLength={120}
              onChange={(e) => setOrgForm({ ...orgForm, name: e.target.value })} />
          </div>
          <div className="field">
            <label className="label" htmlFor="o-type">Organisation type</label>
            <select id="o-type" className="select" value={orgForm.type} disabled={!isAdmin}
              onChange={(e) => setOrgForm({ ...orgForm, type: e.target.value })}>
              {Object.entries(orgTypes).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              {!orgTypes[orgForm.type] && <option value={orgForm.type}>{org.type_label}</option>}
            </select>
          </div>
          <Status state={orgStatus} />
          {isAdmin ? (
            <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }} disabled={busy}>Save organisation</button>
          ) : (
            <span className="xs muted">Only an administrator can change these.</span>
          )}
        </form>

        {isAdmin && (
          <form className="card stack stack-4" onSubmit={add}>
            <span className="eyebrow">Add a member</span>
            <p className="xs muted">
              They get a temporary password to pass on, and choose their own at first sign-in.
            </p>
            <div className="field">
              <label className="label" htmlFor="i-name">Full name</label>
              <input id="i-name" className="input" value={invite.name} required maxLength={120}
                onChange={(e) => setInvite({ ...invite, name: e.target.value })} />
            </div>
            <div className="field">
              <label className="label" htmlFor="i-email">Official email</label>
              <input id="i-email" className="input" type="email" value={invite.email} required
                onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
            </div>
            <div className="field">
              <label className="label" htmlFor="i-role">Role</label>
              <select id="i-role" className="select" value={invite.role}
                onChange={(e) => setInvite({ ...invite, role: e.target.value })}>
                {Object.entries(roles).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </div>
            <button className="btn btn-primary btn-sm" style={{ alignSelf: 'flex-start' }} disabled={busy}>
              <Icon name="plus" size={14} /> Add member
            </button>
          </form>
        )}
      </div>

      <div className="card stack stack-4">
        <div className="row-between">
          <span className="eyebrow">Members</span>
          {members && <span className="badge badge-neutral">{members.length}</span>}
        </div>
        {secret && (
          <OneTimeSecret label={secret.label} value={secret.value}
            note="Pass this on privately. It is not shown again; they must replace it when they first sign in."
            onDone={() => setSecret(null)} />
        )}
        <Status state={inviteStatus} />
        {membersError && <span className="xs muted">{membersError}</span>}
        {!members && !membersError && <span className="xs muted">Loading…</span>}
        {(members ?? []).map((m) => (
          <div key={m.id} className="member-row">
            <span className="avatar" aria-hidden="true">{m.initials}</span>
            <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
              <span className="small strong">
                {m.name} {m.id === user.id && <span className="xs faint">(you)</span>}
                {m.disabled && <span className="badge badge-neutral" style={{ marginLeft: 6 }}>Disabled</span>}
                {m.must_change_password && !m.disabled && <span className="badge badge-warn" style={{ marginLeft: 6 }}>Not signed in yet</span>}
              </span>
              <span className="xs faint member-email">{m.email}</span>
              {isAdmin && m.id !== user.id ? (
                <span className="row wrap" style={{ gap: 'var(--s2)' }}>
                  <label className="sr-only" htmlFor={`role-${m.id}`}>Role for {m.name}</label>
                  <select id={`role-${m.id}`} className="select select-sm" value={m.role} disabled={busy}
                    onChange={(e) => change(m, { role: e.target.value })}>
                    {Object.entries(roles).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                  </select>
                  <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
                    onClick={() => change(m, { reset_password: true }, `Reset ${m.name}'s password? Their current sessions end.`)}>
                    Reset password
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
                    onClick={() => change(m, { disabled: !m.disabled }, m.disabled ? null : `Disable ${m.name}? They are signed out at once.`)}>
                    {m.disabled ? 'Enable' : 'Disable'}
                  </button>
                </span>
              ) : (
                <span className="xs faint">{m.role_label} · last sign-in {when(m.last_login_at)}</span>
              )}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------ API keys ------------------------------ */

const ENDPOINTS = [
  { m: 'POST', p: '/retrieve', d: 'Ranked standards for a description' },
  { m: 'POST', p: '/boq', d: 'Standards for every line item of a BOQ file' },
  { m: 'POST', p: '/audit', d: 'Check the citations in a tender file' },
  { m: 'POST', p: '/simulate', d: 'What changes when the requirement changes' },
  { m: 'GET',  p: '/standards/search?q=', d: 'Search the catalogue' },
  { m: 'GET',  p: '/standards/{number}/related', d: 'Allied standards' },
  { m: 'GET',  p: '/standards/{number}/certification', d: 'Certification requirement' },
];

function KeysTab() {
  const { user } = useAuth();
  const [keys, setKeys] = useState(null);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [secret, setSecret] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setKeys((await listApiKeys()).keys); setError(''); } catch (err) { setError(err.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const data = await createApiKey(name);
      setSecret({ label: `API key "${data.key.name}"`, value: data.secret });
      setName('');
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (k) => {
    if (!window.confirm(`Revoke "${k.name}"? Anything using it stops working immediately.`)) return;
    setBusy(true);
    try { await revokeApiKey(k.id); await load(); } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return (
    <div className="stack stack-4">
      <div className="notice notice-info">
        <Icon name="info" size={15} />
        <span className="xs">
          Keys let a portal call the engine without a person signing in. Send one as
          <code className="mono"> Authorization: Bearer sk_…</code> or <code className="mono">X-API-Key</code>.
          It acts with your role, and every call counts against it below.
          {user.role === 'admin' ? ' As an administrator you see every key in the organisation.' : ''}
        </span>
      </div>

      {secret && (
        <OneTimeSecret label={secret.label} value={secret.value}
          note="Copy it now. Only a short prefix is stored in readable form, so it cannot be shown again."
          onDone={() => setSecret(null)} />
      )}

      <div className="card card-flush">
        <form className="card-head" onSubmit={create} style={{ gap: 'var(--s3)', flexWrap: 'wrap' }}>
          <h2 className="card-title">API keys</h2>
          <div className="row" style={{ gap: 'var(--s2)' }}>
            <label className="sr-only" htmlFor="k-name">Key name</label>
            <input id="k-name" className="input input-sm" placeholder="What will use it, e.g. GeM portal"
              value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
            <button className="btn btn-primary btn-sm" disabled={busy}>
              <Icon name="plus" size={14} /> Create key
            </button>
          </div>
        </form>
        {error && <div className="card-body"><span className="xs" style={{ color: 'var(--crit)' }}>{error}</span></div>}
        {keys && keys.length === 0 ? (
          <div className="card-body"><span className="xs muted">No active keys.</span></div>
        ) : (
          <div className="scroll-x" tabIndex={0} role="region" aria-label="API keys">
            <table className="table table-hover">
              <caption className="sr-only">Active API keys</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Key</th>
                  <th scope="col">Owner</th>
                  <th scope="col">Created</th>
                  <th scope="col">Last used</th>
                  <th scope="col">Calls</th>
                  <th scope="col"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {(keys ?? []).map((k) => (
                  <tr key={k.id}>
                    <td className="small strong">{k.name}</td>
                    <td className="mono xs">{k.prefix}…</td>
                    <td className="xs muted nowrap">{k.owner}</td>
                    <td className="xs muted nowrap">{when(k.created_at)}</td>
                    <td className="xs muted nowrap">{k.last_used_at ? when(k.last_used_at) : 'Never'}</td>
                    <td className="small tabular">{k.calls.toLocaleString('en-IN')}</td>
                    <td>
                      <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => revoke(k)}
                        aria-label={`Revoke ${k.name}`}>
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card stack stack-3">
        <div className="row-between">
          <span className="eyebrow">Endpoint reference</span>
          <a className="btn btn-ghost btn-sm" href={`${BASE_URL}/docs`} target="_blank" rel="noreferrer">
            Full API documentation <Icon name="external" size={13} />
          </a>
        </div>
        {ENDPOINTS.map((e) => (
          <div key={e.p} className="endpoint">
            <span className={`badge ${e.m === 'GET' ? 'badge-info' : 'badge-ok'} mono`}>{e.m}</span>
            <span className="mono xs grow">{e.p}</span>
            <span className="xs faint">{e.d}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------ Activity ------------------------------ */

function csvCell(value) {
  const s = String(value ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function ActivityTab() {
  const { isAdmin, org } = useAuth();
  const [scope, setScope] = useState('me');
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState({ key: '', items: [], hasMore: false });
  const [error, setError] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const key = `${scope}|${filter}`;

  useEffect(() => {
    const controller = new AbortController();
    getActivity({ scope, action: filter || undefined, limit: 50, signal: controller.signal })
      .then((data) => { setPage({ key, items: data.items, hasMore: data.has_more }); setError(''); })
      .catch((err) => { if (err.name !== 'AbortError') setError(err.message); });
    return () => controller.abort();
  }, [scope, filter, key]);

  const loading = page.key !== key && !error;
  const items = page.key === key ? page.items : [];

  const more = async () => {
    setLoadingMore(true);
    try {
      const data = await getActivity({ scope, action: filter || undefined, limit: 50, before: items[items.length - 1]?.id });
      setPage({ key, items: [...items, ...data.items], hasMore: data.has_more });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  };

  const exportCsv = () => {
    const rows = [['time', 'user', 'action', 'detail'], ...items.map((i) => [i.at, i.user ?? '', i.action, i.detail])];
    const blob = new Blob([rows.map((r) => r.map(csvCell).join(',')).join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `activity-${scope === 'org' ? 'organisation' : 'mine'}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="card card-flush">
      <div className="card-head" style={{ flexWrap: 'wrap', gap: 'var(--s3)' }}>
        <div className="stack stack-2">
          <h2 className="card-title">Activity trail</h2>
          <span className="xs faint">
            {scope === 'org' ? `Everyone in ${org?.name}` : 'What you have done'}, newest first. Recorded by the engine as it happens.
          </span>
        </div>
        <div className="row wrap" style={{ gap: 'var(--s2)' }}>
          {isAdmin && (
            <>
              <label className="sr-only" htmlFor="a-scope">Whose activity</label>
              <select id="a-scope" className="select select-sm" value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="me">Mine</option>
                <option value="org">Whole organisation</option>
              </select>
            </>
          )}
          <label className="sr-only" htmlFor="a-filter">Kind of activity</label>
          <select id="a-filter" className="select select-sm" value={filter} onChange={(e) => setFilter(e.target.value)}>
            {ACTIVITY_FILTERS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
          </select>
          <button className="btn btn-secondary btn-sm" onClick={exportCsv} disabled={items.length === 0}>
            <Icon name="download" size={13} /> Export CSV
          </button>
        </div>
      </div>
      <div className="stack" style={{ padding: 'var(--s3)' }}>
        {error && <span className="xs" style={{ color: 'var(--crit)', padding: 'var(--s3)' }}>{error}</span>}
        {loading && <span className="xs muted" style={{ padding: 'var(--s3)' }}>Loading…</span>}
        {!loading && !error && items.length === 0 && (
          <span className="xs muted" style={{ padding: 'var(--s3)' }}>Nothing recorded yet.</span>
        )}
        {items.map((l) => (
          <div key={l.id} className="log-row">
            <span className="xs faint mono nowrap log-time">{when(l.at)}</span>
            <span className="log-mark" />
            <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
              <span className="small strong">{ACTION_LABEL[l.action] ?? l.action}</span>
              <span className="xs muted" style={{ overflowWrap: 'anywhere' }}>{l.detail}</span>
            </span>
            {scope === 'org' && <span className="xs faint nowrap">{l.user}</span>}
          </div>
        ))}
        {page.hasMore && page.key === key && (
          <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: 'center' }} onClick={more} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : 'Show older'}
          </button>
        )}
      </div>
    </div>
  );
}

/* ------------------------------- Page ------------------------------- */

export default function Settings() {
  const { user } = useAuth();
  const tabs = [
    { id: 'profile', label: 'Profile' },
    { id: 'security', label: 'Password' },
    { id: 'org', label: 'Organisation' },
    ...(KEY_ROLES.has(user.role) ? [{ id: 'api', label: 'API keys' }] : []),
    { id: 'activity', label: 'Activity' },
  ];
  const [tab, setTab] = useState('profile');

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">
            Your profile and password, your organisation and its members, integration keys, and
            the record of what has been done in this workspace.
          </p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Settings sections">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? 'is-active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="settings-body">
        {tab === 'profile' && <ProfileTab />}
        {tab === 'security' && <SecurityTab />}
        {tab === 'org' && <OrgTab />}
        {tab === 'api' && <KeysTab />}
        {tab === 'activity' && <ActivityTab />}
      </div>
    </div>
  );
}
