/**
 * components/MetricsChart.js — Multi-metric time-series chart powered by Recharts.
 *
 * Props
 * -----
 * metrics : array of metric objects from GET /metrics/
 *           { id, server_id, metric_type, value, label, timestamp }
 *
 * The component groups metrics by type and renders a line chart per type.
 * If multiple labels exist (e.g. disk mounts) each label gets its own line.
 */

import React, { useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

// Palette for multiple lines in the same chart
const LINE_COLORS = [
  '#6366f1', '#22c55e', '#f59e0b', '#ef4444',
  '#06b6d4', '#a855f7', '#ec4899', '#84cc16',
];

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

export default function MetricsChart({ metrics = [] }) {
  const metricTypes = useMemo(() => [...new Set(metrics.map((m) => m.metric_type))], [metrics]);
  const [activeType, setActiveType] = useState(null);

  const displayType = activeType || metricTypes[0];

  const chartData = useMemo(() => {
    if (!displayType) return [];

    // Filter to selected type, sort by time
    const subset = metrics
      .filter((m) => m.metric_type === displayType)
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    // All unique timestamps
    const tsSet = [...new Set(subset.map((m) => m.timestamp))];
    // All unique labels
    const labels = [...new Set(subset.map((m) => m.label || 'value'))];

    // Build [{time, label1: val, label2: val, ...}]
    return tsSet.map((ts) => {
      const point = { time: formatTime(ts) };
      for (const lbl of labels) {
        const rec = subset.find((m) => m.timestamp === ts && (m.label || 'value') === lbl);
        point[lbl] = rec ? parseFloat(rec.value.toFixed(2)) : undefined;
      }
      return point;
    });
  }, [metrics, displayType]);

  const lineKeys = useMemo(() => {
    if (!displayType) return [];
    return [...new Set(
      metrics.filter((m) => m.metric_type === displayType).map((m) => m.label || 'value')
    )];
  }, [metrics, displayType]);

  if (!metrics.length) {
    return <p className="text-muted text-small">No metrics data available for this server.</p>;
  }

  return (
    <div>
      {/* Type selector tabs */}
      <div className="flex gap-8 mb-16" style={{ flexWrap: 'wrap' }}>
        {metricTypes.map((t) => (
          <button
            key={t}
            className={`btn ${displayType === t ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: 12, padding: '4px 12px' }}
            onClick={() => setActiveType(t)}
          >
            {t.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="time"
            tick={{ fill: '#8892a0', fontSize: 11 }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: '#8892a0', fontSize: 11 }}
            unit="%"
          />
          <Tooltip
            contentStyle={{ background: '#1a1d27', border: '1px solid #2e3147', borderRadius: 6 }}
            labelStyle={{ color: '#e2e8f0' }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#8892a0' }} />
          {lineKeys.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={LINE_COLORS[i % LINE_COLORS.length]}
              dot={false}
              activeDot={{ r: 4 }}
              strokeWidth={2}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
