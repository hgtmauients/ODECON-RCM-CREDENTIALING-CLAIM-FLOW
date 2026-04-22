/**
 * Settings Page
 * Per-tenant configuration for API keys, SMTP, integrations.
 * Reads/writes via GET/PUT /api/tenants/{id}/settings.
 */

import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import { useAuth } from '@/auth/AuthProvider';
import toast from 'react-hot-toast';

interface SettingField {
  key: string;
  label: string;
  description: string;
  category: string;
  sensitive?: boolean;
  type?: 'text' | 'number' | 'email';
  placeholder?: string;
}

const SETTING_FIELDS: SettingField[] = [
  { key: 'api_cert_key', label: 'API-Cert Key', description: 'License verification API key (50 free/month)', category: 'API-Cert', sensitive: true, placeholder: 'lva_...' },
  { key: 'caqh_org_id', label: 'CAQH Org ID', description: 'CAQH ProView organization ID', category: 'CAQH ProView', placeholder: '12345' },
  { key: 'caqh_username', label: 'CAQH Username', description: 'CAQH ProView API username', category: 'CAQH ProView' },
  { key: 'caqh_password', label: 'CAQH Password', description: 'CAQH ProView API password', category: 'CAQH ProView', sensitive: true },
  { key: 'smtp_host', label: 'SMTP Host', description: 'Email server hostname', category: 'Email (SMTP)', placeholder: 'smtp.sendgrid.net' },
  { key: 'smtp_port', label: 'SMTP Port', description: 'Default: 587', category: 'Email (SMTP)', type: 'number', placeholder: '587' },
  { key: 'smtp_user', label: 'SMTP User', description: 'Email server username / API key name', category: 'Email (SMTP)' },
  { key: 'smtp_pass', label: 'SMTP Password', description: 'Email server password / API key', category: 'Email (SMTP)', sensitive: true },
  { key: 'from_email', label: 'From Email', description: 'Sender address for system emails', category: 'Email (SMTP)', type: 'email', placeholder: 'billing@practice.com' },
  { key: 'webhook_secret', label: 'Webhook Secret', description: 'HMAC secret for provider signup webhooks', category: 'Webhooks', sensitive: true },
];

const CATEGORIES = [...new Set(SETTING_FIELDS.map(f => f.category))];

function SourceBadge({ source }: { source: string }) {
  if (source === 'db') {
    return <span style={{ fontSize: 'var(--font-size-xs)', padding: '1px 6px', borderRadius: 'var(--radius-sm)', background: 'var(--brand-primary)', color: 'white', marginLeft: 6 }}>Saved</span>;
  }
  if (source === 'env') {
    return <span style={{ fontSize: 'var(--font-size-xs)', padding: '1px 6px', borderRadius: 'var(--radius-sm)', background: 'var(--brand-warning, #e6a817)', color: 'white', marginLeft: 6 }}>Env var</span>;
  }
  return null;
}

