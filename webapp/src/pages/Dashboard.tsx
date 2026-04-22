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

const fmtCurrency = (v: number) =>
  v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery(
    'dashboard-summary',
    () => apiService.get('/dashboard/summary'),
    { staleTime: 30_000 },
  );

  const summary: DashboardData | null = data?.data || null;
  const greeting = user?.email ? user.email.split('@')[0] : 'there';

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

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
        {/* Work queues */}
        <Card title="Work queues" subtitle="Counts of actionable items right now">
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {summary.work_queues.map((q) => (
              <button
                key={q.key}
                onClick={() => navigate(q.link)}
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

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 'var(--space-6)' }}>
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
