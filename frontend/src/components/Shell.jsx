import { useState, useEffect, useRef } from 'react';
import { Link, NavLink, useNavigate, useLocation } from 'react-router-dom';
import Icon from './Icon';
import Logo from './Logo';
import SpecBasket from './SpecBasket';
import { StartDemoButton } from '../demo/DemoProvider';
import { USER } from '../data/mock';
import { getAlerts } from '../api/client';
import './shell.css';

/**
 * Five top-level destinations. Everything else nests inside one of them —
 * a workbench needs a short rail, not a directory of every screen.
 */
// `short` is the label under the icon when the sidebar is collapsed to a rail.
const NAV = [
  {
    to: '/app/query', icon: 'search', label: 'New query', short: 'Search',
    sub: [
      { to: '/app/boq', label: 'Upload tender / BOQ' },
      { to: '/app/builder', label: 'Spec builder' },
      { to: '/app/tender', label: 'Tender builder' },
      { to: '/app/map', label: 'Related standards map' },
      { to: '/app/certification', label: 'Certification' },
    ],
  },
  { to: '/app/audit', icon: 'audit', label: 'Audit', short: 'Audit' },
  {
    to: '/app/projects', icon: 'layers', label: 'My projects', short: 'Projects',
    sub: [
      { to: '/app', label: 'Dashboard', end: true },
      { to: '/app/compliance', label: 'Corpus health', adminOnly: true },
      { to: '/app/alerts', label: 'Standards hygiene' },
    ],
  },
  { to: '/app/catalogue', icon: 'graph', label: 'Standards catalogue', short: 'Catalogue' },
  {
    to: '/app/admin', icon: 'settings', label: 'Admin', short: 'Admin', adminOnly: true,
    sub: [{ to: '/app/settings', label: 'Settings' }],
  },
];

/**
 * The account control: avatar and name only, with everything else (email,
 * organisation, the guided demo, sign out) one click away. Closes on an
 * outside click, on Escape, and after choosing an item.
 */
function ProfileMenu({ onSignOut }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => {
      if (e.key === 'Escape') { setOpen(false); triggerRef.current?.focus(); }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const firstName = USER.name.split(' ')[0];

  return (
    <div className="profile" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`profile-trigger ${open ? 'is-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="profile-panel"
      >
        <span className="avatar" aria-hidden="true">{USER.initials}</span>
        <span className="profile-name">{firstName}</span>
        <Icon name="chevronDown" size={15} className="profile-chevron" />
      </button>

      {open && (
        <div className="profile-panel fade-in" id="profile-panel">
          <div className="profile-head">
            <span className="avatar avatar-lg" aria-hidden="true">{USER.initials}</span>
            <span className="stack" style={{ minWidth: 0 }}>
              <span className="small strong">{USER.name}</span>
              <span className="xs muted profile-email">{USER.email}</span>
            </span>
          </div>

          <div className="profile-org">
            <Icon name="users" size={15} />
            <span className="stack" style={{ minWidth: 0 }}>
              <span className="xs strong">{USER.org}</span>
              <span className="xs faint">{USER.role}</span>
            </span>
          </div>

          <hr className="divider" />

          <div onClick={() => setOpen(false)}>
            <StartDemoButton className="profile-item" label="Start guided demo" />
          </div>
          <button type="button" className="profile-item" onClick={() => { setOpen(false); onSignOut(); }}>
            <Icon name="logout" size={16} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/** A group is "current" when its own route or any of its sub-routes is open. */
const inGroup = (item, pathname) =>
  pathname === item.to || (item.sub ?? []).some((s) => pathname === s.to);

export default function Shell({ children }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isAdmin = USER.role.includes('Admin');

  // Desktop sidebar can fold to an icon rail. Remembered per browser; a
  // blocked storage just means it starts expanded each visit.
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('bis-sidebar') === 'collapsed'; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem('bis-sidebar', collapsed ? 'collapsed' : 'expanded'); } catch { /* storage blocked */ }
  }, [collapsed]);

  // The count on the bell is the number of findings that would actually
  // invalidate a tender clause -- superseded editions whose replacement the
  // corpus can name. It was a fixture ("3 unread") until the alerts screen
  // became real; a badge that disagrees with the screen it links to is worse
  // than no badge, so it is fetched rather than assumed.
  //
  // Failure is silent and shows nothing. A backend that is down is not a
  // reason to assert a count, in either direction.
  const [critical, setCritical] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getAlerts({ signal: controller.signal })
      .then((data) => setCritical(data.critical_count ?? 0))
      .catch(() => { /* engine unreachable -- show no badge rather than a guess */ });
    return () => controller.abort();
  }, []);

  // Escape closes the mobile drawer — a drawer with no keyboard exit is a trap.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <div className={`shell ${collapsed ? 'is-collapsed' : ''}`}>
      {open && <button className="scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}

      <aside className={`sidebar ${open ? 'is-open' : ''}`}>
        <div className="sidebar-brand">
          <Link to="/" className="brand-link" aria-label="StandEng home" title="Home">
            <Logo height={30} />
          </Link>
          <button
            type="button"
            className="btn-icon sidebar-collapse"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!collapsed}
            aria-controls="main-nav"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <Icon name="panelLeft" size={18} />
          </button>
        </div>

        <nav className="sidebar-nav" id="main-nav" aria-label="Main">
          {NAV.filter((i) => !i.adminOnly || isAdmin).map((item) => (
            <div key={item.to} className="nav-group">
              <NavLink
                to={item.to}
                end={item.end}
                onClick={() => setOpen(false)}
                data-demo-target={`nav-${item.to.replace(/^\/app\/?/, '') || 'dashboard'}`}
                title={collapsed ? item.label : undefined}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'is-active' : ''} ${inGroup(item, pathname) ? 'in-group' : ''}`}
              >
                <span className="nav-icon"><Icon name={item.icon} size={18} /></span>
                <span className="nav-label">{item.label}</span>
                <span className="nav-short" aria-hidden="true">{item.short}</span>
              </NavLink>

              {item.sub && (
                <div className="nav-sub">
                  {item.sub.filter((s) => !s.adminOnly || isAdmin).map((s) => (
                    <NavLink
                      key={s.to}
                      to={s.to}
                      end={s.end}
                      onClick={() => setOpen(false)}
                      data-demo-target={`nav-${s.to.replace(/^\/app\/?/, '') || 'dashboard'}`}
                      className={({ isActive }) => `nav-subitem ${isActive ? 'is-active' : ''}`}
                    >
                      <span>{s.label}</span>
                      {s.label === 'Standards hygiene' && critical > 0 && <span className="nav-count">{critical}</span>}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </aside>

      <div className="shell-main">
        <header className="topbar">
          <button
            className="btn-icon nav-toggle"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? 'Close navigation' : 'Open navigation'}
            aria-expanded={open}
            aria-controls="main-nav"
          >
            <Icon name={open ? 'x' : 'menu'} size={19} />
          </button>

          <div className="grow" />

          <button
            className="btn-icon topbar-bell"
            onClick={() => navigate('/app/alerts')}
            aria-label={`Alerts, ${critical} unread`}
            title="Standards hygiene alerts"
          >
            <Icon name="bell" size={18} />
            {critical > 0 && <span className="dot" aria-hidden="true" />}
          </button>

          <ProfileMenu onSignOut={() => navigate('/')} />
        </header>

        <main className="shell-content">{children}</main>
      </div>

      <SpecBasket />
    </div>
  );
}
