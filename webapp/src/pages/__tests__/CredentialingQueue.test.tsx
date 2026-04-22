import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from 'react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import CredentialingQueue from '../CredentialingQueue';
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

vi.mock('@/services/iconReplacementService', () => ({
  PremiumIcon: ({ name }: { name: string }) => <div data-testid={`icon-${name}`} />,
}));

vi.mock('@/utils/formatters', () => ({
  formatDate: (date: string) => new Date(date).toLocaleDateString(),
}));

const mockCredentialingRecords = [
  {
    provider_id: 'prov_123',
    signup_data: {
      first_name: 'John',
      last_name: 'Doe',
      email: 'john.doe@example.com',
      npi: '1234567890',
      state_code: 'CA',
      license_number: 'CA123456',
      specialty: 'Family Medicine',
    },
    credentialing_status: 'requires_review',
    overall_score: 85,
    signup_date: '2025-11-01T10:00:00Z',
    npi_verification: { verified: true },
    state_license_verification: { verified: true },
    oig_check: { excluded: false },
    sam_check: { excluded: false },
  },
  {
    provider_id: 'prov_456',
    signup_data: {
      first_name: 'Jane',
      last_name: 'Smith',
      email: 'jane.smith@example.com',
      npi: '0987654321',
      state_code: 'NY',
      license_number: 'NY789012',
      specialty: 'Pediatrics',
    },
    credentialing_status: 'pending',
    overall_score: 65,
    signup_date: '2025-11-05T14:30:00Z',
    npi_verification: { verified: true },
    state_license_verification: { verified: false },
  },
  {
    provider_id: 'prov_789',
    signup_data: {
      first_name: 'Bob',
      last_name: 'Johnson',
      email: 'bob.johnson@example.com',
      npi: '5555555555',
      state_code: 'TX',
      license_number: 'TX345678',
    },
    credentialing_status: 'passed',
    overall_score: 95,
    signup_date: '2025-10-28T08:15:00Z',
    completed_at: '2025-11-02T16:45:00Z',
    npi_verification: { verified: true },
    state_license_verification: { verified: true },
    oig_check: { excluded: false },
    sam_check: { excluded: false },
    background_check: { cleared: true },
  },
];

