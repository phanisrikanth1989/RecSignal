/**
 * pages/Login.js — SSO Login screen
 */

import React, { useState } from 'react';
import { useApp } from '../context/AppContext';

// Mock SSO — resolves after a short delay with a fake user object
function mockSSOAuthenticate() {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (Math.random() < 0.05) {
        reject(new Error('SSO IdP unreachable. Please retry.'));
        return;
      }
      resolve({
        name:  'Phani Kumar',
        email: 'phani.kumar@internal.corp',
        role:  'Ops Engineer',
      });
    }, 1600);
  });
}

export default function Login() {
  const { login } = useApp();

  const [phase, setPhase]   = useState('idle');   // idle | redirecting | authenticating | error
  const [errorMsg, setErrorMsg] = useState('');

  async function handleSSO(e) {
    e.preventDefault();
    setErrorMsg('');
    setPhase('redirecting');

    await new Promise(r => setTimeout(r, 900));
    setPhase('authenticating');

    try {
      const user = await mockSSOAuthenticate();
      login(user);
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
