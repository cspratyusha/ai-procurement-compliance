import { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import Icon from './Icon';
import SpecBasket from './SpecBasket';
import { USER, ALERTS } from '../data/mock';
import './shell.css';

/**
 * Five top-level destinations. Everything else nests inside one of them —
 * a workbench needs a short rail, not a directory of every screen.
 */
const NAV = [
  {
    to: '/app/query', icon: 'search', label: 'New query',
    sub: [
      { to: '/app/boq', label: 'Upload tender / BOQ' },
      { to: '/app/builder', label: 'Spec builder' },
      { to: '/app/map', label: 'Related standards map' },
      { to: '/app/certification', label: 'Certification' },
    ],
  },
  { to: '/app/audit', icon: 'audit', label: 'Audit' },
  {
    to: '/app/projects', icon: 'layers', label: 'My projects',
    sub: [
      { to: '/app', label: 'Dashboard', end: true },
      { to: '/app/compliance', label: 'Compliance', adminOnly: true },
      { to: '/app/alerts', label: 'Alerts' },
    ],
  },
  { to: '/app/catalogue', icon: 'graph', label: 'Standards catalogue' },
  {
    to: '/app/admin', icon: 'settings', label: 'Admin', adminOnly: true,
    sub: [{ to: '/app/settings', label: 'Settings' }],
  },
];

export default function Shell({ children, theme, onToggleTheme }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const unread = ALERTS.filter((a) => a.unread).length;
  const isAdmin = USER.role.includes('Admin');

  // Escape closes the mobile drawer — a drawer with no keyboard exit is a trap.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <div className="shell">
      {open && <button className="scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}

      <aside className={`sidebar ${open ? 'is-open' : ''}`}>
        <div className="sidebar-brand">
          <div className="stack" style={{ lineHeight: 1.3 }}>
            <span className="wordmark">StandEng</span>
            <span className="xs faint">Indian Standards for procurement</span>
          </div>
        </div>

        <nav className="sidebar-nav" id="main-nav" aria-label="Main">
          {NAV.filter((i) => !i.adminOnly || isAdmin).map((item) => (
            <div key={item.to} className="nav-group">
              <NavLink
                to={item.to}
                end={item.end}
                onClick={() => setOpen(false)}
                className={({ isActive }) => `nav-item ${isActive ? 'is-active' : ''}`}
              >
                <Icon name={item.icon} size={17} />
                <span>{item.label}</span>
              </NavLink>

              {item.sub && (
                <div className="nav-sub">
                  {item.sub.filter((s) => !s.adminOnly || isAdmin).map((s) => (
                    <NavLink
                      key={s.to}
                      to={s.to}
                      end={s.end}
                      onClick={() => setOpen(false)}
                      className={({ isActive }) => `nav-subitem ${isActive ? 'is-active' : ''}`}
                    >
                      <span>{s.label}</span>
                      {s.label === 'Alerts' && unread > 0 && <span className="nav-count">{unread}</span>}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="org-card">
            <span className="xs faint">Organisation</span>
            <span className="small strong">{USER.org}</span>
            <span className="xs muted">{USER.role}</span>
          </div>
        </div>
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
            className="btn-icon"
            onClick={onToggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={18} />
          </button>

          <button
            className="btn-icon topbar-bell"
            onClick={() => navigate('/app/alerts')}
            aria-label={`Alerts, ${unread} unread`}
          >
            <Icon name="bell" size={18} />
            {unread > 0 && <span className="dot" aria-hidden="true" />}
          </button>

          <div className="topbar-user">
            <span className="avatar" aria-hidden="true">{USER.initials}</span>
            <span className="stack topbar-user-text">
              <span className="xs strong nowrap">{USER.name}</span>
              <span className="xs faint nowrap">{USER.email}</span>
            </span>
          </div>

          <button className="btn-icon" onClick={() => navigate('/')} aria-label="Sign out" title="Sign out">
            <Icon name="logout" size={18} />
          </button>
        </header>

        <main className="shell-content">{children}</main>
      </div>

      <SpecBasket />
    </div>
  );
}
