/**
 * components/AlertList.js — Reusable alert table.
 *
 * Props
 * -----
 * alerts          : array of alert objects
 * onAcknowledge   : (alertId) => void   — called when Acknowledge clicked
 * onResolve       : (alertId) => void   — called when Resolve clicked
 * onRefresh       : () => void          — called to trigger parent refresh
 * compact         : bool                — hide action buttons (dashboard mode)
 */

import React from 'react';

function timeAgo(isoString) {
  if (!isoString) return '—';
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400)return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function SeverityChip({ severity }) {
  const map = {
    CRITICAL: 'chip chip-critical',
    WARNING:  'chip chip-warning',
    OK:       'chip chip-ok',
  };
  return <span className={map[severity] || 'chip'}>{severity}</span>;
}

function StatusChip({ status }) {
  const map = {
    OPEN:         'chip chip-open',
    ACKNOWLEDGED: 'chip chip-acknowledged',
    RESOLVED:     'chip chip-resolved',
  };
  return <span className={map[status] || 'chip'}>{status}</span>;
}

export default function AlertList({ alerts = [], onAcknowledge, onResolve, compact = false }) {
  if (!alerts.length) {
    return (
      <p className="text-muted" style={{ padding: '24px 0', textAlign: 'center' }}>
        No alerts to display.
      </p>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Severity</th>
            <th>Metric</th>
            <th>Label</th>
            <th>Value</th>
            <th>Status</th>
            <th>Created</th>
            {!compact && <th>Acknowledged by</th>}
            {!compact && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.id}>
              <td className="text-muted text-small">{alert.id}</td>
              <td><SeverityChip severity={alert.severity} /></td>
              <td style={{ fontWeight: 500 }}>{alert.metric?.replace(/_/g, ' ')}</td>
              <td className="text-muted">{alert.label || '—'}</td>
              <td>
                <span
                  style={{
                    fontWeight: 600,
                    color:
                      alert.severity === 'CRITICAL'
                        ? 'var(--color-critical)'
                        : alert.severity === 'WARNING'
                        ? 'var(--color-warning)'
                        : 'var(--color-text)',
                  }}
                >
                  {typeof alert.value === 'number' ? alert.value.toFixed(1) : alert.value}
                </span>
              </td>
              <td><StatusChip status={alert.status} /></td>
              <td className="text-muted text-small">{timeAgo(alert.created_at)}</td>
              {!compact && (
                <td className="text-muted text-small">{alert.acknowledged_by || '—'}</td>
              )}
              {!compact && (
                <td>
                  <div className="flex gap-8">
                    {alert.status === 'OPEN' && onAcknowledge && (
                      <button
                        className="btn btn-warning"
                        style={{ padding: '4px 10px', fontSize: 12 }}
                        onClick={() => onAcknowledge(alert.id)}
                      >
                        Ack
                      </button>
                    )}
                    {alert.status !== 'RESOLVED' && onResolve && (
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '4px 10px', fontSize: 12 }}
                        onClick={() => onResolve(alert.id)}
                      >
                        Resolve
                      </button>
                    )}
                    {alert.status === 'RESOLVED' && (
                      <span className="chip chip-resolved">✓</span>
                    )}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
