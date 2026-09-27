import { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getMe, getToken, signOut as apiSignOut } from '../api/client';

/**
 * Who is signed in.
 *
 * The session token lives in the API client; this holds the account it
 * belongs to (`{ user, org }`) and keeps the two in step. A 401 from any call
 * means the server ended the session, and the client announces that with a
 * `bis-session-ended` event, which signs this tab out.
 *
 * `status` is 'loading' while a stored token is being checked, then 'signed-in'
 * or 'signed-out'. 'offline' means a token exists but the engine could not be
 * reached to check it; the workbench then says so instead of bouncing the
 * user to a sign-in form they cannot use either.
 */

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [account, setAccount] = useState(null);
  const [status, setStatus] = useState(() => (getToken() ? 'loading' : 'signed-out'));

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setAccount(null);
      setStatus('signed-out');
      return null;
    }
    try {
      const data = await getMe();
      setAccount(data);
      setStatus('signed-in');
      return data;
    } catch (err) {
      if (err.status === 401) {
        setAccount(null);
        setStatus('signed-out');
      } else {
        setStatus('offline');
      }
      return null;
    }
  }, []);

  // Only a stored token needs checking; without one the initial state is already right.
  useEffect(() => { if (getToken()) refresh(); }, [refresh]);

  useEffect(() => {
    const ended = () => { setAccount(null); setStatus('signed-out'); };
    window.addEventListener('bis-session-ended', ended);
    return () => window.removeEventListener('bis-session-ended', ended);
  }, []);

  /** After sign-in or setup: the response already carries `{ user, org }`. */
  const accept = useCallback((data) => {
    setAccount({ user: data.user, org: data.org });
    setStatus('signed-in');
  }, []);

  const signOut = useCallback(async () => {
    await apiSignOut();
    setAccount(null);
    setStatus('signed-out');
  }, []);

  const value = useMemo(() => ({
    status,
    user: account?.user ?? null,
    org: account?.org ?? null,
    isAdmin: account?.user?.role === 'admin',
    accept,
    refresh,
    signOut,
    setAccount,
  }), [status, account, accept, refresh, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

/**
 * Gate for the workbench. Sends a signed-out visitor to sign in and back to
 * where they were going afterwards; holds a new member on the password
 * change their temporary password requires.
 */
export function RequireAuth({ children }) {
  const { status, user } = useAuth();
  const location = useLocation();
  const next = encodeURIComponent(location.pathname + location.search);

  if (status === 'loading') {
    return (
      <div className="auth-gate" aria-busy="true">
        <span className="spinner" />
        <span className="sr-only">Checking your session</span>
      </div>
    );
  }
  if (status === 'offline') {
    return (
      <div className="auth-gate">
        <div className="stack stack-3" style={{ maxWidth: '44ch', textAlign: 'center' }}>
          <h1 style={{ fontSize: 'var(--fs-lg)' }}>The standards engine is not reachable</h1>
          <p className="small muted">
            Your session could not be checked because the engine is not responding. Start the
            backend, then reload this page.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      </div>
    );
  }
  if (status !== 'signed-in') return <Navigate to={`/login?next=${next}`} replace />;
  if (user?.must_change_password) return <Navigate to={`/login?step=password&next=${next}`} replace />;
  return children;
}
