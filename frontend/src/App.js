/**
 * App.js — Root component with navigation and routing.
 *
 * Routes:
 *   /            → Dashboard
 *   /alerts      → Alert management
 *   /config      → Threshold configuration
 */

import React from 'react';
import { BrowserRouter as Router, Link, NavLink, Route, Routes } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

import Alerts from './pages/Alerts';
import Config from './pages/Config';
import Dashboard from './pages/Dashboard';

import './App.css';

function App() {
  return (
    <Router>
      <div className="app-wrapper">
        {/* ── Sidebar / Top nav ── */}
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
          <div className="env-badges">
            <span className="badge badge-dev">DEV</span>
            <span className="badge badge-uat">UAT</span>
            <span className="badge badge-prod">PROD</span>
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

        {/* ── Toast notifications ── */}
        <ToastContainer position="bottom-right" autoClose={4000} />
      </div>
    </Router>
  );
}

export default App;
