/**
 * App.js — Root component with navigation, routing and auth gate.
 *
 * Routes (protected):
 *   /            → Dashboard
 *   /alerts      → Alert management
 *   /config      → Threshold configuration
 *
 * Auth is handled via SSO login page → AppContext session.
 */

import React from 'react';
import { BrowserRouter as Router, Link, NavLink, Route, Routes } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

import { AppProvider, useApp } from './context/AppContext';
import Alerts    from './pages/Alerts';
import Config    from './pages/Config';
import Dashboard from './pages/Dashboard';
import Login     from './pages/Login';

import './App.css';

const ENV_COLOR = { DEV: '#3b82f6', UAT: '#8b5cf6', PROD: '#f97316' };
const ENVS = ['DEV', 'UAT', 'PROD'];

// ── Protected shell ──────────────────────────────────────────────────────────
function AppShell() {
  const { user, env, isAuth, logout, setEnv } = useApp();

  if (!isAuth) return <Login />;

  return (
    <div className="app-wrapper">
      {/* ── Top nav ── */}
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-icon">📡</span>
          <span className="brand-name">RecSignal</span>
        </Link>

        <nav className="nav-links">
          <NavLink to="/"       end className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>Dashboard</NavLink>
          <NavLink to="/alerts"     className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>Alerts</NavLink>
          <NavLink to="/config"     className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>Config</NavLink>
        </nav>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* ── Environment switcher ── */}
        <div className="header-env-wrapper">
          <span className="header-env-dot" style={{ background: ENV_COLOR[env] }} />
          <select
            className="header-env-select"
            value={env}
            onChange={e => setEnv(e.target.value)}
            title="Switch active environment"
          >
            {ENVS.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        </div>

        {/* ── User info + logout ── */}
        <div className="header-user">
          <span className="header-avatar">{user?.name?.[0] ?? '?'}</span>
          <div className="header-user-info">
            <span className="header-user-name">{user?.name}</span>
            <span className="header-user-role">{user?.role}</span>
          </div>
          <button className="header-logout-btn" onClick={logout} title="Sign out">
            ⏻
          </button>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="app-main">
        <Routes>
          <Route path="/"       element={<Dashboard />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/config" element={<Config />} />
        </Routes>
      </main>

      <ToastContainer position="bottom-right" autoClose={4000} />
    </div>
  );
}

// ── Root ─────────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <AppProvider>
      <Router>
        <AppShell />
      </Router>
    </AppProvider>
  );
}
