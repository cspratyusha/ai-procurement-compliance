import { useEffect, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';

import Shell from './components/Shell';
import { SpecProvider } from './state/SpecStore';
import { AuthProvider, RequireAuth, useAuth } from './state/Auth';
import { DemoProvider } from './demo/DemoProvider';

// The pages a visit starts on load with the app; every other screen loads the
// first time it is opened, so the first page does not wait for all of them.
import Landing from './pages/Landing';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Query from './pages/Query';

const BOQ = lazy(() => import('./pages/BOQ'));
const Builder = lazy(() => import('./pages/Builder'));
const TenderBuilder = lazy(() => import('./pages/TenderBuilder'));
const StandardDetail = lazy(() => import('./pages/StandardDetail'));
const StandardsMap = lazy(() => import('./pages/StandardsMap'));
const Certification = lazy(() => import('./pages/Certification'));
const Audit = lazy(() => import('./pages/Audit'));
const Explorer = lazy(() => import('./pages/Explorer'));
const Simulator = lazy(() => import('./pages/Simulator'));
const Projects = lazy(() => import('./pages/Projects'));
const Admin = lazy(() => import('./pages/Admin'));
const Alerts = lazy(() => import('./pages/Alerts'));
const Settings = lazy(() => import('./pages/Settings'));
// Charting pulls in Recharts (~400 kB), so only this route pays for it.
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

// The interface is light-only (Material You light scheme). Clear any theme a
// previous build persisted so an old "dark" preference cannot linger.
try { localStorage.removeItem('bis-theme'); } catch { /* storage blocked */ }

/** Admin-only screens: anyone else is sent to the dashboard, not shown a 403. */
function AdminOnly({ children }) {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <Navigate to="/app" replace />;
}

export default function App() {
  const app = (page) => (
    <RequireAuth><Shell><Suspense fallback={<PageLoading />}>{page}</Suspense></Shell></RequireAuth>
  );
  const admin = (page) => app(<AdminOnly>{page}</AdminOnly>);

  return (
    <BrowserRouter>
      <AuthProvider>
      <SpecProvider>
        <ScrollTop />
        {/* Demo Mode wraps the routes because its engine navigates through
            react-router. It renders nothing until the demo is started. */}
        <DemoProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/reset-password" element={<Login />} />

            {/* Workbench */}
            <Route path="/app"               element={app(<Dashboard />)} />
            <Route path="/app/query"         element={app(<Query />)} />
            <Route path="/app/boq"           element={app(<BOQ />)} />
            <Route path="/app/builder"       element={app(<Builder />)} />
            <Route path="/app/tender"        element={app(<TenderBuilder />)} />
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
            <Route path="/app/compliance"    element={admin(<Compliance />)} />

            {/* Admin */}
            <Route path="/app/admin"         element={admin(<Admin />)} />
            <Route path="/app/settings"      element={app(<Settings />)} />

            {/* Legacy path kept so old links resolve */}
            <Route path="/app/explorer" element={<Navigate to="/app/catalogue" replace />} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </DemoProvider>
      </SpecProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
