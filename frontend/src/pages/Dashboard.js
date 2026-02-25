/**
 * pages/Dashboard.js — Main monitoring dashboard.
 *
 * Shows:
 *  - Stat summary (total servers, active/critical/warning alerts)
 *  - Server list filtered by environment
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

const ENVIRONMENTS = ['DEV', 'UAT', 'PROD'];
const REFRESH_INTERVAL = 60_000; // 60 s

export default function Dashboard() {
  const { env: globalEnv } = useApp();

  const [stats, setStats]         = useState(null);
  const [servers, setServers]     = useState([]);
  const [metrics, setMetrics]     = useState([]);
  const [envFilter, setEnvFilter] = useState(globalEnv);
  const [selectedSrv, setSelectedSrv] = useState(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);

  // Keep local filter in sync when the header env switcher changes
  useEffect(() => { setEnvFilter(globalEnv); }, [globalEnv]);

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
  const filteredServers = servers.filter((s) => s.environment === envFilter);

  // ── Render ─────────────────────────────────────────────────────────────
  if (loading) return <div className="spinner">Loading dashboard…</div>;
  if (error)   return <div className="error-box">{error}</div>;

  return (
    <div>
      {/* Page header */}
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">Real-time server &amp; database health</p>
        </div>
        <button className="btn btn-ghost" onClick={fetchDashboard}>↻ Refresh</button>
      </div>

      {/* Summary stats */}
      <div className="grid-4 mb-16">
        <StatCard label="Total Servers"   value={stats?.total_servers ?? 0} />
        <StatCard label="Active Alerts"   value={stats?.active_alerts ?? 0} color="var(--color-warning)" />
        <StatCard label="Critical"         value={stats?.critical_alerts ?? 0} color="var(--color-critical)" />
        <StatCard label="Warning"          value={stats?.warning_alerts ?? 0} color="var(--color-warning)" />
      </div>

      {/* Environment filter */}
      <div className="flex gap-8 mb-16">
        {ENVIRONMENTS.map((env) => (
          <button
            key={env}
            className={`btn ${envFilter === env ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setEnvFilter(env)}
          >
            {env}
          </button>
        ))}
      </div>

      {/* Server grid */}
      <div className="section-title">Servers ({filteredServers.length})</div>
      {filteredServers.length === 0 ? (
        <p className="text-muted">No servers found for this filter.</p>
      ) : (
        <div className="grid-3 mb-16">
          {filteredServers.map((srv) => (
            <ServerCard
              key={srv.id}
              server={srv}
              selected={selectedSrv?.id === srv.id}
              onClick={() => setSelectedSrv(srv.id === selectedSrv?.id ? null : srv)}
            />
          ))}
        </div>
      )}

      {/* Metrics chart (shown when a server is selected) */}
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
