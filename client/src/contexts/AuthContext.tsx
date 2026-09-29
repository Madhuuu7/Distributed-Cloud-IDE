import { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { authApi, clearToken, getToken, setToken, setUnauthorizedHandler } from '../services/api';
import type { User } from '../types';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

type AuthContextValue = {
  user: User | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
};

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>(getToken() ? 'loading' : 'anonymous');

  const signOut = useCallback(() => {
    clearToken();
    setUser(null);
    setStatus('anonymous');
  }, []);

  const signIn = useCallback(async (token: string) => {
    setToken(token);

    // Confirm the token against the API so we never render a fake session.
    const { data } = await authApi.me();

    setUser(data);
    setStatus('authenticated');
  }, []);

  // An expired token anywhere in the app drops us back to anonymous.
  useEffect(() => {
    setUnauthorizedHandler(signOut);
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  // Restore the session on a hard refresh.
  useEffect(() => {
    if (!getToken()) {
      return;
    }

    let cancelled = false;

    authApi
      .me()
      .then(({ data }) => {
        if (cancelled) return;
        setUser(data);
        setStatus('authenticated');
      })
      .catch(() => {
        if (cancelled) return;
        clearToken();
        setUser(null);
        setStatus('anonymous');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({
      user,
      status,
      isAuthenticated: status === 'authenticated',
      signIn,
      signOut
    }),
    [user, status, signIn, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
