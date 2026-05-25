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
  logout: () => void;
  setTenant: (tenantId: string) => void;
}

const AuthContext = createContext<AuthContextType>({
  isLoading: true,
  isAuthenticated: false,
  user: null,
  login: async () => {},
  logout: () => {},
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
        const token = sessionStorage.getItem(TOKEN_KEY);
        const storedUser = sessionStorage.getItem(USER_KEY);
        // Security hardening: avoid persisting auth tokens across browser restarts.
        clearLegacyLocalSession();
        if (token && storedUser) {
          try {
            apiService.setAuthToken(token);
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
            sessionStorage.removeItem(TOKEN_KEY);
            sessionStorage.removeItem(USER_KEY);
            apiService.setAuthToken(null);
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
    const { access_token, user: userData } = response;
    sessionStorage.setItem(TOKEN_KEY, access_token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(userData));
    apiService.setAuthToken(access_token);
    apiService.setTenantId(userData.tenant_id);
    setUser(userData);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    clearLegacyLocalSession();
    apiService.setAuthToken(null);
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
