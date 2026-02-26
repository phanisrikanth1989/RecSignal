/**
 * api/api.js — Centralised Axios client for the RecSignal backend.
 *
 * All route modules import from here so the base URL is configured once.
 * Override REACT_APP_API_URL in .env to point at a non-local backend.
 */

import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// ---- Request interceptor: attach auth token if present ----
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('recsignal_token');
  if (token) config.headers['Authorization'] = `Bearer ${token}`;
  return config;
});

// ---- Response interceptor: normalise errors ----
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Unexpected error';
    return Promise.reject(new Error(message));
  }
);

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export const getDashboard = () => api.get('/dashboard');

// ---------------------------------------------------------------------------
// Servers
// ---------------------------------------------------------------------------
export const getServers = (params = {}) => api.get('/servers/', { params });
export const getServer = (id) => api.get(`/servers/${id}`);
export const registerServer = (data) => api.post('/servers/', data);
export const deactivateServer = (id) => api.patch(`/servers/${id}/deactivate`);

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------
export const getMetrics = (params = {}) => api.get('/metrics/', { params });
export const getLatestMetrics = (serverId) =>
  api.get('/metrics/latest', { params: { server_id: serverId } });
export const ingestMetrics = (payload) => api.post('/metrics/ingest', payload);

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------
export const getAlerts = (params = {}) => api.get('/alerts/', { params });
export const getAlert = (id) => api.get(`/alerts/${id}`);
export const acknowledgeAlert = (alertId, acknowledgedBy) =>
  api.post('/alerts/acknowledge', { alert_id: alertId, acknowledged_by: acknowledgedBy });
export const resolveAlert = (alertId) => api.post(`/alerts/${alertId}/resolve`);
export const getAlertSummary = () => api.get('/alerts/summary/counts');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
/** Fetch all threshold configs.  Pass { hostname: '' } to get only global defaults. */
export const getConfigs = (params = {}) => api.get('/config/', { params });
/** Fetch all overrides for a specific server hostname. */
export const getServerConfigs = (hostname) => api.get('/config/', { params: { hostname } });
export const getConfig = (metricType, environment, hostname = '', pathLabel = '') =>
  api.get(`/config/${metricType}/${environment}`, { params: { hostname, path_label: pathLabel } });
export const updateConfig = (data) => api.post('/config/update', data);
export const deleteConfig = (configId) => api.delete(`/config/${configId}`);

export default api;
