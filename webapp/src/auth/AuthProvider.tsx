import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiService } from '@/services/api';

interface AuthContextType {
  isLoading: boolean;
  isAuthenticated: boolean;
  user: {
    email: string;
    tenant_id: string;
    roles: string[];
    user_id?: string;
    full_name?: string | null;
  } | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setTenant: (tenantId: string) => void;
}

const AuthContext = createContext<AuthContextType>({
  isLoading: true,
  isAuthenticated: false,
  user: null,
  login: async () => {},
  logout: async () => {},
  setTenant: () => {},
});

const TOKEN_KEY = 'claimflow_token';
const USER_KEY = 'claimflow_user';

function clearLegacyLocalSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthContextType['user']>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const storedUser = sessionStorage.getItem(USER_KEY);
        // Security hardening: avoid persisting auth tokens in browser storage.
        sessionStorage.removeItem(TOKEN_KEY);
        clearLegacyLocalSession();
        if (storedUser) {
          try {
            const parsed = JSON.parse(storedUser);
            // Revalidate server-side before trusting rehydrated session state.
            const me = await apiService.get('/auth/me');
            const mergedUser = { ...parsed, ...me };
            if (!mounted) return;
            setUser(mergedUser);
            if (mergedUser.tenant_id) {
              apiService.setTenantId(mergedUser.tenant_id);
            }
            sessionStorage.setItem(USER_KEY, JSON.stringify(mergedUser));
          } catch {
            sessionStorage.removeItem(USER_KEY);
            apiService.setAuthToken(null);
            apiService.setCsrfToken(null);
            apiService.setTenantId(null);
          }
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiService.post('/auth/login', { email, password });
    const { user: userData, csrf_token: csrfToken } = response;
    sessionStorage.setItem(USER_KEY, JSON.stringify(userData));
    apiService.setAuthToken(null);
    apiService.setCsrfToken(csrfToken ?? null);
    apiService.setTenantId(userData.tenant_id);
    setUser(userData);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiService.post('/auth/logout');
    } catch {
      // If logout endpoint fails we still clear client state.
    }
    sessionStorage.removeItem(USER_KEY);
    clearLegacyLocalSession();
    apiService.setAuthToken(null);
    apiService.setCsrfToken(null);
    apiService.setTenantId(null);
    setUser(null);
  }, []);

  const setTenant = useCallback((tenantId: string) => {
    if (!user?.roles?.includes('super_admin')) {
      return;
    }
    apiService.setTenantId(tenantId);
    if (user) {
      const updated = { ...user, tenant_id: tenantId };
      setUser(updated);
      sessionStorage.setItem(USER_KEY, JSON.stringify(updated));
    }
  }, [user]);

  return (
    <AuthContext.Provider value={{ isLoading, isAuthenticated: !!user, user, login, logout, setTenant }}>
      {children}
    </AuthContext.Provider>
  );
}
