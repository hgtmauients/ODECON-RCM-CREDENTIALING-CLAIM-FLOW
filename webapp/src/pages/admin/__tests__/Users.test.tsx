import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from 'react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import Users from '../Users';
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

vi.mock('@/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { user_id: 'u-1', roles: ['admin'], tenant_id: 't-1', email: 'admin@example.com' },
  }),
}));

describe('Admin Users page', () => {
  const renderPage = () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <Users />
      </QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when no users match filters', async () => {
    vi.mocked(apiService.get).mockImplementation(async (path: string) => {
      if (path === '/admin/users/_meta/roles') return { success: true, data: [] };
      return { success: true, data: [], total: 0 };
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Users')).toBeInTheDocument();
      expect(screen.getByText('No users match these filters.')).toBeInTheDocument();
    });
  });

  it('renders returned users', async () => {
    vi.mocked(apiService.get).mockImplementation(async (path: string) => {
      if (path === '/admin/users/_meta/roles') return { success: true, data: [] };
      return {
        success: true,
        total: 1,
        data: [
          {
            id: 'u-2',
            email: 'billing@example.com',
            full_name: 'Billing User',
            roles: ['billing'],
            is_active: true,
            last_login_at: null,
            created_at: null,
          },
        ],
      };
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('billing@example.com')).toBeInTheDocument();
      expect(screen.getByText('Billing User')).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
    });
  });
});
