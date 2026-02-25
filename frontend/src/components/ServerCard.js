/**
 * components/ServerCard.js — Clickable card representing a single server.
 *
 * Props
 * -----
 * server   : server object { id, hostname, environment, type, active }
 * selected : boolean — highlight when true
 * onClick  : callback when card is clicked
 */

import React from 'react';

const ENV_COLOR = {
  DEV:  'var(--color-dev)',
  UAT:  'var(--color-uat)',
  PROD: 'var(--color-prod)',
};

const TYPE_ICON = {
  UNIX:   '🖥️',
  ORACLE: '🗄️',
};

export default function ServerCard({ server, selected, onClick }) {
  const { hostname, environment, type, active } = server;

  return (
    <div
      className="card"
      onClick={onClick}
      style={{
        cursor: 'pointer',
        borderColor: selected ? 'var(--color-primary)' : undefined,
        background: selected ? 'rgba(99,102,241,0.08)' : undefined,
        transition: 'all 0.15s',
      }}
    >
      {/* Header row */}
      <div className="flex-between">
        <span style={{ fontSize: 22 }}>{TYPE_ICON[type] || '💻'}</span>
        <span
          className="chip"
          style={{
            background: `${ENV_COLOR[environment]}22`,
            color: ENV_COLOR[environment] || 'var(--color-text)',
          }}
        >
          {environment}
        </span>
      </div>

      {/* Hostname */}
      <div
        style={{
          fontWeight: 600,
          fontSize: 14,
          marginTop: 12,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={hostname}
      >
        {hostname}
      </div>

      {/* Meta row */}
      <div className="flex gap-8 mt-8" style={{ alignItems: 'center' }}>
        <span className="text-muted text-small">{type}</span>
        <span style={{ marginLeft: 'auto' }}>
          {active
            ? <span className="chip chip-ok">Active</span>
            : <span className="chip" style={{ background: 'rgba(255,255,255,0.08)', color: 'var(--color-muted)' }}>Inactive</span>
          }
        </span>
      </div>
    </div>
  );
}
