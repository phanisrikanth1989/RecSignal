/**
 * pages/Login.js — SSO Login screen
 *
 * Features:
 *  - Environment selector  (DEV / UAT / PROD)
 *  - "Sign in with SSO" button (simulates SAML/OIDC redirect + callback)
 *  - Loading / error states
 */

import React, { useState } from 'react';
import { useApp } from '../context/AppContext';

const ENVS = ['DEV', 'UAT', 'PROD'];

// Simulated SSO identity provider metadata per environment
const ENV_META = {
  DEV:  { label: 'Development',  color: '#3b82f6', idp: 'sso-dev.internal'  },
  UAT:  { label: 'User Acceptance Testing', color: '#8b5cf6', idp: 'sso-uat.internal'  },
  PROD: { label: 'Production',   color: '#f97316', idp: 'sso.internal' },
};

// Mock SSO — resolves after a short delay with a fake user object
function mockSSOAuthenticate(env) {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      // 5 % chance of failure to exercise the error state during demos
      if (Math.random() < 0.05) {
        reject(new Error('SSO IdP unreachable. Please retry.'));
        return;
      }
      resolve({
        name:  'Phani Kumar',
        email: 'phani.kumar@internal.corp',
        role:  env === 'PROD' ? 'Ops Engineer' : 'Developer',
        ssoProvider: ENV_META[env].idp,
      });
    }, 1600);
  });
}

export default function Login() {
  const { login } = useApp();

  const [selectedEnv, setSelectedEnv] = useState('PROD');
  const [phase, setPhase]             = useState('idle');   // idle | redirecting | authenticating | error
  const [errorMsg, setErrorMsg]       = useState('');

  const meta = ENV_META[selectedEnv];

  async function handleSSO(e) {
    e.preventDefault();
    setErrorMsg('');
    setPhase('redirecting');

    // Simulate "redirect to IdP" delay
    await new Promise(r => setTimeout(r, 900));
    setPhase('authenticating');

    try {
      const user = await mockSSOAuthenticate(selectedEnv);
      login(user, selectedEnv);
      // App.js will unmount this page and render the main app
    } catch (err) {
      setPhase('error');
      setErrorMsg(err.message);
    }
  }

  const busy = phase === 'redirecting' || phase === 'authenticating';

  return (
    <div className="login-backdrop">
      {/* Animated background grid */}
      <div className="login-grid-bg" />

      <div className="login-card">
        {/* Brand */}
        <div className="login-brand">
          <span className="login-brand-icon">📡</span>
          <span className="login-brand-name">RecSignal</span>
        </div>
        <p className="login-tagline">Internal DevOps Monitoring Platform</p>

        <form onSubmit={handleSSO} className="login-form">
          {/* Environment selector */}
          <div className="login-field">
            <label className="login-label" htmlFor="env-select">
              Environment
            </label>
            <div className="login-select-wrapper">
              <span
                className="env-dot"
                style={{ background: meta.color }}
              />
              <select
                id="env-select"
                className="login-select"
                value={selectedEnv}
                onChange={e => setSelectedEnv(e.target.value)}
                disabled={busy}
                required
              >
                {ENVS.map(e => (
                  <option key={e} value={e}>
                    {e} — {ENV_META[e].label}
                  </option>
                ))}
              </select>
              <span className="select-chevron">▾</span>
            </div>
            <p className="login-hint">
              You will be redirected to <code>{meta.idp}</code> for authentication.
            </p>
          </div>

          {/* Status message */}
          {phase === 'redirecting'    && <StatusBanner icon="⇢" text="Redirecting to SSO provider…" />}
          {phase === 'authenticating' && <StatusBanner icon="⟳" text="Verifying credentials…" spin />}
          {phase === 'error'          && (
            <div className="login-error">
              <span>⚠</span> {errorMsg}
            </div>
          )}

          {/* CTA */}
          <button
            type="submit"
            className="login-btn"
            disabled={busy}
            style={{ '--env-color': meta.color }}
          >
            {busy ? (
              <><span className="btn-spinner" /> Connecting…</>
            ) : (
              <><span className="sso-icon">🔐</span> Sign in with SSO</>
            )}
          </button>
        </form>

        <p className="login-footer">
          Single Sign-On powered by your organisation's Identity Provider.
          <br />Contact IT if you need access.
        </p>
      </div>
    </div>
  );
}

function StatusBanner({ icon, text, spin }) {
  return (
    <div className={`login-status ${spin ? 'login-status--spin' : ''}`}>
      <span className={spin ? 'spin-icon' : ''}>{icon}</span>
      {text}
    </div>
  );
}
