/**
 * pages/Config.js — Threshold configuration management.
 *
 * Section 1 — Environment Defaults: global warn/crit per metric × environment.
 * Section 2 — Server & Path Overrides: per-server, per-path threshold overrides.
 *             Overrides take priority over global defaults during alert evaluation.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { deleteConfig, getConfigs, getServers, updateConfig } from '../api/api';

const ENVIRONMENTS = ['DEV', 'UAT', 'PROD'];

const METRIC_LABELS = {
  DISK_USAGE:           'Disk Usage (%)',
  INODE_USAGE:          'Inode Usage (%)',
  MEMORY_USAGE:         'Memory Usage (%)',
  CPU_LOAD:             'CPU Load (%)',
  TABLESPACE_USAGE:     'Tablespace Usage (%)',
  BLOCKING_SESSIONS:    'Blocking Sessions (count)',
  LONG_RUNNING_QUERIES: 'Long Running Queries (min)',
};

const BLANK_OVERRIDE = {
  metric_type: 'DISK_USAGE',
  path_label:  '',
  warning:     70,
  critical:    90,
};

export default function Config() {
  const [configs,        setConfigs]        = useState([]);
  const [servers,        setServers]        = useState([]);
  const [editing,        setEditing]        = useState(null);
  const [editingOvr,     setEditingOvr]     = useState(null);   // override row being edited
  const [selectedServer,    setSelectedServer]    = useState('');
  const [selectedEnvFilter, setSelectedEnvFilter] = useState('UAT');
  const [showAddForm,    setShowAddForm]    = useState(false);
  const [newOverride,    setNewOverride]    = useState(BLANK_OVERRIDE);
  const [saving,         setSaving]         = useState(false);
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState(null);

  // ── Data fetching ──────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgRes, srvRes] = await Promise.all([
        getConfigs(),
        getServers({ type: 'UNIX', active_only: true }),
      ]);
      setConfigs(cfgRes.data);
      setServers(srvRes.data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // ── Derived data ───────────────────────────────────────────────────────
  // Global defaults: rows where hostname === '' and path_label === ''
  const globalConfigs = configs.filter(c => c.hostname === '' && c.path_label === '');
  const globalLookup  = Object.fromEntries(
    globalConfigs.map((c) => [`${c.metric_type}:${c.environment}`, c]),
  );

  // Server overrides: rows where hostname !== ''
  const allOverrides      = configs.filter(c => c.hostname !== '');
  const serverOverrides   = selectedServer
    ? allOverrides.filter(c => c.hostname === selectedServer)
    : [];

  // Environment of the selected server — used to pre-fill the add form
  const selectedServerEnv = servers.find(s => s.hostname === selectedServer)?.environment ?? selectedEnvFilter;
  const filteredServers    = servers.filter(s => s.environment === selectedEnvFilter);

  // ── Global defaults table handlers ────────────────────────────────────
  const handleEdit = (metric_type, environment) => {
    const existing = globalLookup[`${metric_type}:${environment}`] || {};
    setEditing({
      metric_type,
      environment,
      warning:  existing.warning_threshold  ?? 70,
      critical: existing.critical_threshold ?? 90,
    });
  };

  const handleSaveGlobal = async () => {
    if (!editing) return;
    if (Number(editing.warning) >= Number(editing.critical)) {
      toast.error('Warning threshold must be less than critical threshold.');
      return;
    }
    setSaving(true);
    try {
      await updateConfig({
        metric_type:        editing.metric_type,
        environment:        editing.environment,
        hostname:           '',
        path_label:         '',
        warning_threshold:  Number(editing.warning),
        critical_threshold: Number(editing.critical),
      });
      toast.success(`Saved ${editing.metric_type} / ${editing.environment}`);
      setEditing(null);
      fetchAll();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Override table handlers ───────────────────────────────────────────
  const handleSaveOverride = async (row) => {
    if (Number(row.warning) >= Number(row.critical)) {
      toast.error('Warning must be less than critical.');
      return;
    }
    setSaving(true);
    try {
      await updateConfig({
        metric_type:        row.metric_type,
        environment:        row.environment || selectedServerEnv,
        hostname:           row.hostname || selectedServer,
        path_label:         row.path_label,
        warning_threshold:  Number(row.warning),
        critical_threshold: Number(row.critical),
      });
      toast.success(`Saved override for ${row.hostname || selectedServer} / ${row.metric_type} [${row.path_label || 'all paths'}]`);
      setEditingOvr(null);
      setShowAddForm(false);
      setNewOverride(BLANK_OVERRIDE);
      fetchAll();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteOverride = async (cfg) => {
    if (!window.confirm(`Delete override for ${cfg.hostname} / ${cfg.metric_type} [${cfg.path_label || 'all paths'}]?`)) return;
    try {
      await deleteConfig(cfg.id);
      toast.success('Override deleted.');
      fetchAll();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────
  const metrics = Object.keys(METRIC_LABELS);

  return (
    <div>
      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="page-header">
        <h1 className="page-title">Threshold Configuration</h1>
        <p className="page-sub">
          Global defaults apply to all servers. Server &amp; path overrides take priority
          during alert evaluation: <strong>server+path &gt; server &gt; global</strong>.
        </p>
      </div>

      {error   && <div className="error-box mb-16">{error}</div>}
      {loading && <div className="spinner">Loading config…</div>}

      {!loading && (
        <>
          {/* ── Section 1: Environment Defaults ─────────────────────────── */}
          <div className="card" style={{ marginBottom: 32 }}>
            <h2 style={{ marginTop: 0, marginBottom: 16, fontSize: 16 }}>
              Environment Defaults
              <span className="text-muted" style={{ fontWeight: 400, fontSize: 13, marginLeft: 8 }}>
                (hostname = any, path = any)
              </span>
            </h2>
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  {ENVIRONMENTS.map((env) => (
                    <th key={env} colSpan={2} style={{ textAlign: 'center' }}>
                      <span className={`badge badge-${env.toLowerCase()}`}>{env}</span>
                    </th>
                  ))}
                </tr>
                <tr>
                  <th></th>
                  {ENVIRONMENTS.flatMap((env) => [
                    <th key={`${env}-w`} style={{ color: 'var(--color-warning)' }}>⚠ Warn</th>,
                    <th key={`${env}-c`} style={{ color: 'var(--color-critical)' }}>🔴 Crit</th>,
                  ])}
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric) => (
                  <tr key={metric}>
                    <td>
                      <span style={{ fontWeight: 500 }}>{METRIC_LABELS[metric]}</span>
                      <br />
                      <span className="text-muted text-small">{metric}</span>
                    </td>
                    {ENVIRONMENTS.flatMap((env) => {
                      const cfg = globalLookup[`${metric}:${env}`];
                      const isEditing =
                        editing?.metric_type === metric && editing?.environment === env;

                      if (isEditing) {
                        return [
                          <td key={`${metric}-${env}-w`}>
                            <input
                              type="number" min={0} step={1}
                              value={editing.warning}
                              onChange={(e) => setEditing({ ...editing, warning: e.target.value })}
                              style={{ width: 72 }}
                            />
                          </td>,
                          <td key={`${metric}-${env}-c`}>
                            <input
                              type="number" min={0} step={1}
                              value={editing.critical}
                              onChange={(e) => setEditing({ ...editing, critical: e.target.value })}
                              style={{ width: 72 }}
                            />
                            <button
                              className="btn btn-primary"
                              style={{ marginLeft: 8, padding: '4px 10px', fontSize: 12 }}
                              onClick={handleSaveGlobal} disabled={saving}
                            >
                              {saving ? '…' : '✓'}
                            </button>
                            <button
                              className="btn btn-ghost"
                              style={{ marginLeft: 4, padding: '4px 10px', fontSize: 12 }}
                              onClick={() => setEditing(null)}
                            >
                              ✕
                            </button>
                          </td>,
                        ];
                      }

                      return [
                        <td key={`${metric}-${env}-w`}>
                          {cfg
                            ? <span style={{ color: 'var(--color-warning)' }}>{cfg.warning_threshold}</span>
                            : <span className="text-muted">—</span>}
                        </td>,
                        <td key={`${metric}-${env}-c`}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {cfg
                              ? <span style={{ color: 'var(--color-critical)' }}>{cfg.critical_threshold}</span>
                              : <span className="text-muted">—</span>}
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '2px 8px', fontSize: 11 }}
                              onClick={() => handleEdit(metric, env)}
                            >
                              Edit
                            </button>
                          </span>
                        </td>,
                      ];
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ── Section 2: Server & Path Overrides ──────────────────────── */}
          <div className="card">
            <h2 style={{ margin: '0 0 14px', fontSize: 16 }}>Server &amp; Path Overrides</h2>

            {/* ── Environment tabs ──────────────────────────────────────── */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
              {['UAT', 'PROD', 'DEV'].map((env) => (
                <button
                  key={env}
                  className={selectedEnvFilter === env ? 'btn btn-primary' : 'btn btn-ghost'}
                  style={{ padding: '5px 16px', fontSize: 13, fontWeight: selectedEnvFilter === env ? 600 : 400 }}
                  onClick={() => {
                    setSelectedEnvFilter(env);
                    setSelectedServer('');
                    setShowAddForm(false);
                    setEditingOvr(null);
                  }}
                >
                  <span className={`badge badge-${env.toLowerCase()}`} style={{ marginRight: 6 }}>{env}</span>
                  ({servers.filter(s => s.environment === env).length})
                </button>
              ))}
            </div>

            {/* ── Server dropdown ───────────────────────────────────────── */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <select
                value={selectedServer}
                onChange={(e) => { setSelectedServer(e.target.value); setShowAddForm(false); setEditingOvr(null); }}
                style={{ minWidth: 220 }}
              >
                <option value="">— select a {selectedEnvFilter} server —</option>
                {filteredServers.map(s => (
                  <option key={s.id} value={s.hostname}>{s.hostname}</option>
                ))}
              </select>
              {selectedServer && !showAddForm && (
                <button
                  className="btn btn-primary"
                  style={{ padding: '6px 14px', fontSize: 13 }}
                  onClick={() => { setShowAddForm(true); setEditingOvr(null); setNewOverride(BLANK_OVERRIDE); }}
                >
                  + Add Override
                </button>
              )}
            </div>

            {!selectedServer && (
              <p className="text-muted" style={{ margin: 0 }}>
                Select a server above to view or add path-level threshold overrides.
                <br />
                There {allOverrides.length === 1 ? 'is' : 'are'} currently{' '}
                <strong>{allOverrides.length}</strong> override{allOverrides.length !== 1 ? 's' : ''}{' '}
                configured across all servers.
              </p>
            )}

            {selectedServer && (
              <>
                {/* ── Add Override Form ───────────────────────────────── */}
                {showAddForm && (
                  <div style={{ background: 'var(--color-surface-2, #1e2533)', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                    <strong style={{ display: 'block', marginBottom: 10, fontSize: 13 }}>
                      New override for <code>{selectedServer}</code>
                    </strong>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        Metric
                        <select
                          value={newOverride.metric_type}
                          onChange={(e) => setNewOverride({ ...newOverride, metric_type: e.target.value })}
                          style={{ minWidth: 180 }}
                        >
                          {metrics.map(m => (
                            <option key={m} value={m}>{METRIC_LABELS[m]}</option>
                          ))}
                        </select>
                      </label>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        Path / Label
                        <input
                          type="text"
                          placeholder="e.g. /opt  or  USERS  (leave blank = all)"
                          value={newOverride.path_label}
                          onChange={(e) => setNewOverride({ ...newOverride, path_label: e.target.value })}
                          style={{ width: 220 }}
                        />
                      </label>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        ⚠ Warn
                        <input
                          type="number" min={0} step={1}
                          value={newOverride.warning}
                          onChange={(e) => setNewOverride({ ...newOverride, warning: e.target.value })}
                          style={{ width: 72 }}
                        />
                      </label>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        🔴 Crit
                        <input
                          type="number" min={0} step={1}
                          value={newOverride.critical}
                          onChange={(e) => setNewOverride({ ...newOverride, critical: e.target.value })}
                          style={{ width: 72 }}
                        />
                      </label>
                      <button
                        className="btn btn-primary"
                        style={{ padding: '6px 14px' }}
                        disabled={saving}
                        onClick={() => handleSaveOverride({
                          ...newOverride,
                          hostname:    selectedServer,
                          environment: selectedServerEnv,
                          warning:     newOverride.warning,
                          critical:    newOverride.critical,
                        })}
                      >
                        {saving ? '…' : 'Save'}
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '6px 14px' }}
                        onClick={() => setShowAddForm(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* ── Overrides Table ─────────────────────────────────── */}
                {serverOverrides.length === 0 ? (
                  <p className="text-muted" style={{ margin: 0 }}>
                    No overrides for <strong>{selectedServer}</strong>. Click "+ Add Override" to create one.
                  </p>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Path / Label</th>
                        <th style={{ color: 'var(--color-warning)' }}>⚠ Warn</th>
                        <th style={{ color: 'var(--color-critical)' }}>🔴 Crit</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {serverOverrides.map((cfg) => {
                        const isEditing = editingOvr?.id === cfg.id;
                        if (isEditing) {
                          return (
                            <tr key={cfg.id}>
                              <td>
                                <span style={{ fontWeight: 500 }}>{METRIC_LABELS[cfg.metric_type] || cfg.metric_type}</span>
                                <br /><span className="text-muted text-small">{cfg.metric_type}</span>
                              </td>
                              <td>
                                <input
                                  type="text"
                                  value={editingOvr.path_label}
                                  onChange={(e) => setEditingOvr({ ...editingOvr, path_label: e.target.value })}
                                  placeholder="e.g. /opt"
                                  style={{ width: 160 }}
                                />
                              </td>
                              <td>
                                <input
                                  type="number" min={0} step={1}
                                  value={editingOvr.warning}
                                  onChange={(e) => setEditingOvr({ ...editingOvr, warning: e.target.value })}
                                  style={{ width: 72 }}
                                />
                              </td>
                              <td>
                                <input
                                  type="number" min={0} step={1}
                                  value={editingOvr.critical}
                                  onChange={(e) => setEditingOvr({ ...editingOvr, critical: e.target.value })}
                                  style={{ width: 72 }}
                                />
                              </td>
                              <td>
                                <button
                                  className="btn btn-primary"
                                  style={{ padding: '4px 10px', fontSize: 12 }}
                                  disabled={saving}
                                  onClick={() => handleSaveOverride({ ...cfg, ...editingOvr })}
                                >
                                  {saving ? '…' : '✓ Save'}
                                </button>
                                <button
                                  className="btn btn-ghost"
                                  style={{ marginLeft: 6, padding: '4px 10px', fontSize: 12 }}
                                  onClick={() => setEditingOvr(null)}
                                >
                                  ✕
                                </button>
                              </td>
                            </tr>
                          );
                        }

                        return (
                          <tr key={cfg.id}>
                            <td>
                              <span style={{ fontWeight: 500 }}>{METRIC_LABELS[cfg.metric_type] || cfg.metric_type}</span>
                              <br /><span className="text-muted text-small">{cfg.metric_type}</span>
                            </td>
                            <td>
                              {cfg.path_label
                                ? <code style={{ fontSize: 13 }}>{cfg.path_label}</code>
                                : <span className="text-muted">— all paths —</span>}
                            </td>
                            <td style={{ color: 'var(--color-warning)' }}>{cfg.warning_threshold}</td>
                            <td style={{ color: 'var(--color-critical)' }}>{cfg.critical_threshold}</td>
                            <td>
                              <button
                                className="btn btn-ghost"
                                style={{ padding: '3px 8px', fontSize: 12 }}
                                onClick={() => setEditingOvr({
                                  id:         cfg.id,
                                  path_label: cfg.path_label,
                                  warning:    cfg.warning_threshold,
                                  critical:   cfg.critical_threshold,
                                })}
                              >
                                Edit
                              </button>
                              <button
                                className="btn btn-ghost"
                                style={{ marginLeft: 6, padding: '3px 8px', fontSize: 12, color: 'var(--color-critical)' }}
                                onClick={() => handleDeleteOverride(cfg)}
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}


