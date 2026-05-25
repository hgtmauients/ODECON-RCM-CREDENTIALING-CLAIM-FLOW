import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from 'react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ClaimsManagement from '../rcm/ClaimsManagement';
import { apiService } from '@/services/api';

vi.mock('@/services/api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    downloadFile: vi.fn(),
    setAuthToken: vi.fn(),
    setTenantId: vi.fn(),
  },
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<any>('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock('@/services/iconReplacementService', () => ({
  PremiumIcon: () => <div data-testid="icon" />,
}));

describe('ClaimsManagement', () => {
  const renderPage = () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <ClaimsManagement />
      </QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows empty state when no claims are returned', async () => {
    vi.mocked(apiService.get).mockResolvedValueOnce({ success: true, data: [], total: 0 });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Claims Management')).toBeInTheDocument();
      expect(screen.getByText('No Claims Yet')).toBeInTheDocument();
    });
  });

  it('shows error UI when list request fails', async () => {
    vi.mocked(apiService.get).mockRejectedValueOnce(new Error('request failed'));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Failed to load claims')).toBeInTheDocument();
    });
  });
});
