/**
 * context/AppContext.js
 *
 * Provides:
 *   user       — { name, email, role } | null
 *   env        — 'DEV' | 'UAT' | 'PROD'
 *   isAuth     — boolean
 *   login(user, env) — store session
 *   logout()         — clear session
 *   setEnv(env)      — change active environment
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

const SESSION_KEY = 'recsignal_session';

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [user,   setUser]   = useState(null);
  const [env,    setEnvState] = useState('PROD');
  const [isAuth, setIsAuth] = useState(false);

  // ── Rehydrate from localStorage on first mount ────────────────────────────
  useEffect(() => {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (raw) {
        const { user: u, env: e } = JSON.parse(raw);
        setUser(u);
        setEnvState(e || 'PROD');
        setIsAuth(true);
      }
    } catch {
      localStorage.removeItem(SESSION_KEY);
    }
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────
  const login = useCallback((userObj, selectedEnv) => {
    setUser(userObj);
    setEnvState(selectedEnv);
    setIsAuth(true);
    localStorage.setItem(SESSION_KEY, JSON.stringify({ user: userObj, env: selectedEnv }));
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setIsAuth(false);
    localStorage.removeItem(SESSION_KEY);
  }, []);

  const setEnv = useCallback((newEnv) => {
    setEnvState(newEnv);
    // persist env change
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (raw) {
        const data = JSON.parse(raw);
        localStorage.setItem(SESSION_KEY, JSON.stringify({ ...data, env: newEnv }));
      }
    } catch { /* ignore */ }
  }, []);

  return (
    <AppContext.Provider value={{ user, env, isAuth, login, logout, setEnv }}>
      {children}
    </AppContext.Provider>
  );
}

/** Hook — throws if called outside <AppProvider> */
export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside <AppProvider>');
  return ctx;
}

export default AppContext;
