import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams, useLocation, Navigate } from 'react-router-dom';
import Icon from '../components/Icon';
import Logo from '../components/Logo';
import {
  getAuthStatus, setupAccount, registerAccount, signIn, changePassword, requestPasswordReset, resetPassword,
} from '../api/client';
import { useAuth } from '../state/Auth';
import './login.css';

/**
 * Sign in, and on a fresh installation, set up the first administrator.
 *
 * There is no default account. The first person to open a new deployment
 * creates their organisation and becomes its administrator; everyone after
 * that is added by an administrator from Settings, with a temporary password
 * they replace here at first sign-in.
 *
 * Where the engine can send email, a forgotten password is reset here too:
 * "Forgot password?" mails a single-use link, which opens /reset-password.
 */

/** Only paths inside the workbench are followed after sign-in. */
function safeNext(raw) {
  return raw && raw.startsWith('/app') ? raw : '/app';
}

function ErrorLine({ text }) {
  if (!text) return null;
  return (
    <p className="small" role="alert" style={{ color: 'var(--crit)' }}>
      <Icon name="alert" size={13} style={{ display: 'inline', verticalAlign: '-2px', marginRight: 6 }} />
      {text}
    </p>
  );
}

function Field({ id, label, hint, ...props }) {
  return (
    <div className="field">
      <label className="label" htmlFor={id}>{label}</label>
      <input id={id} className="input" {...props} />
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const resetToken = location.pathname === '/reset-password' ? params.get('token') : null;
  const next = safeNext(params.get('next'));
  const { status: session, user, accept, refresh } = useAuth();

  const [status, setStatus] = useState(null);      // /auth/status
  const [mode, setMode] = useState(params.get('mode') === 'register' ? 'register' : 'signin');
  const [statusError, setStatusError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [setup, setSetup] = useState({ org_name: '', org_type: 'ministry', name: '', email: '', password: '', confirm: '' });
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' });
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    getAuthStatus({ signal: controller.signal })
      .then(setStatus)
      .catch((err) => { if (err.name !== 'AbortError') setStatusError(err.message); });
    return () => controller.abort();
  }, []);

  const mustChange = session === 'signed-in' && user?.must_change_password;
  if (session === 'signed-in' && !mustChange && !resetToken) return <Navigate to={next} replace />;

  const minLength = status?.min_password_length ?? 10;

  const submitLogin = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const data = await signIn(email, password);
      accept(data);
      // A temporary password keeps the user on this page for the change step.
      if (!data.user.must_change_password) navigate(next, { replace: true });
      else setPw((p) => ({ ...p, current: password }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submitSetup = async (e) => {
    e.preventDefault();
    setError('');
    if (setup.password !== setup.confirm) {
      setError('The two passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const body = {
        org_name: setup.org_name, org_type: setup.org_type,
        name: setup.name, email: setup.email, password: setup.password,
      };
      const data = status.setup_required ? await setupAccount(body) : await registerAccount(body);
      accept(data);
      navigate('/app', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submitPassword = async (e) => {
    e.preventDefault();
    setError('');
    if (pw.next !== pw.confirm) {
      setError('The two new passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await changePassword(pw.current, pw.next);
      await refresh();
      navigate(next, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submitForgot = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      setNotice((await requestPasswordReset(email)).status);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submitReset = async (e) => {
    e.preventDefault();
    setError('');
    if (pw.next !== pw.confirm) {
      setError('The two new passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const data = await resetPassword(resetToken, pw.next);
      setPw({ current: '', next: '', confirm: '' });
      setNotice(data.status);
      setMode('signin');
      navigate('/login', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  let card;
  if (resetToken) {
    card = (
      <form className="stack stack-5" onSubmit={submitReset}>
        <div className="stack stack-2">
          <h2 style={{ fontSize: 'var(--fs-lg)' }}>Choose a new password</h2>
          <p className="small muted">
            The link in your email works once. Saving a new password signs you out everywhere else.
          </p>
        </div>
        <Field id="r-new" label="New password" type="password" autoComplete="new-password"
          hint={`At least ${minLength} characters, with upper and lower case letters and a number.`}
          value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} required minLength={minLength} />
        <Field id="r-confirm" label="Confirm new password" type="password" autoComplete="new-password"
          value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} required />
        <ErrorLine text={error} />
        <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? <><span className="spinner" /> Saving</> : 'Save new password'}
        </button>
      </form>
    );
  } else if (mustChange) {
    card = (
      <form className="stack stack-5" onSubmit={submitPassword}>
        <div className="stack stack-2">
          <h2 style={{ fontSize: 'var(--fs-lg)' }}>Choose your password</h2>
          <p className="small muted">
            You signed in with a temporary password from your administrator. Replace it with one
            only you know before continuing.
          </p>
        </div>
        <Field id="pw-current" label="Temporary password" type="password" autoComplete="current-password"
          value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} required />
        <Field id="pw-new" label="New password" type="password" autoComplete="new-password"
          hint={`At least ${minLength} characters, with upper and lower case letters and a number.`}
          value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} required minLength={minLength} />
        <Field id="pw-confirm" label="Confirm new password" type="password" autoComplete="new-password"
          value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} required />
        <ErrorLine text={error} />
        <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? <><span className="spinner" /> Saving</> : 'Save password and continue'}
        </button>
      </form>
    );
  } else if (statusError) {
    card = (
      <div className="stack stack-4">
        <h2 style={{ fontSize: 'var(--fs-lg)' }}>The standards engine is not reachable</h2>
        <p className="small muted">{statusError}</p>
        <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    );
  } else if (!status) {
    card = (
      <div className="row center" style={{ justifyContent: 'center', padding: 'var(--s6)' }} aria-busy="true">
        <span className="spinner" />
      </div>
    );
  } else if (status.setup_required || (mode === 'register' && status.registration_open)) {
    const firstRun = status.setup_required;
    card = (
      <form className="stack stack-5" onSubmit={submitSetup}>
        <div className="stack stack-2">
          <h2 style={{ fontSize: 'var(--fs-lg)' }}>{firstRun ? 'Set up StandEng' : 'Create an account'}</h2>
          <p className="small muted">
            {firstRun
              ? 'This installation has no accounts yet. Create your organisation and its administrator account.'
              : 'This creates a new organisation with you as its administrator.'}
            {' '}You can add colleagues from Settings afterwards.
            {!firstRun && ' Joining an organisation that already uses StandEng? Ask its administrator to add you instead.'}
          </p>
        </div>
        <Field id="s-org" label="Organisation name" value={setup.org_name} autoComplete="organization"
          onChange={(e) => setSetup({ ...setup, org_name: e.target.value })} required
          placeholder="e.g. Ministry of Consumer Affairs" />
        <div className="field">
          <label className="label" htmlFor="s-type">Organisation type</label>
          <select id="s-type" className="select" value={setup.org_type}
            onChange={(e) => setSetup({ ...setup, org_type: e.target.value })}>
            {Object.entries(status.org_types).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </div>
        <Field id="s-name" label="Your full name" value={setup.name} autoComplete="name"
          onChange={(e) => setSetup({ ...setup, name: e.target.value })} required />
        <Field id="s-email" label="Official email" type="email" value={setup.email} autoComplete="username"
          onChange={(e) => setSetup({ ...setup, email: e.target.value })} required placeholder="name@department.gov.in" />
        <Field id="s-password" label="Password" type="password" value={setup.password} autoComplete="new-password"
          hint={`At least ${minLength} characters, with upper and lower case letters and a number.`}
          onChange={(e) => setSetup({ ...setup, password: e.target.value })} required minLength={minLength} />
        <Field id="s-confirm" label="Confirm password" type="password" value={setup.confirm} autoComplete="new-password"
          onChange={(e) => setSetup({ ...setup, confirm: e.target.value })} required />
        <ErrorLine text={error} />
        <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? <><span className="spinner" /> Creating</> : 'Create account'}
        </button>
        {!firstRun && (
          <p className="small muted" style={{ textAlign: 'center' }}>
            Already have an account?{' '}
            <button type="button" className="link-button" onClick={() => { setMode('signin'); setError(''); }}>
              Sign in
            </button>
          </p>
        )}
      </form>
    );
  } else if (mode === 'forgot' && status.password_reset_by_email) {
    card = (
      <form className="stack stack-5" onSubmit={submitForgot}>
        <div className="stack stack-2">
          <h2 style={{ fontSize: 'var(--fs-lg)' }}>Reset your password</h2>
          <p className="small muted">
            Enter the email you sign in with. If it has an account, a link to choose a new password
            arrives within a few minutes and works for one hour.
          </p>
        </div>
        <Field id="f-email" label="Official email" type="email" value={email} autoComplete="username"
          onChange={(e) => setEmail(e.target.value)} required placeholder="name@department.gov.in" autoFocus />
        {notice && <p className="small" role="status">{notice}</p>}
        <ErrorLine text={error} />
        <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? <><span className="spinner" /> Sending</> : 'Email me a reset link'}
        </button>
        <p className="small muted" style={{ textAlign: 'center' }}>
          <button type="button" className="link-button"
            onClick={() => { setMode('signin'); setError(''); setNotice(''); }}>
            Back to sign in
          </button>
        </p>
      </form>
    );
  } else {
    card = (
      <form className="stack stack-5" onSubmit={submitLogin}>
        <div className="stack stack-2">
          <h2 style={{ fontSize: 'var(--fs-lg)' }}>Sign in</h2>
          <p className="small muted">
            Sign in with your email and password.
            {status.password_reset_by_email ? (
              <>
                {' '}
                <button type="button" className="link-button"
                  onClick={() => { setMode('forgot'); setError(''); setNotice(''); }}>
                  Forgot password?
                </button>
              </>
            ) : (
              <> Forgotten your password? Your organisation&rsquo;s administrator can reset it from Settings.</>
            )}
          </p>
          {notice && <p className="small" role="status">{notice}</p>}
        </div>
        <Field id="email" label="Official email" type="email" data-demo-target="email" value={email}
          autoComplete="username" onChange={(e) => setEmail(e.target.value)} required
          placeholder="name@department.gov.in" autoFocus />
        <Field id="password" label="Password" type="password" data-demo-target="password" value={password}
          autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} required />
        <ErrorLine text={error} />
        <button className="btn btn-primary" type="submit" data-demo-target="sign-in" disabled={busy}
          style={{ width: '100%' }}>
          {busy ? <><span className="spinner" /> Signing in</> : 'Sign in'}
        </button>
        {status.registration_open && (
          <p className="small muted" style={{ textAlign: 'center' }}>
            New to StandEng?{' '}
            <button type="button" className="link-button" data-demo-target="register"
              onClick={() => { setMode('register'); setError(''); }}>
              Create an account
            </button>
          </p>
        )}
      </form>
    );
  }

  return (
    <div className="auth">
      <aside className="auth-aside">
        <span className="blob blob-a" aria-hidden="true" />
        <span className="blob blob-b" aria-hidden="true" />
        <div className="stack stack-5">
          <Link to="/" style={{ width: 'fit-content' }}>
            <Logo height={36} />
          </Link>

          <h1 className="auth-quote">
            &ldquo;A tender specification has to survive an audit years after it was written.&rdquo;
          </h1>
          <p className="small muted" style={{ maxWidth: '40ch' }}>
            Every search, upload and decision you make here is recorded in your own activity
            trail, with the standards shown and the action you took.
          </p>

          <div className="auth-marks">
            {[
              { icon: 'shield', text: 'Runs on your own servers, with a local language model' },
              { icon: 'file', text: 'An activity trail for every account' },
              { icon: 'users', text: 'Role-based access for officers, admins and integrators' },
            ].map((m) => (
              <div key={m.text} className="auth-mark">
                <Icon name={m.icon} size={16} />
                <span className="small">{m.text}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>

      <main className="auth-main">
        {/* Stays usable while the guided tour runs: the tour waits here for
            the viewer to sign in with their own account. */}
        <div className="auth-card" data-demo-ignore="true">{card}</div>

        <div
          className="row center"
          style={{ marginTop: 'var(--s5)', gap: 'var(--s4)', justifyContent: 'center' }}
        >
          <Link to="/" className="xs faint" style={{ textDecoration: 'underline' }}>
            Back to overview
          </Link>
        </div>
      </main>
    </div>
  );
}