describe('CredentialingQueue', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <CredentialingQueue />
      </QueryClientProvider>
    );
  };

  function mockListSuccess(data = mockCredentialingRecords) {
    vi.mocked(apiService.get).mockResolvedValue({ success: true, data });
  }

  describe('Component Rendering', () => {
    it('renders page header correctly', async () => {
      mockListSuccess([]);
      renderComponent();

      expect(screen.getByText('Provider Credentialing Queue')).toBeInTheDocument();
      expect(screen.getByText('Review and approve provider credentialing applications')).toBeInTheDocument();
    });

    it('displays loading state while fetching data', () => {
      vi.mocked(apiService.get).mockImplementation(() => new Promise(() => {}));
      renderComponent();

      expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument();
    });

    it('displays error state when API call fails', async () => {
      vi.mocked(apiService.get).mockRejectedValue(new Error('API Error'));
      renderComponent();

      await waitFor(() => {
        expect(screen.getByText('Error loading credentialing queue')).toBeInTheDocument();
      });
    });

    it('displays empty state when no records exist', async () => {
      mockListSuccess([]);
      renderComponent();

      await waitFor(() => {
        expect(screen.getByText('No providers pending credentialing')).toBeInTheDocument();
      });
    });

    it('displays credentialing records when data is loaded', async () => {
      mockListSuccess();
      renderComponent();

      await waitFor(() => {
        expect(screen.getByText('John Doe')).toBeInTheDocument();
        expect(screen.getByText('Jane Smith')).toBeInTheDocument();
        expect(screen.getByText('Bob Johnson')).toBeInTheDocument();
      });
    });
  });

  describe('Filter Functionality', () => {
    beforeEach(() => {
      mockListSuccess();
    });

    it('renders all filter buttons with correct counts', async () => {
      renderComponent();

      await waitFor(() => {
        expect(screen.getByText(/All \(3\)/)).toBeInTheDocument();
        expect(screen.getByText(/Review \(1\)/)).toBeInTheDocument();
        expect(screen.getByText(/Pending \(1\)/)).toBeInTheDocument();
      });
    });

    it('filters records by "requires_review" status', async () => {
      const user = userEvent.setup();
      renderComponent();

      await waitFor(() => screen.getByText('John Doe'));

      const reviewButton = screen.getByText(/Review \(1\)/);
      await user.click(reviewButton);

      await waitFor(() => {
        expect(apiService.get).toHaveBeenCalledWith(
          '/credentialing/',
          expect.objectContaining({ status: 'requires_review' })
        );
      });
    });

    it('shows all records when "All" filter is clicked', async () => {
      const user = userEvent.setup();
      renderComponent();

      await waitFor(() => screen.getByText('John Doe'));

      await user.click(screen.getByText(/Pending/));
      await user.click(screen.getByText(/All/));

      await waitFor(() => {
        expect(apiService.get).toHaveBeenLastCalledWith(
          '/credentialing/',
          expect.objectContaining({ status: undefined })
        );
      });
    });
  });

  describe('Provider Card Display', () => {
    beforeEach(() => {
      mockListSuccess();
    });

    it('displays provider information correctly', async () => {
      renderComponent();

      await waitFor(() => {
        expect(screen.getByText('John Doe')).toBeInTheDocument();
        expect(screen.getByText(/NPI: 1234567890/)).toBeInTheDocument();
        expect(screen.getByText(/CA/)).toBeInTheDocument();
        expect(screen.getByText(/Family Medicine/)).toBeInTheDocument();
      });
    });

    it('displays correct status badge for each provider', async () => {
      renderComponent();

      await waitFor(() => {
        expect(screen.getByText('REQUIRES REVIEW')).toBeInTheDocument();
        expect(screen.getByText('PENDING')).toBeInTheDocument();
        expect(screen.getByText('PASSED')).toBeInTheDocument();
      });
    });

    it('displays overall score', async () => {
      renderComponent();

      await waitFor(() => {
        const scores = screen.getAllByText(/\/100/);
        expect(scores).toHaveLength(3);
        expect(screen.getByText('85/100')).toBeInTheDocument();
        expect(screen.getByText('65/100')).toBeInTheDocument();
        expect(screen.getByText('95/100')).toBeInTheDocument();
      });
    });
  });

  describe('Approval Actions', () => {
    beforeEach(() => {
      mockListSuccess();
      vi.mocked(apiService.post).mockResolvedValue({ success: true });
    });

    it('calls approve endpoint when approve button clicked', async () => {
      const user = userEvent.setup();
      renderComponent();

      await waitFor(() => screen.getByText('John Doe'));

      const providerCard = screen.getByText('John Doe').closest('div[style*="cursor"]');
      await user.click(providerCard!);

      const approveButton = screen.getByText('Approve');
      await user.click(approveButton);

      await waitFor(() => {
        expect(apiService.post).toHaveBeenCalledWith(
          '/credentialing/prov_123/approve',
          expect.any(Object)
        );
      });
    });

    it('calls reject endpoint when reject button clicked', async () => {
      vi.mocked(apiService.post).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderComponent();

      await waitFor(() => screen.getByText('John Doe'));

      const providerCard = screen.getByText('John Doe').closest('div[style*="cursor"]');
      await user.click(providerCard!);

      const rejectButton = screen.getByText('Reject');
      await user.click(rejectButton);

      // Should prompt for reason (depends on UI implementation)
      // After providing reason, it should call:
      await waitFor(() => {
        expect(apiService.post).toHaveBeenCalledWith(
          '/credentialing/prov_123/reject',
          expect.any(Object)
        );
      });
    });
  });

  describe('Provider Detail Modal', () => {
    beforeEach(() => {
      mockListSuccess();
    });

    it('opens modal when provider card is clicked', async () => {
      const user = userEvent.setup();
      renderComponent();

      await waitFor(() => screen.getByText('John Doe'));

      const providerCard = screen.getByText('John Doe').closest('div[style*="cursor"]');
      await user.click(providerCard!);

      expect(screen.getByText('Provider Credentialing Details')).toBeInTheDocument();
    });

    it('displays provider information in modal', async () => {
      const user = userEvent.setup();
      renderComponent();

      await waitFor(() => screen.getByText('John Doe'));
      await user.click(screen.getByText('John Doe').closest('div[style*="cursor"]')!);

      const modal = screen.getByText('Provider Credentialing Details').closest('div');
      expect(within(modal!).getByText(/john.doe@example.com/)).toBeInTheDocument();
      expect(within(modal!).getByText(/1234567890/)).toBeInTheDocument();
      expect(within(modal!).getByText(/CA123456/)).toBeInTheDocument();
    });

    it('closes modal when close button is clicked', async () => {
      const user = userEvent.setup();
      renderComponent();

      await waitFor(() => screen.getByText('John Doe'));
      await user.click(screen.getByText('John Doe').closest('div[style*="cursor"]')!);

      expect(screen.getByText('Provider Credentialing Details')).toBeInTheDocument();

      await user.click(screen.getByText('Close'));

      await waitFor(() => {
        expect(screen.queryByText('Provider Credentialing Details')).not.toBeInTheDocument();
      });
    });
  });
});
