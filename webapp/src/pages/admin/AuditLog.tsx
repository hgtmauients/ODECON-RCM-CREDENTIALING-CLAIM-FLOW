/**
 * Admin → Audit Log
 *
 * Read-only window onto SecurityAuditLog. Filters: action / resource_type /
 * resource_id / user_email / success / time range. Each row expands to show
 * the full changes + metadata payload.
 */

import React, { useState } from 'react';
import { useQuery } from 'react-query';
import { apiService } from '@/services/api';
import { Pagination } from '@/components/Pagination';

const PAGE_SIZE = 100;

interface AuditRow {
  id: number;
  user_email: string | null;
  user_role: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  timestamp: string | null;
  ip_address: string | null;
  user_agent: string | null;
  changes: any;
  metadata: any;
  success: boolean;
  error_message: string | null;
}

const isoToInputValue = (iso: string) => iso.slice(0, 16); // YYYY-MM-DDTHH:mm

export default function AuditLog() {
  const [action, setAction] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [resourceId, setResourceId] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [successFilter, setSuccessFilter] = useState<'all' | 'success' | 'failure'>('all');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);

  React.useEffect(() => { setOffset(0); }, [action, resourceType, resourceId, userEmail, successFilter, since, until]);

  const actionsQuery = useQuery('audit-actions', () => apiService.get('/admin/audit-log/_meta/actions'));

  const eventsQuery = useQuery(
    ['audit-log', action, resourceType, resourceId, userEmail, successFilter, since, until, offset],
    () => {
      const params: Record<string, string | number | boolean | undefined> = { limit: PAGE_SIZE, offset };
      if (action) params.action = action;
      if (resourceType) params.resource_type = resourceType;
      if (resourceId) params.resource_id = resourceId;
      if (userEmail) params.user_email = userEmail;
      if (successFilter === 'success') params.success = true;
      if (successFilter === 'failure') params.success = false;
      if (since) params.since = new Date(since).toISOString();
      if (until) params.until = new Date(until).toISOString();
      return apiService.get('/admin/audit-log', params);
    },
    { keepPreviousData: true },
  );

  const rows: AuditRow[] = eventsQuery.data?.data || [];
  const total: number = eventsQuery.data?.total ?? rows.length;
  const knownActions: { action: string; count: number }[] = actionsQuery.data?.data || [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-6)' }}>
        <div>
          <h1 className="page-title">Audit Log</h1>
          <p className="page-subtitle">Every PHI / credential / configuration mutation in this tenant</p>
        </div>
        <button
          className="btn btn-ghost btn-lg"
          onClick={() => {
            const params: Record<string, string | number | boolean | undefined> = { limit: 20000 };
            if (action) params.action = action;
            if (resourceType) params.resource_type = resourceType;
            if (resourceId) params.resource_id = resourceId;
            if (userEmail) params.user_email = userEmail;
            if (successFilter === 'success') params.success = true;
            if (successFilter === 'failure') params.success = false;
            if (since) params.since = new Date(since).toISOString();
            if (until) params.until = new Date(until).toISOString();
            apiService.downloadFile('/admin/audit-log/export.csv', 'audit_log.csv', params).catch((err: any) => {
              alert(err?.message || 'Export failed');
            });
          }}
          title="Download filtered audit events as CSV"
        >
          Export CSV
        </button>
      </div>

      <div className="card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)', display: 'grid', gap: 'var(--space-3)', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
        <select className="input" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All actions</option>
          {knownActions.map((a) => (
            <option key={a.action} value={a.action}>{a.action} ({a.count})</option>
          ))}
        </select>
        <input className="input" placeholder="Resource type (e.g. patient)" value={resourceType} onChange={(e) => setResourceType(e.target.value)} />
        <input className="input" placeholder="Resource ID" value={resourceId} onChange={(e) => setResourceId(e.target.value)} />
        <input className="input" placeholder="User email contains..." value={userEmail} onChange={(e) => setUserEmail(e.target.value)} />
        <select className="input" value={successFilter} onChange={(e) => setSuccessFilter(e.target.value as any)}>
          <option value="all">Success + Failure</option>
          <option value="success">Successes only</option>
          <option value="failure">Failures only</option>
        </select>
        <input type="datetime-local" className="input" value={since} onChange={(e) => setSince(e.target.value)} placeholder="From" />
        <input type="datetime-local" className="input" value={until} onChange={(e) => setUntil(e.target.value)} placeholder="To" />
        {(action || resourceType || resourceId || userEmail || successFilter !== 'all' || since || until) && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { setAction(''); setResourceType(''); setResourceId(''); setUserEmail(''); setSuccessFilter('all'); setSince(''); setUntil(''); }}
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        {eventsQuery.isLoading ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>Loading...</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
            No audit events match these filters.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ background: 'var(--surface-secondary)', borderBottom: '2px solid var(--border-primary)' }}>
              <tr>
                {['When', 'Who', 'Action', 'Resource', 'Status', 'IP', ''].map((h) => (
                  <th key={h} style={{ padding: 'var(--space-3)', textAlign: 'left', fontSize: 'var(--font-size-xs)', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <React.Fragment key={r.id}>
                  <tr style={{ borderBottom: '1px solid var(--border-primary)', cursor: 'pointer' }} onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                    <td style={{ padding: 'var(--space-3)', fontSize: 'var(--font-size-sm)', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                      {r.timestamp ? new Date(r.timestamp).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: 'var(--space-3)', fontSize: 'var(--font-size-sm)' }}>
                      <div>{r.user_email || '—'}</div>
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>{r.user_role || ''}</div>
                    </td>
                    <td style={{ padding: 'var(--space-3)', fontFamily: 'monospace', fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>
                      {r.action}
                    </td>
                    <td style={{ padding: 'var(--space-3)', fontSize: 'var(--font-size-sm)' }}>
                      <div>{r.resource_type || '—'}</div>
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>{r.resource_id}</div>
                    </td>
                    <td style={{ padding: 'var(--space-3)' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-sm)',
                        background: r.success ? 'var(--brand-success)' : 'var(--brand-error)',
                        color: 'white',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600,
                      }}>
                        {r.success ? 'OK' : 'FAIL'}
                      </span>
                    </td>
                    <td style={{ padding: 'var(--space-3)', fontSize: 'var(--font-size-sm)', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                      {r.ip_address || '—'}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)' }}>
                      {expanded === r.id ? '▲' : '▼'}
                    </td>
                  </tr>
                  {expanded === r.id && (
                    <tr style={{ background: 'var(--surface-secondary)' }}>
                      <td colSpan={7} style={{ padding: 'var(--space-4)' }}>
                        <DetailRow label="User-Agent">{r.user_agent || '—'}</DetailRow>
                        {r.error_message && <DetailRow label="Error" tone="danger">{r.error_message}</DetailRow>}
                        {r.changes && (
                          <DetailRow label="Changes">
                            <pre style={preStyle}>{JSON.stringify(r.changes, null, 2)}</pre>
                          </DetailRow>
                        )}
                        {r.metadata && (
                          <DetailRow label="Metadata">
                            <pre style={preStyle}>{JSON.stringify(r.metadata, null, 2)}</pre>
                          </DetailRow>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}

        {!eventsQuery.isLoading && total > 0 && (
          <Pagination
            total={total}
            limit={PAGE_SIZE}
            offset={offset}
            onChange={setOffset}
            loading={eventsQuery.isFetching}
            itemLabel="event"
          />
        )}
      </div>
    </div>
  );
}

const preStyle: React.CSSProperties = {
  margin: '4px 0 0',
  padding: 'var(--space-3)',
  background: 'var(--surface-primary)',
  border: '1px solid var(--border-light)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--font-size-xs)',
  fontFamily: 'monospace',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  maxHeight: 280,
  overflow: 'auto',
};

function DetailRow({ label, children, tone }: { label: string; children: React.ReactNode; tone?: 'danger' }) {
  return (
    <div style={{ marginBottom: 'var(--space-2)' }}>
      <div style={{ fontSize: 'var(--font-size-xs)', fontWeight: 600, color: tone === 'danger' ? 'var(--brand-error)' : 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 'var(--font-size-sm)' }}>{children}</div>
    </div>
  );
}
