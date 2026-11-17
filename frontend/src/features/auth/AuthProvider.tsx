/** Coordinate persisted bearer, live identity, and visible recovery states. */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { LoginCredentials, User } from '../../types';
import { ApiError, SESSION_EXPIRED, TOKEN_KEY } from '../../shared/api';
import * as authApi from './authApi';
interface AuthContextValue {
  user: User | null;
  loading: boolean;
  error: string | null;
  sessionMessage: string | null;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  clearSession: (message?: string) => void;
  updateIdentity: (identity: User) => void;
}
const AuthContext = createContext<AuthContextValue | null>(null);
/** Own the single session state and handle expiry/cross-tab changes. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(localStorage.getItem(TOKEN_KEY)));
  const [error, setError] = useState<string | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const generation = useRef(0);
  /** Discard stale async identity results when a session is cleared. */
  const clear = useCallback(() => {
    generation.current += 1;
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setLoading(false);
    setError(null);
    setSessionMessage(null);
  }, []);
  /** Retain nonsecret feedback across the protected route's sign-in redirect. */
  const clearSession = (message?: string) => {
    clear();
    setSessionMessage(message || null);
  };
  /** Revalidate the stored bearer and retain recoverable network failures. */
  const refresh = useCallback(async () => {
    const current = ++generation.current;
    if (!localStorage.getItem(TOKEN_KEY)) { setUser(null); setLoading(false); return; }
    setLoading(true);
    setError(null);
    try {
      const identity = await authApi.me();
      if (current === generation.current) setUser(identity);
    } catch (failure) {
      if (current === generation.current) {
        setUser(null);
        if (failure instanceof ApiError && failure.status === 401) clear();
        else setError(failure instanceof Error ? failure.message : 'Unable to verify your session.');
      }
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [clear]);
  useEffect(() => {
    void refresh();
    /** Revalidate identity when another browser tab changes the session. */
    const storage = (event: StorageEvent) => { if (event.key === TOKEN_KEY) void refresh(); };
    window.addEventListener(SESSION_EXPIRED, clear);
    window.addEventListener('storage', storage);
    return () => {
      generation.current += 1;
      window.removeEventListener(SESSION_EXPIRED, clear);
      window.removeEventListener('storage', storage);
    };
  }, [clear, refresh]);
  /** Store only the real server bearer after a successful credential exchange. */
  const login = async (credentials: LoginCredentials) => {
    const result = await authApi.login(credentials);
    generation.current += 1;
    localStorage.setItem(TOKEN_KEY, result.token);
    setUser(result.user);
    setSessionMessage(null);
    setError(null);
    setLoading(false);
  };
  /** Clear client identity even on network failure; disclose failed server revocation. */
  const logout = async () => {
    try { await authApi.logout(); } finally { clear(); }
  };
  /** Apply a persisted profile response only to the still-current account. */
  const updateIdentity = (identity: User) => {
    if (user?.id === identity.id && localStorage.getItem(TOKEN_KEY)) {
      generation.current += 1;
      setUser(identity);
    }
  };
  return (
    <AuthContext.Provider value={{ user, loading, error, sessionMessage, login, logout, refresh, clearSession, updateIdentity }}>
      {children}
    </AuthContext.Provider>
  );
}
/** Read identity and fail loudly if used outside its single provider. */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth requires AuthProvider');
  return context;
}