export default function Settings() {
  const { user } = useAuth();
  const tenantId = user?.tenant_id || '';
  const queryClient = useQueryClient();

  const [form, setForm] = useState<Record<string, string>>({});
  const [showFields, setShowFields] = useState<Record<string, boolean>>({});
  const [dirty, setDirty] = useState(false);

  const { data: settingsResp, isLoading } = useQuery(
    ['tenant-settings', tenantId],
    () => apiService.get(`/tenants/${tenantId}/settings`),
    { enabled: !!tenantId }
  );

  const settings: Record<string, string> = settingsResp?.data || {};

  useEffect(() => {
    if (settingsResp?.data) {
      const initial: Record<string, string> = {};
      SETTING_FIELDS.forEach(f => {
        initial[f.key] = settingsResp.data[f.key] ?? '';
      });
      setForm(initial);
      setDirty(false);
    }
  }, [settingsResp]);

  const saveMutation = useMutation(
    (payload: Record<string, string>) =>
      apiService.put(`/tenants/${tenantId}/settings`, payload),
    {
      onSuccess: () => {
        toast.success('Settings saved');
        setDirty(false);
        queryClient.invalidateQueries(['tenant-settings', tenantId]);
      },
      onError: (err: any) => { toast.error(err.message || 'Failed to save settings'); },
    }
  );

  const handleChange = (key: string, value: string) => {
    setForm(prev => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const handleSave = () => {
    saveMutation.mutate(form);
  };

  // Test buttons
  const [testingSmtp, setTestingSmtp] = useState(false);
  const [testingApiCert, setTestingApiCert] = useState(false);
  const [testingCaqh, setTestingCaqh] = useState(false);

  const testSmtp = async () => {
    setTestingSmtp(true);
    try {
      const resp = await apiService.post(`/tenants/${tenantId}/settings/test-smtp`, { to: user?.email });
      if (resp.success) toast.success(resp.message || 'Test email sent');
      else toast.error(resp.error || 'SMTP test failed');
    } catch (e: any) { toast.error(e.message || 'SMTP test failed'); }
    setTestingSmtp(false);
  };

  const testApiCert = async () => {
    setTestingApiCert(true);
    try {
      const resp = await apiService.post(`/tenants/${tenantId}/settings/test-api-cert`, {});
      if (resp.success) {
        const d = resp.data || {};
        toast.success(`API-Cert connected — ${d.requests_used ?? '?'} / ${d.monthly_quota ?? '50'} used`);
      } else {
        toast.error(resp.error || 'API-Cert test failed');
      }
    } catch (e: any) { toast.error(e.message || 'API-Cert test failed'); }
    setTestingApiCert(false);
  };

  const testCaqh = async () => {
    setTestingCaqh(true);
    try {
      const resp = await apiService.post(`/tenants/${tenantId}/settings/test-caqh`, {});
      if (resp.success) toast.success(resp.message || 'CAQH connected');
      else toast.error(resp.error || 'CAQH test failed');
    } catch (e: any) { toast.error(e.message || 'CAQH test failed'); }
    setTestingCaqh(false);
  };

  // Build the health URL from VITE_API_BASE_URL.
  // - Production (set to https://api.noodledoc.com/api) → strip /api → https://api.noodledoc.com/health
  // - Local dev (default /api proxied by Vite) → strip /api → '' → use /health (Vite proxy)
  const healthUrl = (() => {
    const raw = (import.meta.env?.VITE_API_BASE_URL as string | undefined) || '/api';
    const stripped = raw.replace(/\/api\/?$/, '');
    // If stripping leaves an empty string, prefix with / so we hit the same origin
    return stripped ? `${stripped}/health` : '/health';
  })();

  const { data: healthData } = useQuery(
    'health',
    () => fetch(healthUrl).then(r => r.json()).catch(() => null),
    { refetchInterval: 30000 }
  );

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--space-8)' }}>
        <div style={{ width: 24, height: 24, border: '3px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-6)' }}>
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Configure API keys, integrations, and email for your organization</p>
        </div>
        <button
          className="btn btn-primary"
          disabled={!dirty || saveMutation.isLoading}
          onClick={handleSave}
          style={{ minWidth: 120 }}
        >
          {saveMutation.isLoading ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {/* System Status */}
      <div className="card" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-6)' }}>
        <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>System Status</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-3)' }}>
          <div className="stat-card">
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 2 }}>Backend</div>
            <div style={{ fontWeight: 700, color: healthData?.status === 'ok' ? 'var(--brand-success)' : 'var(--brand-error)' }}>
              {healthData?.status === 'ok' ? 'Online' : 'Offline'}
            </div>
          </div>
          <div className="stat-card">
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 2 }}>Database</div>
            <div style={{ fontWeight: 700, color: healthData?.database ? 'var(--brand-success)' : 'var(--brand-error)' }}>
              {healthData?.database ? 'Connected' : 'Disconnected'}
            </div>
          </div>
          <div className="stat-card">
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 2 }}>Tenant</div>
            <div style={{ fontWeight: 700, fontSize: 'var(--font-size-sm)' }}>{tenantId ? tenantId.substring(0, 8) + '...' : '—'}</div>
          </div>
        </div>
      </div>

      {/* Per-category settings */}
      {CATEGORIES.map(cat => {
        const fields = SETTING_FIELDS.filter(f => f.category === cat);
        const testButton = cat === 'Email (SMTP)' ? (
          <button className="btn btn-ghost btn-sm" onClick={testSmtp} disabled={testingSmtp} style={{ fontSize: 'var(--font-size-xs)' }}>
            {testingSmtp ? 'Sending...' : 'Send Test Email'}
          </button>
        ) : cat === 'API-Cert' ? (
          <button className="btn btn-ghost btn-sm" onClick={testApiCert} disabled={testingApiCert} style={{ fontSize: 'var(--font-size-xs)' }}>
            {testingApiCert ? 'Checking...' : 'Check Usage'}
          </button>
        ) : cat === 'CAQH ProView' ? (
          <button className="btn btn-ghost btn-sm" onClick={testCaqh} disabled={testingCaqh} style={{ fontSize: 'var(--font-size-xs)' }}>
            {testingCaqh ? 'Testing...' : 'Test Connection'}
          </button>
        ) : null;

        return (
          <div key={cat} className="card" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <h2 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, color: 'var(--text-primary)' }}>{cat}</h2>
              {testButton}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              {fields.map(f => {
                const source = settings[`${f.key}_source`] || 'none';
                const isSensitive = !!f.sensitive;
                const showing = !!showFields[f.key];
                const currentValue = form[f.key] ?? '';
                const isPlaceholder = isSensitive && currentValue.startsWith('***');

                return (
                  <div key={f.key} style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: 'var(--space-3)', alignItems: 'center', padding: 'var(--space-2) 0' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>
                        {f.label}
                        <SourceBadge source={source} />
                      </div>
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginTop: 2 }}>{f.description}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                      <input
                        type={isSensitive && !showing ? 'password' : (f.type || 'text')}
                        className="form-input"
                        value={currentValue}
                        placeholder={isPlaceholder ? '' : (f.placeholder || '')}
                        onFocus={() => {
                          if (isPlaceholder) {
                            handleChange(f.key, '');
                          }
                        }}
                        onChange={(e) => handleChange(f.key, e.target.value)}
                        style={{ flex: 1, fontSize: 'var(--font-size-sm)', padding: '6px 10px' }}
                      />
                      {isSensitive && (
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ fontSize: 10, padding: '4px 8px', whiteSpace: 'nowrap' }}
                          onClick={() => setShowFields(prev => ({ ...prev, [f.key]: !prev[f.key] }))}
                        >
                          {showing ? 'Hide' : 'Show'}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* System-level info */}
      <div style={{ padding: 'var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-lg)', fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
        <strong>System-level settings</strong> (DATABASE_URL, JWT config, encryption key, CORS, storage paths) are configured via environment variables or <code>docker-compose.yml</code> and require a container restart. Only per-tenant integration settings are editable above.
      </div>
    </div>
  );
}
