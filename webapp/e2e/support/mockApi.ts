import type { Page, Route } from '@playwright/test';

function isApiPath(route: Route, path: string): boolean {
  const url = new URL(route.request().url());
  return url.pathname === path;
}

export async function mockAuthenticatedDashboardApis(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const method = route.request().method().toUpperCase();

    if (isApiPath(route, '/api/auth/login') && method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            email: 'admin@app.io',
            user_id: 'e2e-admin-user',
            tenant_id: 'e2e-tenant',
            roles: ['admin'],
          },
          csrf_token: 'e2e-csrf-token',
        }),
      });
      return;
    }

    if (isApiPath(route, '/api/dashboard/summary') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            as_of: '2026-01-01T00:00:00.000Z',
            claims: { by_state: { draft: 3, submitted: 2 }, total: 5 },
            ar: { buckets: [{ bucket: '0-30', amount: 250, count: 2 }], total: 250 },
            denials: { open: 1, this_month: 1 },
            credentialing: { by_status: { pending: 2 } },
            enrollment: { expiring_30d: 0 },
            work_queues: [{ key: 'draft_claims', label: 'Draft claims', count: 3, link: '/claims?state=draft' }],
            month_to_date: { claims_created: 5, charges: 500, paid: 250 },
            year_to_date: { submitted: 10, denied: 1, denial_rate_pct: 10, collection_rate_pct: 80, charges: 2000, paid: 1600 },
          },
        }),
      });
      return;
    }

    if (isApiPath(route, '/api/dashboard/integrations') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            coverage_pct: 88,
            clearinghouse: { active_payers: 3, active_connections: 2, protocols: { sftp: 2 }, tested_connections: 2, successful_tests: 2, test_success_pct: 100 },
            credentialing_integrations: { state_license_provider_configured: true, background_check_provider_configured: true, api_cert_configured: true, caqh_configured: true },
            notifications: { smtp_configured: true },
            security: { webhook_secret_configured: true, adapter_auth_configured: true },
          },
        }),
      });
      return;
    }

    if (isApiPath(route, '/api/dashboard/benchmarks') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            throughput_30d: { submitted: 10, adjudicated: 8, denied_claims: 1 },
            rates_30d: { denial_rate_pct: 10, first_pass_paid_rate_pct: 75 },
            cycle_time_days_90d: { sample_size: 5, avg: 12.4, p50: 10.2, p95: 20.1 },
            trend_windows: [],
            backlog: { open_denials: 2, draft_claims: 3, ready_to_submit: 1, submitted: 2 },
            credentialing_depth: { by_status: { pending: 2 }, completed_90d: 12, completion_days_90d: { avg: 11.2, median: 10.0, p95: 19.5 } },
            payer_enrollment_lifecycle: { by_status: { approved: 3 }, submitted_30d: 4, approved_30d: 3, approval_cycle_days_90d: { sample_size: 3, avg: 15, median: 14 } },
            rcm_reliability_hardening: {
              scheduler: { enabled: true, running: true, runs: 50, failures: 1, failure_rate_pct: 2 },
              credentialing_queue: { runs: 20, items_claimed: 40, items_failed: 2, item_failure_rate_pct: 5, stale_recovered: 1, last_success_at: null, last_failure_at: null },
            },
          },
        }),
      });
      return;
    }

    if (isApiPath(route, '/api/dashboard/compliance') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
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
            alerts: [],
            alert_summary: { breach_count: 0, warning_count: 0, ok_count: 0 },
          },
        }),
      });
      return;
    }

    if (isApiPath(route, '/api/dashboard/scalability') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            readiness_score: 86,
            capacity: { db_pool_size: 10, db_max_overflow: 20, db_total_capacity: 30, web_concurrency: 2, db_capacity_per_worker: 15 },
            job_reliability: { scheduler_enabled: true, scheduler_running: true, scheduler_runs: 50, scheduler_failures: 1, scheduler_skips_locked: 3, scheduler_failure_rate_pct: 2, queue_runs: 20, queue_items_claimed: 40, queue_items_failed: 2, queue_failure_rate_pct: 5, queue_stale_recovered: 1 },
            throughput_30d: { claims_submitted: 10, claims_adjudicated: 8, credentialing_completed: 5, enrollment_approved: 3 },
            backlog: { claims: 4, credentialing: 2, payer_enrollment: 1 },
            pressure: { claims_backlog_to_submit_ratio: 0.4, credentialing_backlog_to_completed_ratio: 0.4, enrollment_backlog_to_approved_ratio: 0.3 },
            alerts: [],
            alert_summary: { breach_count: 0, warning_count: 0, ok_count: 0 },
          },
        }),
      });
      return;
    }

    if (isApiPath(route, '/api/notifications/unread-count') && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { unread: 0 } }),
      });
      return;
    }

    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: {} }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true }),
    });
  });
}
