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
  const { isAuthenticated, user, login, logout } = useAuth();
  return (
    <div>
      <div data-testid="auth-state">{isAuthenticated ? 'yes' : 'no'}</div>
      <div data-testid="tenant">{user?.tenant_id ?? ''}</div>
      <button onClick={() => login('user@example.com', 'pass')}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

describe('AuthProvider session behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('rehydrates from sessionStorage and clears legacy localStorage keys', async () => {
    sessionStorage.setItem('claimflow_token', 'session-token');
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
    expect(apiService.setAuthToken).toHaveBeenCalledWith('session-token');
    expect(apiService.setTenantId).toHaveBeenCalledWith('tenant-a');
    expect(localStorage.getItem('claimflow_token')).toBeNull();
    expect(localStorage.getItem('claimflow_user')).toBeNull();
  });

  it('stores login session in sessionStorage and clears on logout', async () => {
    vi.mocked(apiService.post).mockResolvedValue({
      access_token: 'new-token',
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
    expect(sessionStorage.getItem('claimflow_token')).toBe('new-token');
    expect(sessionStorage.getItem('claimflow_user')).toContain('"tenant_id":"tenant-b"');

    await act(async () => {
      await user.click(screen.getByText('logout'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('auth-state')).toHaveTextContent('no');
    });
    expect(sessionStorage.getItem('claimflow_token')).toBeNull();
    expect(sessionStorage.getItem('claimflow_user')).toBeNull();
  });
});
