/**
 * pages/Alerts.js — Full alert management page.
 *
 * Features:
 *  - Filter by status, severity, environment
 *  - Acknowledge individual alerts
 *  - Resolve individual alerts
 *  - Bulk acknowledge all open alerts
 */

import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { acknowledgeAlert, getAlerts, resolveAlert } from '../api/api';
import AlertList from '../components/AlertList';

const STATUS_OPTIONS    = ['', 'OPEN', 'ACKNOWLEDGED', 'RESOLVED'];
const SEVERITY_OPTIONS  = ['', 'CRITICAL', 'WARNING'];
const ENV_OPTIONS       = ['', 'PROD', 'UAT', 'DEV'];

export default function Alerts() {
  const [alerts, setAlerts]         = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [statusFilter, setStatus]   = useState('OPEN');
  const [severityFilter, setSev]    = useState('');
  const [envFilter, setEnv]         = useState('');

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 500 };
      if (statusFilter)   params.status      = statusFilter;
      if (severityFilter) params.severity    = severityFilter;
      if (envFilter)      params.environment = envFilter;

      const res = await getAlerts(params);
      setAlerts(res.data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, severityFilter, envFilter]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  // ── Handlers ────────────────────────────────────────────────────────────

  const handleAcknowledge = async (alertId) => {
    const user = prompt('Acknowledge as (enter your name):');
    if (!user) return;
    try {
      await acknowledgeAlert(alertId, user);
      toast.success(`Alert #${alertId} acknowledged`);
      fetchAlerts();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleResolve = async (alertId) => {
    if (!window.confirm(`Resolve alert #${alertId}?`)) return;
    try {
      await resolveAlert(alertId);
      toast.success(`Alert #${alertId} resolved`);
      fetchAlerts();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleBulkAcknowledge = async () => {
    const openAlerts = alerts.filter((a) => a.status === 'OPEN');
    if (!openAlerts.length) { toast.info('No open alerts to acknowledge.'); return; }
    const user = prompt(`Acknowledge ${openAlerts.length} open alerts as (enter your name):`);
    if (!user) return;
    try {
      await Promise.all(openAlerts.map((a) => acknowledgeAlert(a.id, user)));
      toast.success(`${openAlerts.length} alerts acknowledged`);
      fetchAlerts();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div>
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">Alert Management</h1>
          <p className="page-sub">{alerts.length} alert(s) matching current filters</p>
        </div>
        <div className="flex gap-8">
          <button className="btn btn-ghost" onClick={fetchAlerts}>↻ Refresh</button>
          <button className="btn btn-warning" onClick={handleBulkAcknowledge}>
            Acknowledge All Open
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card mb-16">
        <div className="flex gap-8 flex-wrap">
          <div>
            <label className="text-muted text-small">Status&nbsp;</label>
            <select value={statusFilter} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s || 'ALL'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-muted text-small">Severity&nbsp;</label>
            <select value={severityFilter} onChange={(e) => setSev(e.target.value)}>
              {SEVERITY_OPTIONS.map((s) => <option key={s} value={s}>{s || 'ALL'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-muted text-small">Environment&nbsp;</label>
            <select value={envFilter} onChange={(e) => setEnv(e.target.value)}>
              {ENV_OPTIONS.map((e) => <option key={e} value={e}>{e || 'ALL'}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Alert table */}
      {error && <div className="error-box mb-16">{error}</div>}
      {loading ? (
        <div className="spinner">Loading alerts…</div>
      ) : (
        <div className="card">
          <AlertList
            alerts={alerts}
            onAcknowledge={handleAcknowledge}
            onResolve={handleResolve}
            onRefresh={fetchAlerts}
          />
        </div>
      )}
    </div>
  );
}
