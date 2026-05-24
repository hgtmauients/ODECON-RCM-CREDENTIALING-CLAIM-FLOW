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
    try {
      const token = sessionStorage.getItem(TOKEN_KEY);
      const storedUser = sessionStorage.getItem(USER_KEY);
      // Security hardening: avoid persisting auth tokens across browser restarts.
      clearLegacyLocalSession();
      if (token && storedUser) {
        try {
          apiService.setAuthToken(token);
          const parsed = JSON.parse(storedUser);
          setUser(parsed);
          if (parsed.tenant_id) {
            apiService.setTenantId(parsed.tenant_id);
          }
        } catch {
          sessionStorage.removeItem(TOKEN_KEY);
          sessionStorage.removeItem(USER_KEY);
        }
      }
    } finally {
      setIsLoading(false);
    }
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
