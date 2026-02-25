/**
 * pages/Config.js — Threshold configuration management.
 *
 * Displays a grid of all metric × environment threshold pairs.
 * Allows inline editing and saving back to the backend via POST /config/update.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { getConfigs, updateConfig } from '../api/api';

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

export default function Config() {
  const [configs, setConfigs]     = useState([]);
  const [editing, setEditing]     = useState(null);   // { metric_type, environment, warning, critical }
  const [saving, setSaving]       = useState(false);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const fetchConfigs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getConfigs();
      setConfigs(res.data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConfigs(); }, [fetchConfigs]);

  // Build a lookup for quick access: "METRIC:ENV" → config
  const lookup = Object.fromEntries(
    configs.map((c) => [`${c.metric_type}:${c.environment}`, c])
  );

  const handleEdit = (metric_type, environment) => {
    const existing = lookup[`${metric_type}:${environment}`] || {};
    setEditing({
      metric_type,
      environment,
      warning:  existing.warning_threshold  ?? 70,
      critical: existing.critical_threshold ?? 90,
    });
  };

  const handleSave = async () => {
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
        warning_threshold:  Number(editing.warning),
        critical_threshold: Number(editing.critical),
      });
      toast.success(`Saved ${editing.metric_type} / ${editing.environment}`);
      setEditing(null);
      fetchConfigs();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────
  const metrics = Object.keys(METRIC_LABELS);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Threshold Configuration</h1>
        <p className="page-sub">
          Set warning and critical thresholds per metric and environment.
          Changes take effect on the next agent ingest cycle.
        </p>
      </div>

      {error   && <div className="error-box mb-16">{error}</div>}
      {loading && <div className="spinner">Loading config…</div>}

      {!loading && (
        <div className="card">
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
                    const cfg = lookup[`${metric}:${env}`];
                    const isEditing =
                      editing?.metric_type === metric && editing?.environment === env;

                    if (isEditing) {
                      return [
                        <td key={`${metric}-${env}-w`}>
                          <input
                            type="number"
                            min={0} max={100} step={1}
                            value={editing.warning}
                            onChange={(e) => setEditing({ ...editing, warning: e.target.value })}
                            style={{ width: 72 }}
                          />
                        </td>,
                        <td key={`${metric}-${env}-c`}>
                          <input
                            type="number"
                            min={0} max={100} step={1}
                            value={editing.critical}
                            onChange={(e) => setEditing({ ...editing, critical: e.target.value })}
                            style={{ width: 72 }}
                          />
                          <button
                            className="btn btn-primary"
                            style={{ marginLeft: 8, padding: '4px 10px', fontSize: 12 }}
                            onClick={handleSave}
                            disabled={saving}
                          >
                            {saving ? '…' : '✓ Save'}
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
      )}
    </div>
  );
}
