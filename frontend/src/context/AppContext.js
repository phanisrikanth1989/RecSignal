/**
 * context/AppContext.js
 *
 * Provides:
 *   user         — { name, email, role } | null
 *   env          — 'DEV' | 'UAT' | 'PROD'
 *   theme        — 'dark' | 'light'
 *   isAuth       — boolean
 *   login(user)  — store session
 *   logout()     — clear session
 *   setEnv(env)  — change active environment
 *   toggleTheme()— switch dark ↔ light
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

const SESSION_KEY = 'recsignal_session';
const THEME_KEY   = 'recsignal_theme';

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [user,   setUser]     = useState(null);
  const [env,    setEnvState] = useState('PROD');
  const [isAuth, setIsAuth]   = useState(false);
  const [theme,  setThemeState] = useState(() => {
    return localStorage.getItem(THEME_KEY) || 'dark';
  });

  // Apply theme attribute to <html> whenever it changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  // ── Rehydrate session from localStorage on first mount ──
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

  // ── Actions ──
  const login = useCallback((userObj) => {
    setUser(userObj);
    setIsAuth(true);
    localStorage.setItem(SESSION_KEY, JSON.stringify({ user: userObj, env }));
  }, [env]);

  const logout = useCallback(() => {
    setUser(null);
    setIsAuth(false);
    localStorage.removeItem(SESSION_KEY);
  }, []);

  const setEnv = useCallback((newEnv) => {
    setEnvState(newEnv);
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (raw) {
        const data = JSON.parse(raw);
        localStorage.setItem(SESSION_KEY, JSON.stringify({ ...data, env: newEnv }));
      }
    } catch { /* ignore */ }
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState(t => t === 'dark' ? 'light' : 'dark');
  }, []);

  return (
    <AppContext.Provider value={{ user, env, theme, isAuth, login, logout, setEnv, toggleTheme }}>
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
