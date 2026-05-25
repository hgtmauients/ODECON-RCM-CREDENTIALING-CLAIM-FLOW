/**
 * Home dashboard.
 *
 * One round-trip to /api/dashboard/summary returns:
 *   - claims by state + total
 *   - AR aging buckets + total outstanding
 *   - open denials + denials this month
 *   - credentialing queue counts
 *   - enrollments expiring within 30 days
 *   - "work queues" — actionable counts the operator should drain
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from 'react-query';
import { apiService } from '@/services/api';
import { useAuth } from '@/auth/AuthProvider';
import { useIsMobile } from '@/hooks/useIsMobile';
import { getSafeInternalPath } from '@/utils/safeNavigation';

type DashboardData = {
  as_of: string;
  claims: { by_state: Record<string, number>; total: number };
  ar: { buckets: { bucket: string; amount: number; count: number }[]; total: number };
  denials: { open: number; this_month: number };
  credentialing: { by_status: Record<string, number> };
  enrollment: { expiring_30d: number };
  work_queues: { key: string; label: string; count: number; link: string }[];
  month_to_date?: { claims_created: number; charges: number; paid: number };
  year_to_date?: {
    submitted: number;
    denied: number;
    denial_rate_pct: number;
    collection_rate_pct: number;
    charges: number;
    paid: number;
  };
};

type IntegrationData = {
  as_of: string;
  coverage_pct: number;
  clearinghouse: {
    active_payers: number;
    active_connections: number;
    protocols: Record<string, number>;
    tested_connections: number;
    successful_tests: number;
    test_success_pct: number;
  };
  credentialing_integrations: {
    state_license_provider_configured: boolean;
    background_check_provider_configured: boolean;
    api_cert_configured: boolean;
    caqh_configured: boolean;
  };
  notifications: { smtp_configured: boolean };
  security: {
    webhook_secret_configured: boolean;
    adapter_auth_configured: boolean;
  };
};

type BenchmarkData = {
  as_of: string;
  throughput_30d: { submitted: number; adjudicated: number; denied_claims: number };
  rates_30d: { denial_rate_pct: number; first_pass_paid_rate_pct: number };
  cycle_time_days_90d: { sample_size: number; avg: number; p50: number; p95: number };
  trend_windows: {
    window_days: number;
    submitted_claims: { current: number; previous: number; delta_pct: number | null };
    adjudicated_claims: { current: number; previous: number; delta_pct: number | null };
    denied_claims: { current: number; previous: number; delta_pct: number | null };
    credentialing_completed: { current: number; previous: number; delta_pct: number | null };
    payer_enrollment_approved: { current: number; previous: number; delta_pct: number | null };
  }[];
  backlog: { open_denials: number; draft_claims: number; ready_to_submit: number; submitted: number };
  credentialing_depth: {
    by_status: Record<string, number>;
    completed_90d: number;
    completion_days_90d: { avg: number; median: number; p95: number };
  };
  payer_enrollment_lifecycle: {
    by_status: Record<string, number>;
    submitted_30d: number;
    approved_30d: number;
    approval_cycle_days_90d: { sample_size: number; avg: number; median: number };
  };
  rcm_reliability_hardening: {
    scheduler: { enabled: boolean; running: boolean; runs: number; failures: number; failure_rate_pct: number };
    credentialing_queue: {
      runs: number;
      items_claimed: number;
      items_failed: number;
      item_failure_rate_pct: number;
      stale_recovered: number;
      last_success_at: string | null;
      last_failure_at: string | null;
    };
  };
};

type ComplianceData = {
  as_of: string;
  maturity_score: number;
  controls: { key: string; label: string; ok: boolean; detail: string }[];
  rls_policy_coverage: {
    tenant_tables: number;
    policy_tables: number;
    coverage_pct: number;
    forced_pct: number;
    strict_enforcement: boolean;
    missing_row_security_tables: string[];
    missing_force_rls_tables: string[];
    missing_policy_tables: string[];
  };
  audit_activity_30d: { security_events: number; security_failures: number; security_failure_rate_pct: number; credential_access_events: number };
  alerts: { key: string; label: string; value: number; threshold: number; direction: 'gt' | 'lt'; status: 'ok' | 'warning' | 'breach'; breached: boolean }[];
  alert_summary: { breach_count: number; warning_count: number; ok_count: number };
};

type ScalabilityData = {
  as_of: string;
  readiness_score: number;
  capacity: {
    db_pool_size: number;
    db_max_overflow: number;
    db_total_capacity: number;
    web_concurrency: number;
    db_capacity_per_worker: number;
  };
  job_reliability: {
    scheduler_enabled: boolean;
    scheduler_running: boolean;
    scheduler_runs: number;
    scheduler_failures: number;
    scheduler_skips_locked: number;
    scheduler_failure_rate_pct: number;
    queue_runs: number;
    queue_items_claimed: number;
    queue_items_failed: number;
    queue_failure_rate_pct: number;
    queue_stale_recovered: number;
  };
  throughput_30d: {
    claims_submitted: number;
    claims_adjudicated: number;
    credentialing_completed: number;
    enrollment_approved: number;
  };
  backlog: { claims: number; credentialing: number; payer_enrollment: number };
  pressure: {
    claims_backlog_to_submit_ratio: number;
    credentialing_backlog_to_completed_ratio: number;
    enrollment_backlog_to_approved_ratio: number;
  };
  alerts: { key: string; label: string; value: number; threshold: number; direction: 'gt' | 'lt'; status: 'ok' | 'warning' | 'breach'; breached: boolean }[];
  alert_summary: { breach_count: number; warning_count: number; ok_count: number };
};

const fmtCurrency = (v: number) =>
  v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

export default function Dashboard() {
  const { user } = useAuth();
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery(
    'dashboard-summary',
    () => apiService.get('/dashboard/summary'),
    { staleTime: 30_000 },
  );
  const integrationsQuery = useQuery(
    'dashboard-integrations',
    () => apiService.get('/dashboard/integrations'),
    { staleTime: 60_000 },
  );
  const benchmarksQuery = useQuery(
    'dashboard-benchmarks',
    () => apiService.get('/dashboard/benchmarks'),
    { staleTime: 60_000 },
  );
  const complianceQuery = useQuery(
    'dashboard-compliance',
    () => apiService.get('/dashboard/compliance'),
    { staleTime: 60_000 },
  );
  const scalabilityQuery = useQuery(
    'dashboard-scalability',
    () => apiService.get('/dashboard/scalability'),
    { staleTime: 60_000 },
  );

  const summary: DashboardData | null = data?.data || null;
  const integrations: IntegrationData | null = integrationsQuery.data?.data || null;
  const benchmarks: BenchmarkData | null = benchmarksQuery.data?.data || null;
  const compliance: ComplianceData | null = complianceQuery.data?.data || null;
  const scalability: ScalabilityData | null = scalabilityQuery.data?.data || null;
  const greeting = user?.email ? user.email.split('@')[0] : 'there';
  const navigateIfSafe = (path: string) => {
    const safePath = getSafeInternalPath(path);
    if (!safePath) return;
    navigate(safePath);
  };

  if (isLoading) {
    return (
      <div style={{ padding: 'var(--space-12)', textAlign: 'center' }}>
        <div style={{ width: 24, height: 24, margin: '0 auto', border: '3px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
      </div>
    );
  }
  if (error || !summary) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--brand-error)' }}>
        Failed to load dashboard.
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <h1 className="page-title">Hello, {greeting}</h1>
        <p className="page-subtitle">
          As of {new Date(summary.as_of).toLocaleString()}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
        <KPI label="Total claims" value={summary.claims.total.toLocaleString()} onClick={() => navigate('/claims')} />
        <KPI label="AR outstanding" value={fmtCurrency(summary.ar.total)} accent="var(--brand-primary)" onClick={() => navigate('/claims?state=submitted')} />
        <KPI label="Open denials" value={summary.denials.open.toLocaleString()} accent={summary.denials.open > 0 ? 'var(--brand-error)' : undefined} onClick={() => navigate('/denials')} />
        <KPI label="Expiring credentials (≤30d)" value={summary.enrollment.expiring_30d.toLocaleString()} accent={summary.enrollment.expiring_30d > 0 ? 'var(--brand-warning, #f59e0b)' : undefined} onClick={() => navigate('/payer-enrollment')} />
      </div>

      {(summary.month_to_date || summary.year_to_date) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
          {summary.month_to_date && (
            <>
              <KPI
                label="Claims this month"
                value={summary.month_to_date.claims_created.toLocaleString()}
              />
              <KPI
                label="Revenue this month"
                value={fmtCurrency(summary.month_to_date.paid)}
                accent="var(--brand-success)"
              />
            </>
          )}
          {summary.year_to_date && (
            <>
              <KPI
                label="Denial rate (YTD)"
                value={`${summary.year_to_date.denial_rate_pct}%`}
                accent={summary.year_to_date.denial_rate_pct >= 10 ? 'var(--brand-error)' : 'var(--text-primary)'}
              />
              <KPI
                label="Collection rate (YTD)"
                value={`${summary.year_to_date.collection_rate_pct}%`}
                accent={summary.year_to_date.collection_rate_pct >= 90 ? 'var(--brand-success)' : 'var(--brand-primary)'}
              />
            </>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1fr) minmax(0, 1fr)', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
        {/* Work queues */}
        <Card title="Work queues" subtitle="Counts of actionable items right now">
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {summary.work_queues.map((q) => (
              <button
                key={q.key}
                onClick={() => navigateIfSafe(q.link)}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: 'var(--space-3) var(--space-2)',
                  border: 'none',
                  borderBottom: '1px solid var(--border-primary)',
                  background: 'transparent',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <span style={{ fontSize: 'var(--font-size-sm)' }}>{q.label}</span>
                <span style={{
                  fontSize: 'var(--font-size-base)',
                  fontWeight: 700,
                  minWidth: 36,
                  textAlign: 'right',
                  color: q.count > 0 ? 'var(--text-primary)' : 'var(--text-tertiary)',
                }}>
                  {q.count.toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        </Card>

        {/* AR aging */}
        <Card title="AR aging" subtitle="Outstanding balance by days since submitted">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={tableHeadCell}>Bucket</th>
                <th style={{ ...tableHeadCell, textAlign: 'right' }}>Claims</th>
                <th style={{ ...tableHeadCell, textAlign: 'right' }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {summary.ar.buckets.map((b) => (
                <tr key={b.bucket} style={{ borderTop: '1px solid var(--border-primary)' }}>
                  <td style={{ padding: 'var(--space-2)', fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>{b.bucket} days</td>
                  <td style={{ padding: 'var(--space-2)', textAlign: 'right', fontSize: 'var(--font-size-sm)' }}>{b.count.toLocaleString()}</td>
                  <td style={{ padding: 'var(--space-2)', textAlign: 'right', fontSize: 'var(--font-size-sm)', fontFamily: 'monospace' }}>
                    {fmtCurrency(b.amount)}
                  </td>
                </tr>
              ))}
              <tr style={{ borderTop: '2px solid var(--border-primary)' }}>
                <td style={{ padding: 'var(--space-2)', fontSize: 'var(--font-size-sm)', fontWeight: 700 }}>Total</td>
                <td />
                <td style={{ padding: 'var(--space-2)', textAlign: 'right', fontSize: 'var(--font-size-sm)', fontFamily: 'monospace', fontWeight: 700 }}>
                  {fmtCurrency(summary.ar.total)}
                </td>
              </tr>
            </tbody>
          </table>
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1fr) minmax(0, 1fr)', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
        <Card title="Enterprise Integrations" subtitle="Clearinghouse + credentialing + security ecosystem status">
          {!integrations ? (
            <p style={{ color: 'var(--text-secondary)' }}>
              {integrationsQuery.isLoading ? 'Loading integration status...' : 'Integration status unavailable.'}
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>Coverage</span>
                <span style={{ fontWeight: 700, color: integrations.coverage_pct >= 75 ? 'var(--brand-success)' : 'var(--brand-warning)' }}>
                  {integrations.coverage_pct}%
                </span>
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                {integrations.clearinghouse.active_connections} active connections across {integrations.clearinghouse.active_payers} active payers
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                Connection test success: {integrations.clearinghouse.test_success_pct}% ({integrations.clearinghouse.successful_tests}/{integrations.clearinghouse.tested_connections})
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
                <li>CAQH configured: {integrations.credentialing_integrations.caqh_configured ? 'Yes' : 'No'}</li>
                <li>API-Cert configured: {integrations.credentialing_integrations.api_cert_configured ? 'Yes' : 'No'}</li>
                <li>SMTP configured: {integrations.notifications.smtp_configured ? 'Yes' : 'No'}</li>
                <li>Webhook secret configured: {integrations.security.webhook_secret_configured ? 'Yes' : 'No'}</li>
              </ul>
            </div>
          )}
        </Card>

        <Card title="Operational Benchmarks" subtitle="Throughput, quality, cycle-time, and backlog indicators">
          {!benchmarks ? (
            <p style={{ color: 'var(--text-secondary)' }}>
              {benchmarksQuery.isLoading ? 'Loading operational benchmarks...' : 'Operational benchmark data unavailable.'}
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 'var(--space-3)' }}>
                <MiniMetric label="Submitted (30d)" value={benchmarks.throughput_30d.submitted.toLocaleString()} />
                <MiniMetric label="Adjudicated (30d)" value={benchmarks.throughput_30d.adjudicated.toLocaleString()} />
                <MiniMetric label="Denial rate (30d)" value={`${benchmarks.rates_30d.denial_rate_pct}%`} />
                <MiniMetric label="First-pass paid (30d)" value={`${benchmarks.rates_30d.first_pass_paid_rate_pct}%`} />
                <MiniMetric label="Cycle avg days (90d)" value={benchmarks.cycle_time_days_90d.avg.toFixed(1)} />
                <MiniMetric label="Cycle p95 days (90d)" value={benchmarks.cycle_time_days_90d.p95.toFixed(1)} />
                <MiniMetric label="Open denials" value={benchmarks.backlog.open_denials.toLocaleString()} />
                <MiniMetric label="Ready to submit" value={benchmarks.backlog.ready_to_submit.toLocaleString()} />
              </div>

              <TrendChart
                title="Submitted claims trend"
                points={benchmarks.trend_windows.map((w) => ({ windowDays: w.window_days, value: w.submitted_claims.current, deltaPct: w.submitted_claims.delta_pct }))}
              />
              <TrendChart
                title="Adjudicated claims trend"
                points={benchmarks.trend_windows.map((w) => ({ windowDays: w.window_days, value: w.adjudicated_claims.current, deltaPct: w.adjudicated_claims.delta_pct }))}
              />
              <TrendChart
                title="Credentialing completions trend"
                points={benchmarks.trend_windows.map((w) => ({ windowDays: w.window_days, value: w.credentialing_completed.current, deltaPct: w.credentialing_completed.delta_pct }))}
              />
              <TrendChart
                title="Payer approvals trend"
                points={benchmarks.trend_windows.map((w) => ({ windowDays: w.window_days, value: w.payer_enrollment_approved.current, deltaPct: w.payer_enrollment_approved.delta_pct }))}
              />

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 'var(--space-3)' }}>
                <MiniMetric label="Credentialing completed (90d)" value={benchmarks.credentialing_depth.completed_90d.toLocaleString()} />
                <MiniMetric label="Credentialing median days" value={benchmarks.credentialing_depth.completion_days_90d.median.toFixed(1)} />
                <MiniMetric label="Enrollment submitted (30d)" value={benchmarks.payer_enrollment_lifecycle.submitted_30d.toLocaleString()} />
                <MiniMetric label="Enrollment approved (30d)" value={benchmarks.payer_enrollment_lifecycle.approved_30d.toLocaleString()} />
                <MiniMetric label="Enrollment median days" value={benchmarks.payer_enrollment_lifecycle.approval_cycle_days_90d.median.toFixed(1)} />
                <MiniMetric label="Scheduler failure rate" value={`${benchmarks.rcm_reliability_hardening.scheduler.failure_rate_pct}%`} />
              </div>
            </div>
          )}
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1fr) minmax(0, 1fr)', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
        <Card title="Compliance & Security Controls" subtitle="Control maturity, policy coverage, and security audit activity">
          {!compliance ? (
            <p style={{ color: 'var(--text-secondary)' }}>
              {complianceQuery.isLoading ? 'Loading compliance controls...' : 'Compliance controls unavailable.'}
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>Maturity score</span>
                <span style={{ fontWeight: 700, color: compliance.maturity_score >= 80 ? 'var(--brand-success)' : 'var(--brand-warning)' }}>
                  {compliance.maturity_score}%
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 'var(--space-2)' }}>
                <MiniMetric label="RLS coverage" value={`${compliance.rls_policy_coverage.coverage_pct}%`} />
                <MiniMetric label="RLS forced" value={`${compliance.rls_policy_coverage.forced_pct}%`} />
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: compliance.rls_policy_coverage.strict_enforcement ? 'var(--brand-success)' : 'var(--brand-error)' }}>
                RLS strict enforcement: {compliance.rls_policy_coverage.strict_enforcement ? 'Enabled' : 'Needs remediation'}
              </div>
              {!compliance.rls_policy_coverage.strict_enforcement && (
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--brand-error)' }}>
                  Missing policy coverage on {compliance.rls_policy_coverage.missing_policy_tables.length} table(s)
                </div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 'var(--space-2)' }}>
                <MiniMetric label="Security events (30d)" value={compliance.audit_activity_30d.security_events.toLocaleString()} />
                <MiniMetric label="Security failures (30d)" value={compliance.audit_activity_30d.security_failures.toLocaleString()} />
                <MiniMetric label="Security failure rate" value={`${compliance.audit_activity_30d.security_failure_rate_pct}%`} />
                <MiniMetric label="Credential access logs (30d)" value={compliance.audit_activity_30d.credential_access_events.toLocaleString()} />
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                <ThresholdPill label="Breaches" count={compliance.alert_summary.breach_count} tone="breach" />
                <ThresholdPill label="Warnings" count={compliance.alert_summary.warning_count} tone="warning" />
                <ThresholdPill label="Healthy" count={compliance.alert_summary.ok_count} tone="ok" />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {compliance.alerts.map((alert) => (
                  <AlertRow key={alert.key} label={alert.label} status={alert.status} value={alert.value} threshold={alert.threshold} direction={alert.direction} />
                ))}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {compliance.controls.map((control) => (
                  <div key={control.key} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-primary)', padding: '4px 0' }}>
                    <span style={{ fontSize: 'var(--font-size-sm)' }}>{control.label}</span>
                    <span style={{ fontSize: 'var(--font-size-sm)', color: control.ok ? 'var(--brand-success)' : 'var(--brand-error)' }}>
                      {control.ok ? 'Pass' : 'Needs hardening'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card title="Implementation & Scalability Readiness" subtitle="Capacity, reliability, and execution-risk pressure indicators">
          {!scalability ? (
            <p style={{ color: 'var(--text-secondary)' }}>
              {scalabilityQuery.isLoading ? 'Loading scalability readiness...' : 'Scalability readiness unavailable.'}
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>Readiness score</span>
                <span style={{ fontWeight: 700, color: scalability.readiness_score >= 80 ? 'var(--brand-success)' : 'var(--brand-warning)' }}>
                  {scalability.readiness_score}%
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 'var(--space-2)' }}>
                <MiniMetric label="DB pool capacity" value={`${scalability.capacity.db_total_capacity}`} />
                <MiniMetric label="Capacity / worker" value={`${scalability.capacity.db_capacity_per_worker}`} />
                <MiniMetric label="Scheduler failure rate" value={`${scalability.job_reliability.scheduler_failure_rate_pct}%`} />
                <MiniMetric label="Queue failure rate" value={`${scalability.job_reliability.queue_failure_rate_pct}%`} />
                <MiniMetric label="Claim pressure" value={`${scalability.pressure.claims_backlog_to_submit_ratio}x`} />
                <MiniMetric label="Credentialing pressure" value={`${scalability.pressure.credentialing_backlog_to_completed_ratio}x`} />
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                <ThresholdPill label="Breaches" count={scalability.alert_summary.breach_count} tone="breach" />
                <ThresholdPill label="Warnings" count={scalability.alert_summary.warning_count} tone="warning" />
                <ThresholdPill label="Healthy" count={scalability.alert_summary.ok_count} tone="ok" />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {scalability.alerts.map((alert) => (
                  <AlertRow key={alert.key} label={alert.label} status={alert.status} value={alert.value} threshold={alert.threshold} direction={alert.direction} />
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1fr) minmax(0, 1fr)', gap: 'var(--space-6)' }}>
        <Card title="Claims by state" subtitle="Breakdown across the lifecycle">
          {Object.keys(summary.claims.by_state).length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>No claims yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {Object.entries(summary.claims.by_state)
                .sort((a, b) => b[1] - a[1])
                .map(([state, count]) => {
                  const pct = summary.claims.total ? Math.round((count / summary.claims.total) * 100) : 0;
                  return (
                    <div key={state}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--font-size-sm)' }}>
                        <span style={{ fontWeight: 600 }}>{state.replace(/_/g, ' ')}</span>
                        <span style={{ color: 'var(--text-secondary)' }}>
                          {count.toLocaleString()} <span style={{ color: 'var(--text-tertiary)' }}>· {pct}%</span>
                        </span>
                      </div>
                      <div style={{ height: 4, background: 'var(--surface-secondary)', borderRadius: 'var(--radius-sm)', marginTop: 4, overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: 'var(--brand-primary)' }} />
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </Card>

        <Card title="Credentialing" subtitle="Provider verification by status">
          {Object.keys(summary.credentialing.by_status).length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>No providers in queue.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {Object.entries(summary.credentialing.by_status)
                .sort((a, b) => b[1] - a[1])
                .map(([status, count]) => (
                  <div key={status} style={{ display: 'flex', justifyContent: 'space-between', padding: 'var(--space-2)', borderBottom: '1px solid var(--border-primary)' }}>
                    <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>{status.replace(/_/g, ' ')}</span>
                    <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>{count.toLocaleString()}</span>
                  </div>
                ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

const tableHeadCell: React.CSSProperties = {
  padding: 'var(--space-2)',
  fontSize: 'var(--font-size-xs)',
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textAlign: 'left',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5)' }}>
      <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: subtitle ? 0 : 'var(--space-3)' }}>{title}</h2>
      {subtitle && <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>{subtitle}</p>}
      {children}
    </div>
  );
}

function KPI({ label, value, accent, onClick }: { label: string; value: string; accent?: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        textAlign: 'left',
        padding: 'var(--space-5)',
        borderRadius: 'var(--radius-xl)',
        background: 'var(--surface-glass)',
        border: '1px solid var(--glass-border)',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div style={{ fontSize: 'var(--font-size-xs)', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 'var(--font-size-3xl)', fontWeight: 800, color: accent || 'var(--text-primary)' }}>
        {value}
      </div>
    </button>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: 'var(--space-2)', border: '1px solid var(--border-primary)', borderRadius: 'var(--radius-md)' }}>
      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
        {label}
      </div>
      <div style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function ThresholdPill({ label, count, tone }: { label: string; count: number; tone: 'ok' | 'warning' | 'breach' }) {
  const bg = tone === 'breach' ? 'var(--brand-error)' : tone === 'warning' ? 'var(--brand-warning)' : 'var(--brand-success)';
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 8px', borderRadius: '999px', background: bg, color: 'white', fontSize: 'var(--font-size-xs)', fontWeight: 700 }}>
      <span>{label}</span>
      <span>{count}</span>
    </div>
  );
}

function AlertRow({
  label,
  status,
  value,
  threshold,
  direction,
}: {
  label: string;
  status: 'ok' | 'warning' | 'breach';
  value: number;
  threshold: number;
  direction: 'gt' | 'lt';
}) {
  const color = status === 'breach' ? 'var(--brand-error)' : status === 'warning' ? 'var(--brand-warning)' : 'var(--brand-success)';
  const relation = direction === 'gt' ? '>' : '<';
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-primary)', padding: '4px 0' }}>
      <span style={{ fontSize: 'var(--font-size-sm)' }}>{label}</span>
      <span style={{ fontSize: 'var(--font-size-xs)', color }}>
        {status.toUpperCase()} ({value} {relation} {threshold})
      </span>
    </div>
  );
}

function formatDelta(deltaPct: number | null): string {
  if (deltaPct === null) {
    return 'n/a';
  }
  if (deltaPct > 0) {
    return `+${deltaPct}%`;
  }
  return `${deltaPct}%`;
}

function TrendChart({
  title,
  points,
}: {
  title: string;
  points: { windowDays: number; value: number; deltaPct: number | null }[];
}) {
  const maxValue = points.reduce((max, point) => Math.max(max, point.value), 0);
  return (
    <div style={{ border: '1px solid var(--border-primary)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3)' }}>
      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.03em', marginBottom: 'var(--space-2)' }}>
        {title}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 'var(--space-2)' }}>
        {points.map((point) => {
          const heightPct = maxValue > 0 ? Math.max(8, Math.round((point.value / maxValue) * 100)) : 8;
          const deltaColor = point.deltaPct === null
            ? 'var(--text-tertiary)'
            : (point.deltaPct >= 0 ? 'var(--brand-success)' : 'var(--brand-error)');
          return (
            <div key={point.windowDays} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ height: 56, display: 'flex', alignItems: 'flex-end', background: 'var(--surface-secondary)', borderRadius: 'var(--radius-sm)', padding: 4 }}>
                <div style={{ width: '100%', height: `${heightPct}%`, background: 'var(--brand-primary)', borderRadius: 'var(--radius-sm)' }} />
              </div>
              <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>{point.windowDays}d</div>
              <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 700 }}>{point.value.toLocaleString()}</div>
              <div style={{ fontSize: 'var(--font-size-xs)', color: deltaColor }}>{formatDelta(point.deltaPct)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
