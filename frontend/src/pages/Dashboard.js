/**
 * pages/Dashboard.js — Main monitoring dashboard.
 *
 * Shows:
 *  - Stat summary cards
 *  - Unix Servers tab  (filtered by header env)
 *  - Oracle Databases tab  (filtered by header env)
 *  - Metrics trend chart for a selected server
 *  - Recent open alerts
 */

import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { getDashboard, getMetrics, getServers } from '../api/api';
import { useApp } from '../context/AppContext';
import AlertList from '../components/AlertList';
import MetricsChart from '../components/MetricsChart';
import ServerCard from '../components/ServerCard';

const TABS = [
  { key: 'UNIX',   label: '🖥️ Unix Servers'      },
  { key: 'ORACLE', label: '🗄️ Oracle Databases'  },
];
const REFRESH_INTERVAL = 60_000;

export default function Dashboard() {
  const { env } = useApp();

  const [stats, setStats]             = useState(null);
  const [servers, setServers]         = useState([]);
  const [metrics, setMetrics]         = useState([]);
  const [activeTab, setActiveTab]     = useState('UNIX');
  const [selectedSrv, setSelectedSrv] = useState(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);

  // Reset selected server when env or tab changes
  useEffect(() => { setSelectedSrv(null); }, [env, activeTab]);

  // ── Data fetching ──────────────────────────────────────────────────────
  const fetchDashboard = useCallback(async () => {
    try {
      const [dashRes, srvRes] = await Promise.all([
        getDashboard(),
        getServers({ active_only: true }),
      ]);
      setStats(dashRes.data);
      setServers(srvRes.data);
      setError(null);
    } catch (err) {
      setError(err.message);
      toast.error(`Dashboard load failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchMetrics = useCallback(async (serverId) => {
    if (!serverId) return;
    try {
      const res = await getMetrics({ server_id: serverId, hours: 24, limit: 300 });
      setMetrics(res.data);
    } catch (err) {
      toast.error(`Metrics load failed: ${err.message}`);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    const timer = setInterval(fetchDashboard, REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, [fetchDashboard]);

  useEffect(() => {
    fetchMetrics(selectedSrv?.id);
  }, [selectedSrv, fetchMetrics]);

  // ── Derived data ───────────────────────────────────────────────────────
  // Servers for the active tab, filtered by the header env
  const visibleServers = servers.filter(
    (s) => s.environment === env && s.type === activeTab
  );

  // ── Render ─────────────────────────────────────────────────────────────
  if (loading) return <div className="spinner">Loading dashboard…</div>;
  if (error)   return <div className="error-box">{error}</div>;

  return (
    <div>
      {/* Page header */}
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">Environment: <strong>{env}</strong></p>
        </div>
        <button className="btn btn-ghost" onClick={fetchDashboard}>↻ Refresh</button>
      </div>

      {/* Summary stats */}
      <div className="grid-4 mb-16">
        <StatCard label="Total Servers"  value={stats?.total_servers ?? 0} />
        <StatCard label="Active Alerts"  value={stats?.active_alerts ?? 0}  color="var(--color-warning)" />
        <StatCard label="Critical"       value={stats?.critical_alerts ?? 0} color="var(--color-critical)" />
        <StatCard label="Warning"        value={stats?.warning_alerts ?? 0}  color="var(--color-warning)" />
      </div>

      {/* Unix / Oracle tabs */}
      <div className="tab-bar mb-16">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab ${activeTab === t.key ? 'tab-active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
            <span className="tab-count">
              {servers.filter(s => s.environment === env && s.type === t.key).length}
            </span>
          </button>
        ))}
      </div>

      {/* Server grid */}
      {visibleServers.length === 0 ? (
        <p className="text-muted mb-16">No {activeTab === 'UNIX' ? 'Unix servers' : 'Oracle databases'} in {env}.</p>
      ) : (
        <div className="grid-3 mb-16">
          {visibleServers.map((srv) => (
            <ServerCard
              key={srv.id}
              server={srv}
              selected={selectedSrv?.id === srv.id}
              onClick={() => setSelectedSrv(srv.id === selectedSrv?.id ? null : srv)}
            />
          ))}
        </div>
      )}

      {/* Metrics chart */}
      {selectedSrv && (
        <div className="card mb-16">
          <div className="card-title">Metrics — {selectedSrv.hostname} (last 24 h)</div>
          <MetricsChart metrics={metrics} />
        </div>
      )}

      {/* Recent alerts */}
      <div className="section-title">Recent Alerts</div>
      <div className="card">
        <AlertList
          alerts={stats?.recent_alerts ?? []}
          onRefresh={fetchDashboard}
          compact
        />
      </div>
    </div>
  );
}

// ── Inner helper ──────────────────────────────────────────────────────────
function StatCard({ label, value, color }) {
  return (
    <div className="card">
      <div className="stat-value" style={{ color: color || 'var(--color-text)' }}>{value}</div>
      <div className="stat-label mt-8">{label}</div>
    </div>
  );
}
