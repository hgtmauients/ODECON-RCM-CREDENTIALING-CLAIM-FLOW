import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from 'react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import Dashboard from '../Dashboard';
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
    user: { user_id: 'u-1', tenant_id: 't-1', email: 'admin@example.com', roles: ['admin'] },
  }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<any>('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock('@/hooks/useIsMobile', () => ({
  useIsMobile: () => false,
}));

describe('Dashboard', () => {
  const renderPage = () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <Dashboard />
      </QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders compliance, scalability, and trend sections', async () => {
    vi.mocked(apiService.get).mockImplementation(async (path: string) => {
      if (path === '/dashboard/summary') {
        return {
          data: {
            as_of: new Date().toISOString(),
            claims: { by_state: { draft: 3, submitted: 2 }, total: 5 },
            ar: { buckets: [{ bucket: '0-30', amount: 250, count: 2 }], total: 250 },
            denials: { open: 1, this_month: 1 },
            credentialing: { by_status: { pending: 2 } },
            enrollment: { expiring_30d: 0 },
            work_queues: [{ key: 'draft_claims', label: 'Draft claims', count: 3, link: '/claims?state=draft' }],
            month_to_date: { claims_created: 5, charges: 500, paid: 250 },
            year_to_date: { submitted: 10, denied: 1, denial_rate_pct: 10, collection_rate_pct: 80, charges: 2000, paid: 1600 },
          },
        };
      }
      if (path === '/dashboard/integrations') {
        return {
          data: {
            coverage_pct: 88,
            clearinghouse: { active_payers: 3, active_connections: 2, protocols: { sftp: 2 }, tested_connections: 2, successful_tests: 2, test_success_pct: 100 },
            credentialing_integrations: { state_license_provider_configured: true, background_check_provider_configured: true, api_cert_configured: true, caqh_configured: true },
            notifications: { smtp_configured: true },
            security: { webhook_secret_configured: true, adapter_auth_configured: true },
          },
        };
      }
      if (path === '/dashboard/benchmarks') {
        return {
          data: {
            throughput_30d: { submitted: 10, adjudicated: 8, denied_claims: 1 },
            rates_30d: { denial_rate_pct: 10, first_pass_paid_rate_pct: 75 },
            cycle_time_days_90d: { sample_size: 5, avg: 12.4, p50: 10.2, p95: 20.1 },
            trend_windows: [
              { window_days: 7, submitted_claims: { current: 4, previous: 3, delta_pct: 33.3 }, adjudicated_claims: { current: 3, previous: 2, delta_pct: 50 }, denied_claims: { current: 1, previous: 1, delta_pct: 0 }, credentialing_completed: { current: 2, previous: 1, delta_pct: 100 }, payer_enrollment_approved: { current: 1, previous: 1, delta_pct: 0 } },
              { window_days: 30, submitted_claims: { current: 10, previous: 8, delta_pct: 25 }, adjudicated_claims: { current: 8, previous: 7, delta_pct: 14.3 }, denied_claims: { current: 1, previous: 2, delta_pct: -50 }, credentialing_completed: { current: 5, previous: 4, delta_pct: 25 }, payer_enrollment_approved: { current: 3, previous: 2, delta_pct: 50 } },
              { window_days: 90, submitted_claims: { current: 24, previous: 20, delta_pct: 20 }, adjudicated_claims: { current: 20, previous: 16, delta_pct: 25 }, denied_claims: { current: 4, previous: 5, delta_pct: -20 }, credentialing_completed: { current: 12, previous: 10, delta_pct: 20 }, payer_enrollment_approved: { current: 8, previous: 6, delta_pct: 33.3 } },
            ],
            backlog: { open_denials: 2, draft_claims: 3, ready_to_submit: 1, submitted: 2 },
            credentialing_depth: { by_status: { pending: 2 }, completed_90d: 12, completion_days_90d: { avg: 11.2, median: 10.0, p95: 19.5 } },
            payer_enrollment_lifecycle: { by_status: { approved: 3 }, submitted_30d: 4, approved_30d: 3, approval_cycle_days_90d: { sample_size: 3, avg: 15, median: 14 } },
            rcm_reliability_hardening: {
              scheduler: { enabled: true, running: true, runs: 50, failures: 1, failure_rate_pct: 2 },
              credentialing_queue: { runs: 20, items_claimed: 40, items_failed: 2, item_failure_rate_pct: 5, stale_recovered: 1, last_success_at: null, last_failure_at: null },
            },
          },
        };
      }
      if (path === '/dashboard/compliance') {
        return {
          data: {
            maturity_score: 91,
            controls: [{ key: 'jwt_validation', label: 'JWT validation hardening', ok: true, detail: 'algorithm=RS256' }],
            rls_policy_coverage: {
              tenant_tables: 10,
              policy_tables: 10,
              coverage_pct: 100,
              forced_pct: 100,
              strict_enforcement: true,
              missing_row_security_tables: [],
              missing_force_rls_tables: [],
              missing_policy_tables: [],
            },
            audit_activity_30d: { security_events: 12, security_failures: 0, security_failure_rate_pct: 0, credential_access_events: 6 },
            alerts: [
              { key: 'rls_coverage_pct', label: 'RLS coverage below required threshold', value: 100, threshold: 100, direction: 'lt', status: 'ok', breached: false },
              { key: 'security_failure_rate_pct', label: 'Security audit failure rate above threshold', value: 0, threshold: 2, direction: 'gt', status: 'ok', breached: false },
            ],
            alert_summary: { breach_count: 0, warning_count: 0, ok_count: 2 },
          },
        };
      }
      if (path === '/dashboard/scalability') {
        return {
          data: {
            readiness_score: 86,
            capacity: { db_pool_size: 10, db_max_overflow: 20, db_total_capacity: 30, web_concurrency: 2, db_capacity_per_worker: 15 },
            job_reliability: { scheduler_enabled: true, scheduler_running: true, scheduler_runs: 50, scheduler_failures: 1, scheduler_skips_locked: 3, scheduler_failure_rate_pct: 2, queue_runs: 20, queue_items_claimed: 40, queue_items_failed: 2, queue_failure_rate_pct: 5, queue_stale_recovered: 1 },
            throughput_30d: { claims_submitted: 10, claims_adjudicated: 8, credentialing_completed: 5, enrollment_approved: 3 },
            backlog: { claims: 4, credentialing: 2, payer_enrollment: 1 },
            pressure: { claims_backlog_to_submit_ratio: 0.4, credentialing_backlog_to_completed_ratio: 0.4, enrollment_backlog_to_approved_ratio: 0.3 },
            alerts: [
              { key: 'scheduler_failure_rate_pct', label: 'Scheduler failure rate above threshold', value: 2, threshold: 2, direction: 'gt', status: 'warning', breached: false },
              { key: 'claims_pressure', label: 'Claims backlog pressure above threshold', value: 0.4, threshold: 1.5, direction: 'gt', status: 'ok', breached: false },
            ],
            alert_summary: { breach_count: 0, warning_count: 1, ok_count: 1 },
          },
        };
      }
      return { data: {} };
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Enterprise Integrations')).toBeInTheDocument();
      expect(screen.getByText('Operational Benchmarks')).toBeInTheDocument();
      expect(screen.getByText('Compliance & Security Controls')).toBeInTheDocument();
      expect(screen.getByText('Implementation & Scalability Readiness')).toBeInTheDocument();
      expect(screen.getByText('Submitted claims trend')).toBeInTheDocument();
      expect(screen.getByText('RLS strict enforcement: Enabled')).toBeInTheDocument();
      expect(screen.getAllByText('Breaches').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Warnings').length).toBeGreaterThan(0);
    });
  });

  it('shows failure state when summary endpoint fails', async () => {
    vi.mocked(apiService.get).mockRejectedValue(new Error('boom'));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Failed to load dashboard.')).toBeInTheDocument();
    });
  });
});
