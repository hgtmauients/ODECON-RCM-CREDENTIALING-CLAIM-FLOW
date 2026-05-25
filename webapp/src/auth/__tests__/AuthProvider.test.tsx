import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, useAuth } from '@/auth/AuthProvider';
import { apiService } from '@/services/api';

vi.mock('@/services/api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    setAuthToken: vi.fn(),
    setTenantId: vi.fn(),
  },
}));

function Harness() {
  const { isAuthenticated, user, login, logout, setTenant } = useAuth();
  return (
    <div>
      <div data-testid="auth-state">{isAuthenticated ? 'yes' : 'no'}</div>
      <div data-testid="tenant">{user?.tenant_id ?? ''}</div>
      <button onClick={() => void login('user@example.com', 'pass').catch(() => undefined)}>login</button>
      <button onClick={logout}>logout</button>
      <button onClick={() => setTenant('tenant-override')}>set-tenant</button>
    </div>
  );
}

describe('AuthProvider session behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    vi.mocked(apiService.get).mockResolvedValue({
      email: 'u@example.com',
      tenant_id: 'tenant-a',
      roles: ['admin'],
    });
    vi.mocked(apiService.post).mockResolvedValue({ success: true } as any);
  });

  it('rehydrates from sessionStorage and clears legacy localStorage keys', async () => {
    sessionStorage.setItem(
      'claimflow_user',
      JSON.stringify({ email: 'u@example.com', tenant_id: 'tenant-a', roles: ['admin'] })
    );
    localStorage.setItem('claimflow_token', 'legacy-token');
    localStorage.setItem('claimflow_user', '{"legacy":true}');

    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('yes');
    });
    expect(screen.getByTestId('tenant')).toHaveTextContent('tenant-a');
    expect(apiService.setTenantId).toHaveBeenCalledWith('tenant-a');
    expect(localStorage.getItem('claimflow_token')).toBeNull();
    expect(localStorage.getItem('claimflow_user')).toBeNull();
  });

  it('stores login session in sessionStorage and clears on logout', async () => {
    vi.mocked(apiService.post).mockResolvedValue({
      user: {
        email: 'user@example.com',
        tenant_id: 'tenant-b',
        roles: ['billing'],
      },
    });
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>
    );

    await act(async () => {
      await user.click(screen.getByText('login'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('yes');
    });
    expect(sessionStorage.getItem('claimflow_token')).toBeNull();
    expect(sessionStorage.getItem('claimflow_user')).toContain('"tenant_id":"tenant-b"');

    await act(async () => {
      await user.click(screen.getByText('logout'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('no');
    });
    expect(sessionStorage.getItem('claimflow_user')).toBeNull();
  });

  it('clears invalid session payloads on boot', async () => {
    sessionStorage.setItem('claimflow_user', '{not-json');

    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('no');
    });
    expect(sessionStorage.getItem('claimflow_user')).toBeNull();
  });

  it('setTenant only applies for super_admin users', async () => {
    sessionStorage.setItem(
      'claimflow_user',
      JSON.stringify({ email: 'u@example.com', tenant_id: 'tenant-a', roles: ['super_admin'] })
    );
    vi.mocked(apiService.get).mockResolvedValue({
      email: 'u@example.com',
      tenant_id: 'tenant-a',
      roles: ['super_admin'],
    });
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('yes');
    });

    await act(async () => {
      await user.click(screen.getByText('set-tenant'));
    });

    expect(apiService.setTenantId).toHaveBeenCalledWith('tenant-override');
    expect(screen.getByTestId('tenant')).toHaveTextContent('tenant-override');
    expect(sessionStorage.getItem('claimflow_user')).toContain('"tenant_id":"tenant-override"');
  });

  it('does not persist auth state when login fails', async () => {
    vi.mocked(apiService.post).mockRejectedValue(new Error('Invalid credentials'));
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>
    );

    await act(async () => {
      await user.click(screen.getByText('login'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('no');
    });
    expect(sessionStorage.getItem('claimflow_user')).toBeNull();
  });

  it('logout removes legacy localStorage session keys too', async () => {
    sessionStorage.setItem(
      'claimflow_user',
      JSON.stringify({ email: 'u@example.com', tenant_id: 'tenant-a', roles: ['admin'] })
    );
    localStorage.setItem('claimflow_token', 'legacy-token');
    localStorage.setItem('claimflow_user', '{"legacy":true}');
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('yes');
    });

    await act(async () => {
      await user.click(screen.getByText('logout'));
    });

    expect(localStorage.getItem('claimflow_token')).toBeNull();
    expect(localStorage.getItem('claimflow_user')).toBeNull();
  });
});
