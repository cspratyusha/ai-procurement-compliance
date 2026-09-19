import { useState } from 'react';
import Icon from '../components/Icon';
import { USER, ROLES, API_KEYS } from '../data/mock';
import './settings.css';

const TABS = [
  { id: 'profile', label: 'Profile' },
  { id: 'org', label: 'Organisation' },
  { id: 'api', label: 'API keys' },
  { id: 'audit', label: 'Audit trail' },
];

const AUDIT_LOG = [
  { t: '14:22', action: 'Accepted recommendation', detail: 'IS 694:2010 for query "PVC insulated copper cable…"', user: 'Demo User' },
  { t: '14:18', action: 'Query submitted', detail: '4 candidates returned, top confidence 94%', user: 'Demo User' },
  { t: '11:04', action: 'Applied audit fix', detail: 'Tender_HT_Cable_Supply_2026.pdf — Clause 4.2 version corrected', user: 'Demo User' },
  { t: '10:51', action: 'Tender uploaded', detail: 'Tender_HT_Cable_Supply_2026.pdf — 5 findings', user: 'Demo User' },
  { t: 'Yesterday', action: 'Reported standards gap', detail: 'Query "composite insulator mounting bracket" routed to committee', user: 'R. Sharma' },
];

export default function Settings() {
  const [tab, setTab] = useState('profile');

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">
            Profile, organisation configuration, integration keys, and the version-stamped record of
            every action taken in this workspace.
          </p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Settings sections">
        {TABS.map((t) => (
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
        {tab === 'profile' && (
          <div className="grid grid-2" style={{ alignItems: 'start' }}>
            <div className="card stack stack-5">
              <span className="eyebrow">Profile</span>
              <div className="field">
                <label className="label" htmlFor="p-name">Full name</label>
                <input id="p-name" className="input" defaultValue={USER.name} />
              </div>
              <div className="field">
                <label className="label" htmlFor="p-email">Official email</label>
                <input id="p-email" className="input" type="email" defaultValue={USER.email} />
                <span className="hint">Changing this requires re-verification.</span>
              </div>
              <div className="field">
                <label className="label" htmlFor="p-lang">Preferred query language</label>
                <select id="p-lang" className="select" defaultValue="en">
                  <option value="en">English</option>
                  <option value="hi">हिन्दी (Hindi)</option>
                  <option value="ta">தமிழ் (Tamil)</option>
                </select>
              </div>
              <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Save changes</button>
            </div>

            <div className="card stack stack-4">
              <span className="eyebrow">Role &amp; scope</span>
              <div className="sunk stack stack-2">
                <span className="small strong">{USER.role}</span>
                <span className="xs muted">
                  {ROLES.find((r) => r.label === USER.role)?.scope}
                </span>
              </div>
              <p className="xs muted">
                Role changes are made by your organisation administrator. Your role determines which
                navigation items render and which API scopes your token permits.
              </p>
              <hr className="divider" />
              <div className="row-between">
                <span className="xs faint">Organisation</span>
                <span className="small">{USER.org}</span>
              </div>
              <div className="row-between">
                <span className="xs faint">Member since</span>
                <span className="small">12 March 2026</span>
              </div>
            </div>
          </div>
        )}

        {tab === 'org' && (
          <div className="grid grid-2" style={{ alignItems: 'start' }}>
            <div className="card stack stack-5">
              <span className="eyebrow">Organisation profile</span>
              <div className="field">
                <label className="label" htmlFor="o-name">Organisation name</label>
                <input id="o-name" className="input" defaultValue={USER.org} />
              </div>
              <div className="field">
                <label className="label" htmlFor="o-type">Organisation type</label>
                <select id="o-type" className="select" defaultValue="ministry">
                  <option value="ministry">Central Government Ministry</option>
                  <option value="pse">Public Sector Enterprise</option>
                  <option value="state">State Department</option>
                  <option value="private">Private Organisation</option>
                </select>
              </div>
              <div className="field">
                <label className="label" htmlFor="o-threshold">Confidence threshold</label>
                <select id="o-threshold" className="select" defaultValue="0.6">
                  <option value="0.5">0.50 — permissive</option>
                  <option value="0.6">0.60 — balanced (recommended)</option>
                  <option value="0.75">0.75 — strict</option>
                </select>
                <span className="hint">
                  Below this score the engine refuses to recommend and flags the query as a
                  potential standards gap.
                </span>
              </div>
              <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Save configuration</button>
            </div>

            <div className="card stack stack-4">
              <span className="eyebrow">Members</span>
              {[
                { n: 'Demo User', r: 'Department Admin', you: true },
                { n: 'R. Sharma', r: 'Procurement Officer' },
                { n: 'M. Iyer', r: 'Procurement Officer' },
                { n: 'S. Banerjee', r: 'Agency Integrator' },
              ].map((m) => (
                <div key={m.n} className="row" style={{ gap: 'var(--s3)' }}>
                  <span className="avatar">{m.n.split(' ').map((x) => x[0]).join('')}</span>
                  <span className="stack stack-2 grow">
                    <span className="small strong">
                      {m.n} {m.you && <span className="xs faint">(you)</span>}
                    </span>
                    <span className="xs faint">{m.r}</span>
                  </span>
                </div>
              ))}
              <hr className="divider" />
              <button className="btn btn-secondary btn-sm" style={{ alignSelf: 'flex-start' }}>
                <Icon name="plus" size={14} /> Invite member
              </button>
            </div>
          </div>
        )}

        {tab === 'api' && (
          <div className="stack stack-4">
            <div className="notice notice-info">
              <Icon name="info" size={15} />
              <span className="xs">
                Keys authenticate portal integrations against the versioned REST API. Treat them as
                secrets — they carry your organisation&rsquo;s scope.
              </span>
            </div>

            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">API keys</h2>
                <button className="btn btn-primary btn-sm">
                  <Icon name="plus" size={14} /> Generate key
                </button>
              </div>
              <div className="scroll-x" tabIndex={0} role="region" aria-label="API keys">
                <table className="table table-hover">
                  <caption className="sr-only">Active API keys</caption>
                  <thead>
                    <tr>
                      <th scope="col">Name</th>
                      <th scope="col">Key</th>
                      <th scope="col">Created</th>
                      <th scope="col">Last used</th>
                      <th scope="col">Calls</th>
                      <th scope="col"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {API_KEYS.map((k) => (
                      <tr key={k.id}>
                        <td className="small strong">{k.name}</td>
                        <td className="mono xs">{k.prefix}••••••••</td>
                        <td className="xs muted nowrap">{k.created}</td>
                        <td className="xs muted nowrap">{k.lastUsed}</td>
                        <td className="small tabular">{k.calls}</td>
                        <td>
                          <button className="btn btn-ghost btn-sm" aria-label={`Revoke ${k.name}`}>
                            Revoke
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card stack stack-3">
              <span className="eyebrow">Endpoint reference</span>
              {[
                { m: 'POST', p: '/v1/recommend', d: 'Return ranked standards for a description' },
                { m: 'POST', p: '/v1/audit', d: 'Audit a tender document for gaps' },
                { m: 'GET',  p: '/v1/certification/{code}', d: 'Certification requirements for a standard' },
                { m: 'GET',  p: '/v1/standards/{code}/cluster', d: 'Allied standards cluster' },
              ].map((e) => (
                <div key={e.p} className="endpoint">
                  <span className={`badge ${e.m === 'GET' ? 'badge-info' : 'badge-ok'} mono`}>{e.m}</span>
                  <span className="mono xs grow">{e.p}</span>
                  <span className="xs faint">{e.d}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'audit' && (
          <div className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title">Audit trail</h2>
                <span className="xs faint">
                  Every query, candidate set, score, version and action — version-stamped and immutable
                </span>
              </div>
              <button className="btn btn-secondary btn-sm">
                <Icon name="download" size={13} /> Export log
              </button>
            </div>
            <div className="stack" style={{ padding: 'var(--s3)' }}>
              {AUDIT_LOG.map((l, i) => (
                <div key={i} className="log-row">
                  <span className="xs faint mono nowrap" style={{ width: 72, flexShrink: 0 }}>{l.t}</span>
                  <span className="log-mark" />
                  <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                    <span className="small strong">{l.action}</span>
                    <span className="xs muted">{l.detail}</span>
                  </span>
                  <span className="xs faint nowrap">{l.user}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
