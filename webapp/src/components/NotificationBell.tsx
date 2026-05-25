/**
 * Notification bell + drawer.
 *
 * Polls /notifications/unread-count every 60s for the badge. The drawer
 * fetches the recent list lazily on open. Click an item → mark-read +
 * navigate to its link_url.
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import { getSafeInternalPath } from '@/utils/safeNavigation';

interface NotifRow {
  id: string;
  type: string;
  severity: 'info' | 'warning' | 'error' | 'success' | string;
  title: string;
  message: string | null;
  link_url: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string | null;
}

const severityColor = (sev: string) => {
  switch (sev) {
    case 'error': return 'var(--brand-error)';
    case 'warning': return 'var(--brand-warning, #f59e0b)';
    case 'success': return 'var(--brand-success)';
    default: return 'var(--brand-primary)';
  }
};

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const unreadQuery = useQuery(
    'notifications-unread',
    () => apiService.get('/notifications/unread-count'),
    { refetchInterval: 60_000, staleTime: 30_000 },
  );

  const listQuery = useQuery(
    ['notifications-list'],
    () => apiService.get('/notifications', { limit: 30 }),
    { enabled: open, staleTime: 15_000 },
  );

  const markRead = useMutation(
    (id: string) => apiService.post(`/notifications/${id}/read`),
    {
      onSuccess: () => {
        qc.invalidateQueries('notifications-unread');
        qc.invalidateQueries(['notifications-list']);
      },
    },
  );

  const markAllRead = useMutation(
    () => apiService.post('/notifications/read-all'),
    {
      onSuccess: () => {
        qc.invalidateQueries('notifications-unread');
        qc.invalidateQueries(['notifications-list']);
      },
    },
  );

  const unread = unreadQuery.data?.data?.unread ?? 0;
  const rows: NotifRow[] = listQuery.data?.data || [];

  const handleClick = async (n: NotifRow) => {
    if (!n.is_read) markRead.mutate(n.id);
    const safePath = getSafeInternalPath(n.link_url);
    if (safePath) {
      setOpen(false);
      navigate(safePath);
    }
  };

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ''}`}
        style={{
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.1)',
          color: '#e2e8f0',
          padding: '6px 10px',
          borderRadius: 'var(--radius-md)',
          cursor: 'pointer',
          position: 'relative',
          fontSize: 14,
          width: '100%',
          textAlign: 'left',
        }}
      >
        Notifications
        {unread > 0 && (
          <span
            aria-hidden
            style={{
              position: 'absolute',
              top: 6,
              right: 8,
              background: 'var(--brand-error)',
              color: 'white',
              fontSize: 10,
              fontWeight: 700,
              padding: '1px 6px',
              borderRadius: 'var(--radius-full)',
              minWidth: 16,
              textAlign: 'center',
            }}
          >
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <div
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 200 }}
          />
          <div
            role="dialog"
            aria-label="Notifications"
            style={{
              position: 'fixed',
              top: 60,
              left: 16,
              width: 360,
              maxHeight: 'calc(100vh - 80px)',
              background: 'var(--surface-primary)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-xl)',
              boxShadow: '0 10px 30px rgba(0,0,0,0.18)',
              zIndex: 210,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 'var(--space-4)', borderBottom: '1px solid var(--border-primary)' }}>
              <strong style={{ fontSize: 'var(--font-size-base)' }}>Notifications</strong>
              {unread > 0 && (
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={markAllRead.isLoading}
                  onClick={() => markAllRead.mutate()}
                  style={{ fontSize: 'var(--font-size-xs)' }}
                >
                  Mark all read
                </button>
              )}
            </div>

            <div style={{ overflowY: 'auto', flex: 1 }}>
              {listQuery.isLoading ? (
                <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-secondary)' }}>Loading…</div>
              ) : rows.length === 0 ? (
                <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  Nothing here yet.
                </div>
              ) : rows.map((n) => (
                <button
                  key={n.id}
                  onClick={() => handleClick(n)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: 'var(--space-3) var(--space-4)',
                    borderBottom: '1px solid var(--border-primary)',
                    background: n.is_read ? 'transparent' : 'rgba(59, 130, 246, 0.06)',
                    border: 'none',
                    borderLeft: `3px solid ${severityColor(n.severity)}`,
                    cursor: n.link_url ? 'pointer' : 'default',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <strong style={{ fontSize: 'var(--font-size-sm)' }}>{n.title}</strong>
                    {!n.is_read && (
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: severityColor(n.severity), flex: '0 0 8px', marginTop: 4 }} />
                    )}
                  </div>
                  {n.message && (
                    <p style={{ margin: '4px 0 0', fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                      {n.message}
                    </p>
                  )}
                  <p style={{ margin: '4px 0 0', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
                    {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
