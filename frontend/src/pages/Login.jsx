import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { ROLES } from '../data/mock';
import './login.css';

export default function Login() {
  const navigate = useNavigate();
  const [step, setStep] = useState('credentials');
  const [email, setEmail] = useState('demo@standeng.gov.in');
  const [password, setPassword] = useState('demo-password');
  const [role, setRole] = useState('admin');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submitCredentials = (e) => {
    e.preventDefault();
    if (!email.includes('@')) {
      setError('Enter a valid official email address.');
      return;
    }
    setError('');
    setBusy(true);
    setTimeout(() => { setBusy(false); setStep('role'); }, 700);
  };

  const submitRole = (e) => {
    e.preventDefault();
    setBusy(true);
    setTimeout(() => navigate('/app'), 600);
  };

  return (
    <div className="auth">
      <aside className="auth-aside">
        <div className="stack stack-5">
          <Link to="/" style={{ width: 'fit-content' }}>
            <span className="wordmark">StandEng</span>
          </Link>

          <h1 className="auth-quote">
            &ldquo;A tender specification has to survive an audit years after it was written.&rdquo;
          </h1>
          <p className="small muted" style={{ maxWidth: '40ch' }}>
            Every recommendation this system makes is logged with its query, the candidates shown,
            their scores, the standard versions in force at the time, and the action you took.
          </p>

          <div className="auth-marks">
            {[
              { icon: 'shield', text: 'Deployed inside government infrastructure' },
              { icon: 'file', text: 'Version-stamped audit trail on every query' },
              { icon: 'users', text: 'Role-scoped access and org-wide visibility' },
            ].map((m) => (
              <div key={m.text} className="row" style={{ gap: 'var(--s3)' }}>
                <Icon name={m.icon} size={15} />
                <span className="xs muted">{m.text}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>

      <main className="auth-main">
        <div className="auth-card">
          {step === 'credentials' ? (
            <form className="stack stack-5" onSubmit={submitCredentials}>
              <div className="stack stack-2">
                <h2 style={{ fontSize: 'var(--fs-lg)' }}>Sign in</h2>
                <p className="small muted">Use your official email or departmental single sign-on.</p>
              </div>

              <button type="button" className="btn btn-secondary" style={{ width: '100%' }}>
                <Icon name="key" size={15} />
                Continue with departmental SSO
              </button>

              <div className="auth-or"><span className="xs faint">or sign in with credentials</span></div>

              <div className="field">
                <label className="label" htmlFor="email">Official email</label>
                <input
                  id="email"
                  className="input"
                  type="email"
                  value={email}
                  autoComplete="username"
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@department.gov.in"
                  required
                />
              </div>

              <div className="field">
                <label className="label" htmlFor="password">Password</label>
                <input
                  id="password"
                  className="input"
                  type="password"
                  value={password}
                  autoComplete="current-password"
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <span className="hint">Demo build — any values are accepted.</span>
              </div>

              {error && (
                <p className="small" role="alert" style={{ color: 'var(--crit)' }}>
                  <Icon name="alert" size={13} style={{ display: 'inline', verticalAlign: '-2px', marginRight: 6 }} />
                  {error}
                </p>
              )}

              <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: '100%' }}>
                {busy ? <><span className="spinner" /> Verifying</> : 'Continue'}
              </button>
            </form>
          ) : (
            <form className="stack stack-5" onSubmit={submitRole}>
              <div className="stack stack-2">
                <h2 style={{ fontSize: 'var(--fs-lg)' }}>Select your role</h2>
                <p className="small muted">
                  Your role determines which features and API scopes are available.
                </p>
              </div>

              <fieldset className="stack stack-3" style={{ border: 0, padding: 0, margin: 0 }}>
                <legend className="sr-only">Role</legend>
                {ROLES.map((r) => (
                  <label key={r.id} className={`role-option ${role === r.id ? 'is-selected' : ''}`}>
                    <input
                      type="radio"
                      name="role"
                      value={r.id}
                      checked={role === r.id}
                      onChange={() => setRole(r.id)}
                    />
                    <span className="stack stack-2">
                      <span className="small strong">{r.label}</span>
                      <span className="xs muted">{r.scope}</span>
                    </span>
                  </label>
                ))}
              </fieldset>

              <div className="field">
                <label className="label" htmlFor="org">Organisation</label>
                <select id="org" className="select" defaultValue="mhi">
                  <option value="mhi">Ministry of Heavy Industries</option>
                  <option value="mor">Ministry of Railways</option>
                  <option value="ntpc">NTPC Limited</option>
                  <option value="bhel">Bharat Heavy Electricals Limited</option>
                </select>
              </div>

              <div className="row" style={{ gap: 'var(--s3)' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setStep('credentials')}>
                  <Icon name="chevronLeft" size={15} />
                  Back
                </button>
                <button className="btn btn-primary grow" type="submit" disabled={busy}>
                  {busy ? <><span className="spinner" /> Loading workspace</> : 'Enter workspace'}
                </button>
              </div>
            </form>
          )}
        </div>

        <p className="xs faint center" style={{ marginTop: 'var(--s5)' }}>
          <Link to="/" style={{ textDecoration: 'underline' }}>Back to overview</Link>
        </p>
      </main>
    </div>
  );
}
