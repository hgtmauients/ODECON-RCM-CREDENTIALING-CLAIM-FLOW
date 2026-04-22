import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiService } from '@/services/api';

interface AuthContextType {
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
  isAuthenticated: false,
  user: null,
  login: async () => {},
  logout: () => {},
  setTenant: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthContextType['user']>(null);

  useEffect(() => {
    const token = localStorage.getItem('claimflow_token');
    const storedUser = localStorage.getItem('claimflow_user');
    if (token && storedUser) {
      try {
        apiService.setAuthToken(token);
        const parsed = JSON.parse(storedUser);
        setUser(parsed);
        if (parsed.tenant_id) {
          apiService.setTenantId(parsed.tenant_id);
        }
      } catch {
        localStorage.removeItem('claimflow_token');
        localStorage.removeItem('claimflow_user');
      }
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiService.post('/auth/login', { email, password });
    const { access_token, user: userData } = response;
    localStorage.setItem('claimflow_token', access_token);
    localStorage.setItem('claimflow_user', JSON.stringify(userData));
    apiService.setAuthToken(access_token);
    apiService.setTenantId(userData.tenant_id);
    setUser(userData);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('claimflow_token');
    localStorage.removeItem('claimflow_user');
    apiService.setAuthToken(null);
    apiService.setTenantId(null);
    setUser(null);
  }, []);

  const setTenant = useCallback((tenantId: string) => {
    apiService.setTenantId(tenantId);
    if (user) {
      const updated = { ...user, tenant_id: tenantId };
      setUser(updated);
      localStorage.setItem('claimflow_user', JSON.stringify(updated));
    }
  }, [user]);

  return (
    <AuthContext.Provider value={{ isAuthenticated: !!user, user, login, logout, setTenant }}>
      {children}
    </AuthContext.Provider>
  );
}
