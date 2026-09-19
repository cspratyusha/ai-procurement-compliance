import { useState, useEffect, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';

import Shell from './components/Shell';
import { SpecProvider } from './state/SpecStore';

import Landing from './pages/Landing';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Query from './pages/Query';
import BOQ from './pages/BOQ';
import Builder from './pages/Builder';
import StandardDetail from './pages/StandardDetail';
import StandardsMap from './pages/StandardsMap';
import Certification from './pages/Certification';
import Audit from './pages/Audit';
import Explorer from './pages/Explorer';
import Simulator from './pages/Simulator';
import Projects from './pages/Projects';
import Admin from './pages/Admin';
import Alerts from './pages/Alerts';
import Settings from './pages/Settings';

// Charting pulls in Recharts (~400 kB) — split it out so only this route pays for it.
const Compliance = lazy(() => import('./pages/Compliance'));

import './styles/tokens.css';
import './styles/app.css';

/** Reset scroll position on navigation. */
function ScrollTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}

/** Reserves the page's vertical space while a lazy route resolves. */
function PageLoading() {
  return (
    <div className="container page" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      <div className="stack stack-5">
        <div className="skeleton" style={{ height: 28, width: 240 }} />
        <div className="grid grid-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 104 }} />)}
        </div>
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.6fr) minmax(0, 1fr)' }}>
          <div className="skeleton" style={{ height: 340 }} />
          <div className="skeleton" style={{ height: 340 }} />
        </div>
      </div>
    </div>
  );
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      const stored = localStorage.getItem('bis-theme');
      if (stored) return stored;
    } catch {
      /* storage blocked — fall through to system preference */
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('bis-theme', theme);
    } catch {
      /* storage blocked — theme still applies for this session */
    }
  }, [theme]);

  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))];
}

export default function App() {
  const [theme, toggleTheme] = useTheme();

  const app = (page) => (
    <Shell theme={theme} onToggleTheme={toggleTheme}>{page}</Shell>
  );

  return (
    <SpecProvider>
      <BrowserRouter>
        <ScrollTop />
        <Routes>
          <Route path="/" element={<Landing theme={theme} onToggleTheme={toggleTheme} />} />
          <Route path="/login" element={<Login />} />

          {/* Workbench */}
          <Route path="/app"               element={app(<Dashboard />)} />
          <Route path="/app/query"         element={app(<Query />)} />
          <Route path="/app/boq"           element={app(<BOQ />)} />
          <Route path="/app/builder"       element={app(<Builder />)} />
          <Route path="/app/map"           element={app(<StandardsMap />)} />
          <Route path="/app/standard/:code" element={app(<StandardDetail />)} />
          <Route path="/app/certification" element={app(<Certification />)} />
          <Route path="/app/certification/:code" element={app(<Certification />)} />

          {/* Audit */}
          <Route path="/app/audit"         element={app(<Audit />)} />

          {/* Projects & catalogue */}
          <Route path="/app/projects"      element={app(<Projects />)} />
          <Route path="/app/catalogue"     element={app(<Explorer />)} />
          <Route path="/app/simulator"     element={app(<Simulator />)} />
          <Route path="/app/alerts"        element={app(<Alerts />)} />
          <Route path="/app/compliance"    element={app(<Suspense fallback={<PageLoading />}><Compliance /></Suspense>)} />

          {/* Admin */}
          <Route path="/app/admin"         element={app(<Admin />)} />
          <Route path="/app/settings"      element={app(<Settings />)} />

          {/* Legacy path kept so old links resolve */}
          <Route path="/app/explorer" element={<Navigate to="/app/catalogue" replace />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </SpecProvider>
  );
}
