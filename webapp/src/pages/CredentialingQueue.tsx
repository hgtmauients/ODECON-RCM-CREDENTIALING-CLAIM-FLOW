import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatDate } from '@/utils/formatters';
import toast from 'react-hot-toast';
import { getStateLicenseFormat, validateLicenseNumber } from '@/utils/stateLicenseFormats';

interface CredentialingRecord {
  provider_id: string;
  signup_data: {
    first_name: string;
    last_name: string;
    email: string;
    npi: string;
    state_code: string;
    license_number: string;
    specialty?: string;
  };
  credentialing_status: 'pending' | 'in_progress' | 'passed' | 'failed' | 'requires_review';
  overall_score: number;
  signup_date: string;
  completed_at?: string;
  npi_verification?: Record<string, unknown>;
  state_license_verification?: Record<string, unknown>;
  background_check?: Record<string, unknown>;
  oig_check?: Record<string, unknown>;
  sam_check?: Record<string, unknown>;
}

export default function CredentialingQueue() {
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [selectedProvider, setSelectedProvider] = useState<CredentialingRecord | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [approvalNotes, setApprovalNotes] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProvider, setEditingProvider] = useState<CredentialingRecord | null>(null);
  const [addForm, setAddForm] = useState<Record<string, any>>({
    first_name: '', last_name: '', email: '', npi: '', state_code: '', license_number: '', specialty: '', provider_type: 'MD', phone: '',
    licenses: [{ state: '', license_number: '', expiration: '', status: 'active' }],
    specialties: [{ specialty: '', board: '', certified: false, expiration: '' }],
    dea_certificates: [{ dea_number: '', state: '', schedules: '', expiration: '' }],
    cned_certificates: [{ state: '', certificate_number: '', expiration: '' }],
  });
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery(
    ['credentialing', selectedStatus],
    () => apiService.get('/credentialing/', { status: selectedStatus || undefined })
  );

  const approveMutation = useMutation(
    ({ providerId, notes }: { providerId: string; notes?: string }) =>
      apiService.post(`/credentialing/${providerId}/approve`, { notes }),
    {
      onSuccess: (response: any) => {
        queryClient.invalidateQueries(['credentialing']);
        const payerResult = response?.payer_enrollment;
        if (payerResult?.cases_created > 0) {
          toast.success(`Provider approved. ${payerResult.cases_created} payer enrollment case(s) created.`);
        } else {
          toast.success('Provider approved.');
        }
        setSelectedProvider(null);
        setApprovalNotes('');
      },
      onError: (err: any) => { toast.error(err?.message || 'Failed to approve provider'); },
    }
  );

  const rejectMutation = useMutation(
    ({ providerId, reason }: { providerId: string; reason: string }) =>
      apiService.post(`/credentialing/${providerId}/reject`, { reason }),
    {
      onSuccess: () => {
        toast.success('Provider rejected');
        queryClient.invalidateQueries(['credentialing']);
        setSelectedProvider(null);
        setRejectionReason('');
      },
      onError: (err: any) => { toast.error(err?.message || 'Failed to reject provider'); },
    }
  );

  const createMutation = useMutation(
    (data: Record<string, string>) => apiService.post('/credentialing/manual', data),
    {
      onSuccess: (response: any) => {
        toast.success(`Provider ${response.provider_id} created. Verification checks running.`);
        queryClient.invalidateQueries(['credentialing']);
        setShowAddModal(false);
        setAddForm({ first_name: '', last_name: '', email: '', npi: '', state_code: '', license_number: '', specialty: '', provider_type: 'MD', phone: '' });
      },
      onError: () => { toast.error('Failed to create provider'); },
    }
  );

  const updateMutation = useMutation(
    ({ providerId, data }: { providerId: string; data: Record<string, string> }) =>
      apiService.put(`/credentialing/${providerId}`, data),
    {
      onSuccess: () => {
        toast.success('Provider updated');
        queryClient.invalidateQueries(['credentialing']);
        setEditingProvider(null);
      },
      onError: () => { toast.error('Failed to update provider'); },
    }
  );

  const deleteMutation = useMutation(
    (providerId: string) => apiService.delete(`/credentialing/${providerId}`),
    {
      onSuccess: () => {
        toast.success('Provider deleted');
        queryClient.invalidateQueries(['credentialing']);
        setSelectedProvider(null);
      },
      onError: () => { toast.error('Failed to delete provider'); },
    }
  );

  const rerunMutation = useMutation(
    (providerId: string) => apiService.post(`/credentialing/${providerId}/rerun-checks`),
    {
      onSuccess: () => {
        toast.success('Verification checks re-initiated');
        queryClient.invalidateQueries(['credentialing']);
      },
      onError: (err: any) => { toast.error(err?.message || 'Failed to re-run checks'); },
    }
  );

  const records: CredentialingRecord[] = data?.data || [];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'passed': return '#25D366';
      case 'failed': return '#ef4444';
      case 'requires_review': return '#F98A33';
      case 'in_progress': return '#009DDD';
      default: return '#6b7280';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return '#25D366';
    if (score >= 60) return '#F98A33';
    return '#ef4444';
  };

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      <div style={{ marginBottom: 'var(--space-6)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 'var(--font-size-3xl)', fontWeight: 800, marginBottom: 'var(--space-2)' }}>
            Provider Credentialing Queue
          </h1>
          <p style={{ color: 'var(--text-secondary)' }}>
            Review and approve provider credentialing applications
          </p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={() => setShowAddModal(true)}>
          Add Provider
        </button>
      </div>

      {/* Filters */}
      <div style={{ 
        display: 'flex', 
        gap: 'var(--space-3)', 
        marginBottom: 'var(--space-6)',
        flexWrap: 'wrap'
      }}>
        <button
          onClick={() => setSelectedStatus('')}
          style={{
            padding: 'var(--space-2) var(--space-4)',
            borderRadius: 'var(--radius-lg)',
            border: selectedStatus === '' ? '2px solid var(--color-primary)' : '1px solid var(--border-primary)',
            background: selectedStatus === '' ? 'var(--color-primary)' : 'transparent',
            color: selectedStatus === '' ? 'white' : 'var(--text-primary)',
            cursor: 'pointer'
          }}
        >
          All ({records.length})
        </button>
        <button
          onClick={() => setSelectedStatus('requires_review')}
          style={{
            padding: 'var(--space-2) var(--space-4)',
            borderRadius: 'var(--radius-lg)',
            border: selectedStatus === 'requires_review' ? '2px solid #F98A33' : '1px solid var(--border-primary)',
            background: selectedStatus === 'requires_review' ? '#F98A33' : 'transparent',
            color: selectedStatus === 'requires_review' ? 'white' : 'var(--text-primary)',
            cursor: 'pointer'
          }}
        >
          Review ({records.filter(r => r.credentialing_status === 'requires_review').length})
        </button>
        <button
          onClick={() => setSelectedStatus('pending')}
          style={{
            padding: 'var(--space-2) var(--space-4)',
            borderRadius: 'var(--radius-lg)',
            border: selectedStatus === 'pending' ? '2px solid #6b7280' : '1px solid var(--border-primary)',
            background: selectedStatus === 'pending' ? '#6b7280' : 'transparent',
            color: selectedStatus === 'pending' ? 'white' : 'var(--text-primary)',
            cursor: 'pointer'
          }}
        >
          Pending ({records.filter(r => r.credentialing_status === 'pending').length})
        </button>
      </div>

      {/* Credentialing List */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
          <div className="loading-spinner" />
        </div>
      ) : error ? (
        <div style={{ 
          padding: 'var(--space-6)', 
          background: 'var(--surface-error)', 
          borderRadius: 'var(--radius-lg)',
          color: 'var(--text-error)'
        }}>
          Error loading credentialing queue
        </div>
      ) : records.length === 0 ? (
        <div style={{ 
          padding: 'var(--space-12)', 
          textAlign: 'center',
          background: 'var(--surface-glass)',
          borderRadius: 'var(--radius-xl)'
        }}>
          <PremiumIcon name="credentialing" size="lg" />
          <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-secondary)' }}>
            No providers pending credentialing
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
          {records.map((record) => (
            <div
              key={record.provider_id}
              onClick={() => setSelectedProvider(record)}
              style={{
                background: 'var(--surface-glass)',
                borderRadius: 'var(--radius-xl)',
                padding: 'var(--space-6)',
                border: selectedProvider?.provider_id === record.provider_id 
                  ? '2px solid var(--color-primary)' 
                  : '1px solid var(--border-primary)',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <div>
                  <h3 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
                    {record.signup_data.first_name} {record.signup_data.last_name}
                  </h3>
                  <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap', marginBottom: 'var(--space-3)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      <PremiumIcon name="npi" size="xs" /> NPI: {record.signup_data.npi}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      <PremiumIcon name="state" size="xs" /> {record.signup_data.state_code}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      <PremiumIcon name="specialty" size="xs" /> {record.signup_data.specialty || 'N/A'}
                    </span>
                  </div>
                  <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Signed up: {formatDate(record.signup_date)}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div
                    style={{
                      padding: 'var(--space-2) var(--space-4)',
                      borderRadius: 'var(--radius-lg)',
                      background: getStatusColor(record.credentialing_status) + '20',
                      color: getStatusColor(record.credentialing_status),
                      fontSize: 'var(--font-size-sm)',
                      fontWeight: 600,
                      marginBottom: 'var(--space-2)'
                    }}
                  >
                    {record.credentialing_status.replace('_', ' ').toUpperCase()}
                  </div>
                  {record.overall_score !== null && (
                    <div
                      style={{
                        fontSize: 'var(--font-size-2xl)',
                        fontWeight: 800,
                        color: getScoreColor(record.overall_score)
                      }}
                    >
                      {record.overall_score}/100
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedProvider && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 'var(--space-6)'
          }}
          onClick={() => setSelectedProvider(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--surface-elevated)',
              borderRadius: 'var(--radius-2xl)',
              padding: 'var(--space-8)',
              maxWidth: '800px',
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto'
            }}
          >
            <h2 style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 800, marginBottom: 'var(--space-6)' }}>
              Provider Credentialing Details
            </h2>

            {/* Provider Info */}
            <div style={{ marginBottom: 'var(--space-6)' }}>
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: 'var(--space-3)' }}>
                Provider Information
              </h3>
              <div style={{ display: 'grid', gap: 'var(--space-2)' }}>
                <div><strong>Name:</strong> {selectedProvider.signup_data.first_name} {selectedProvider.signup_data.last_name}</div>
                <div><strong>Email:</strong> {selectedProvider.signup_data.email}</div>
                <div><strong>NPI:</strong> {selectedProvider.signup_data.npi}</div>
                <div><strong>State:</strong> {selectedProvider.signup_data.state_code}</div>
                <div><strong>License:</strong> {selectedProvider.signup_data.license_number}</div>
                <div><strong>Specialty:</strong> {selectedProvider.signup_data.specialty || 'N/A'}</div>
              </div>
            </div>

            {/* Verification Results */}
            <div style={{ marginBottom: 'var(--space-6)' }}>
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: 'var(--space-3)' }}>
                Verification Results
              </h3>
              <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
                {selectedProvider.npi_verification && (
                  <div style={{ padding: 'var(--space-3)', background: 'var(--surface-glass)', borderRadius: 'var(--radius-lg)' }}>
                    <strong>NPI:</strong> {selectedProvider.npi_verification.verified ? 'VERIFIED' : 'NOT VERIFIED'}
                  </div>
                )}
                {selectedProvider.state_license_verification && (
                  <div style={{ padding: 'var(--space-3)', background: 'var(--surface-glass)', borderRadius: 'var(--radius-lg)' }}>
                    <strong>State License:</strong> {selectedProvider.state_license_verification.verified ? 'VERIFIED' : 'NOT VERIFIED'}
                  </div>
                )}
                {selectedProvider.oig_check && (
                  <div style={{ padding: 'var(--space-3)', background: 'var(--surface-glass)', borderRadius: 'var(--radius-lg)' }}>
                    <strong>OIG Check:</strong> {selectedProvider.oig_check.excluded ? 'EXCLUDED' : 'CLEAR'}
                  </div>
                )}
                {selectedProvider.sam_check && (
                  <div style={{ padding: 'var(--space-3)', background: 'var(--surface-glass)', borderRadius: 'var(--radius-lg)' }}>
                    <strong>SAM Check:</strong> {selectedProvider.sam_check.excluded ? 'EXCLUDED' : 'CLEAR'}
                  </div>
                )}
              </div>
            </div>

            {/* Actions — only when reviewable AND not currently running checks */}
            {(() => {
              const isReviewable = ['requires_review', 'pending'].includes(selectedProvider.credentialing_status);
              const isRunning = selectedProvider.credentialing_status === 'in_progress';
              if (!isReviewable && !isRunning) return null;
              return (
                <div style={{ display: 'flex', gap: 'var(--space-3)', flexDirection: 'column' }}>
                  {isRunning && (
                    <div style={{ padding: 'var(--space-3)', background: 'rgba(0,157,221,0.1)', border: '1px solid #009DDD', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-sm)' }}>
                      Verification checks in progress. Approve / Reject are disabled until checks complete.
                    </div>
                  )}
                  <div>
                    <label style={{ display: 'block', marginBottom: 'var(--space-2)' }}>Approval Notes (Optional)</label>
                    <textarea
                      value={approvalNotes}
                      onChange={(e) => setApprovalNotes(e.target.value)}
                      disabled={isRunning}
                      style={{ width: '100%', padding: 'var(--space-3)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-primary)', background: 'var(--surface-glass)' }}
                      rows={3}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 'var(--space-2)' }}>Rejection Reason</label>
                    <textarea
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      disabled={isRunning}
                      style={{ width: '100%', padding: 'var(--space-3)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-primary)', background: 'var(--surface-glass)' }}
                      rows={3}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
                    <button
                      onClick={() => approveMutation.mutate({ providerId: selectedProvider.provider_id, notes: approvalNotes })}
                      disabled={approveMutation.isLoading || isRunning}
                      style={{ flex: 1, padding: 'var(--space-4)', borderRadius: 'var(--radius-lg)', background: '#25D366', color: 'white', border: 'none', cursor: (approveMutation.isLoading || isRunning) ? 'not-allowed' : 'pointer', opacity: (approveMutation.isLoading || isRunning) ? 0.5 : 1 }}
                    >
                      Approve Provider
                    </button>
                    <button
                      onClick={() => rejectMutation.mutate({ providerId: selectedProvider.provider_id, reason: rejectionReason })}
                      disabled={rejectMutation.isLoading || !rejectionReason || isRunning}
                      style={{ flex: 1, padding: 'var(--space-4)', borderRadius: 'var(--radius-lg)', background: '#ef4444', color: 'white', border: 'none', cursor: (rejectMutation.isLoading || !rejectionReason || isRunning) ? 'not-allowed' : 'pointer', opacity: (rejectMutation.isLoading || !rejectionReason || isRunning) ? 0.5 : 1 }}
                    >
                      Reject Provider
                    </button>
                  </div>
                </div>
              );
            })()}

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-6)', borderTop: '1px solid var(--border-light)', paddingTop: 'var(--space-4)' }}>
              <button className="btn btn-ghost btn-sm" onClick={() => { setEditingProvider(selectedProvider); setShowAddModal(true); setSelectedProvider(null); }}>
                Edit
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={selectedProvider.credentialing_status === 'in_progress' || rerunMutation.isLoading}
                onClick={() => rerunMutation.mutate(selectedProvider.provider_id)}
                title={selectedProvider.credentialing_status === 'in_progress' ? 'Already running' : 'Re-run all verification checks'}
              >
                {rerunMutation.isLoading ? 'Re-running...' : selectedProvider.credentialing_status === 'in_progress' ? 'Running...' : 'Re-run Checks'}
              </button>
              <button className="btn btn-ghost btn-sm" style={{ color: 'var(--brand-error)' }} onClick={() => {
                if (confirm('Delete this provider? This cannot be undone.')) {
                  deleteMutation.mutate(selectedProvider.provider_id);
                }
              }}>
                Delete
              </button>
              <div style={{ flex: 1 }} />
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedProvider(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add/Edit Provider Modal */}
      {showAddModal && (() => {
        const form = editingProvider ? { ...(editingProvider.signup_data as any || {}), licenses: (editingProvider as any).licenses || [], specialties: (editingProvider as any).specialties || [], dea_certificates: (editingProvider as any).dea_certificates || [], cned_certificates: (editingProvider as any).cned_certificates || [] } : addForm;
        const setForm = (updates: Record<string, any>) => {
          if (editingProvider) {
            setEditingProvider({ ...editingProvider, signup_data: { ...editingProvider.signup_data, ...updates }, ...(['licenses','specialties','dea_certificates','cned_certificates'].some(k => k in updates) ? updates : {}) } as any);
          } else {
            setAddForm(prev => ({ ...prev, ...updates }));
          }
        };
        const setArray = (key: string, arr: any[]) => {
          if (editingProvider) {
            setEditingProvider({ ...editingProvider, [key]: arr } as any);
          } else {
            setAddForm(prev => ({ ...prev, [key]: arr }));
          }
        };

        const inputStyle = { padding: '6px 10px', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-sm)', width: '100%' };
        const selectStyle = { ...inputStyle, background: 'var(--surface-primary)', color: 'var(--text-primary)' };
        const labelStyle: React.CSSProperties = { display: 'block', fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.04em' };

        const US_STATES = [
          'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME',
          'MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI',
          'SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','AS','GU','MP','PR','VI',
        ];
        const BOARDS = [
          'ABMS','ABPN','ABIM','ABS','ABP','ABFM','ABOG','ABPath','ABR','ABEM','ABA','ABPM',
          'ABNS','ABU','ABOS','ABD','ABOOPH','ABOTO','ABTPM','ABNM','AOA','NBOME','Other',
        ];
        const StateSelect = ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
          <select style={selectStyle} value={value} onChange={e => onChange(e.target.value)}>
            <option value="">--</option>
            {US_STATES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        );

        return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: 40, zIndex: 100, overflowY: 'auto' }} onClick={() => { setShowAddModal(false); setEditingProvider(null); }}>
          <div style={{ background: 'var(--surface-primary)', borderRadius: 'var(--radius-xl)', padding: 'var(--space-6)', width: 640, marginBottom: 40 }} onClick={e => e.stopPropagation()}>
            <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)' }}>
              {editingProvider ? 'Edit Provider' : 'Add Provider'}
            </h2>

            {/* Basic Info */}
            <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 'var(--space-2)', marginTop: 'var(--space-2)' }}>Basic Information</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
              <div><label style={labelStyle}>First Name *</label><input style={inputStyle} value={form.first_name || ''} onChange={e => setForm({ first_name: e.target.value })} /></div>
              <div><label style={labelStyle}>Last Name *</label><input style={inputStyle} value={form.last_name || ''} onChange={e => setForm({ last_name: e.target.value })} /></div>
              <div><label style={labelStyle}>NPI *</label><input style={inputStyle} value={form.npi || ''} onChange={e => setForm({ npi: e.target.value })} maxLength={10} /></div>
              <div><label style={labelStyle}>Provider Type</label>
                <select style={selectStyle} value={form.provider_type || 'MD'} onChange={e => setForm({ provider_type: e.target.value })}>
                  <option value="MD">MD - Doctor of Medicine</option>
                  <option value="DO">DO - Doctor of Osteopathy</option>
                  <option value="DPM">DPM - Podiatrist</option>
                  <option value="PA">PA - Physician Assistant</option>
                  <option value="NP">NP - Nurse Practitioner</option>
                  <option value="PhD">PhD - Psychologist</option>
                  <option value="LCSW">LCSW - Social Worker</option>
                </select>
              </div>
              <div><label style={labelStyle}>Email</label><input style={inputStyle} value={form.email || ''} onChange={e => setForm({ email: e.target.value })} /></div>
              <div><label style={labelStyle}>Phone</label><input style={inputStyle} value={form.phone || ''} onChange={e => setForm({ phone: e.target.value })} /></div>
            </div>

            {/* State Licenses */}
            <div style={{ marginBottom: 'var(--space-4)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-secondary)' }}>State Medical Licenses</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setArray('licenses', [...(form.licenses || []), { state: '', license_number: '', expiration: '', status: 'active' }])}>+ Add</button>
              </div>
              {(form.licenses || []).map((lic: any, i: number) => {
                const fmt = getStateLicenseFormat(lic.state);
                const validation = lic.license_number ? validateLicenseNumber(lic.state, lic.license_number) : { valid: true, message: '' };
                return (
                <div key={i} style={{ marginBottom: 'var(--space-2)' }}>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                    <div style={{ width: 70 }}><label style={labelStyle}>State</label><StateSelect value={lic.state} onChange={v => { const a = [...form.licenses]; a[i] = { ...a[i], state: v }; setArray('licenses', a); }} /></div>
                    <div style={{ width: 100 }}><label style={labelStyle}>License Type</label>
                      <select style={selectStyle} value={lic.license_type || 'MD'} onChange={e => { const a = [...form.licenses]; a[i] = { ...a[i], license_type: e.target.value }; setArray('licenses', a); }}>
                        <option value="MD">MD</option><option value="DO">DO</option><option value="DPM">DPM</option><option value="PA">PA</option><option value="NP">NP</option><option value="RN">RN</option>
                      </select>
                    </div>
                    <div style={{ flex: 1 }}><label style={labelStyle}>License #</label><input style={{ ...inputStyle, borderColor: !validation.valid ? 'var(--brand-error)' : undefined }} value={lic.license_number} placeholder={fmt?.placeholder || ''} onChange={e => { const a = [...form.licenses]; a[i] = { ...a[i], license_number: e.target.value }; setArray('licenses', a); }} /></div>
                    <div style={{ width: 90 }}><label style={labelStyle}>Status</label>
                      <select style={selectStyle} value={lic.status || 'active'} onChange={e => { const a = [...form.licenses]; a[i] = { ...a[i], status: e.target.value }; setArray('licenses', a); }}>
                        <option value="active">Active</option><option value="inactive">Inactive</option><option value="expired">Expired</option><option value="pending">Pending</option>
                      </select>
                    </div>
                    <div style={{ width: 120 }}><label style={labelStyle}>Expiration</label><input type="date" style={inputStyle} value={lic.expiration} onChange={e => { const a = [...form.licenses]; a[i] = { ...a[i], expiration: e.target.value }; setArray('licenses', a); }} /></div>
                    {form.licenses.length > 1 && <button className="btn btn-ghost btn-sm" style={{ color: 'var(--brand-error)', marginTop: 14 }} onClick={() => { const a = form.licenses.filter((_: any, j: number) => j !== i); setArray('licenses', a); }}>X</button>}
                  </div>
                  {fmt && (
                    <div style={{ fontSize: 10, color: !validation.valid ? 'var(--brand-error)' : 'var(--text-tertiary)', marginTop: 2, marginLeft: 172 }}>
                      {!validation.valid ? validation.message : `${fmt.board} -- Format: ${fmt.format} -- Renewal: ${fmt.renewalNote}`}
                    </div>
                  )}
                </div>
                );
              })}
            </div>

            {/* Specialties */}
            <div style={{ marginBottom: 'var(--space-4)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-secondary)' }}>Board Certifications / Specialties</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setArray('specialties', [...(form.specialties || []), { specialty: '', board: '', certified: false, expiration: '' }])}>+ Add</button>
              </div>
              {(form.specialties || []).map((spec: any, i: number) => (
                <div key={i} style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-1)', alignItems: 'center' }}>
                  <div style={{ flex: 1 }}><label style={labelStyle}>Specialty</label><input style={inputStyle} value={spec.specialty} onChange={e => { const a = [...form.specialties]; a[i] = { ...a[i], specialty: e.target.value }; setArray('specialties', a); }} placeholder="e.g. Psychiatry" /></div>
                  <div style={{ width: 110 }}><label style={labelStyle}>Board</label>
                    <select style={selectStyle} value={spec.board} onChange={e => { const a = [...form.specialties]; a[i] = { ...a[i], board: e.target.value }; setArray('specialties', a); }}>
                      <option value="">Select</option>
                      {BOARDS.map(b => <option key={b} value={b}>{b}</option>)}
                    </select>
                  </div>
                  <div style={{ width: 120 }}><label style={labelStyle}>Expiration</label><input type="date" style={inputStyle} value={spec.expiration} onChange={e => { const a = [...form.specialties]; a[i] = { ...a[i], expiration: e.target.value }; setArray('specialties', a); }} /></div>
                  <div style={{ marginTop: 14 }}><label style={{ fontSize: 10, display: 'flex', alignItems: 'center', gap: 4 }}><input type="checkbox" checked={spec.certified} onChange={e => { const a = [...form.specialties]; a[i] = { ...a[i], certified: e.target.checked }; setArray('specialties', a); }} /> Cert</label></div>
                  {form.specialties.length > 1 && <button className="btn btn-ghost btn-sm" style={{ color: 'var(--brand-error)', marginTop: 14 }} onClick={() => setArray('specialties', form.specialties.filter((_: any, j: number) => j !== i))}>X</button>}
                </div>
              ))}
            </div>

            {/* DEA Certificates */}
            <div style={{ marginBottom: 'var(--space-4)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-secondary)' }}>DEA Certificates</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setArray('dea_certificates', [...(form.dea_certificates || []), { dea_number: '', state: '', schedules: 'II,III,IV,V', expiration: '' }])}>+ Add</button>
              </div>
              {(form.dea_certificates || []).map((dea: any, i: number) => (
                <div key={i} style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-1)', alignItems: 'center' }}>
                  <div style={{ flex: 1 }}><label style={labelStyle}>DEA Number</label><input style={inputStyle} value={dea.dea_number} onChange={e => { const a = [...form.dea_certificates]; a[i] = { ...a[i], dea_number: e.target.value }; setArray('dea_certificates', a); }} /></div>
                  <div style={{ width: 70 }}><label style={labelStyle}>State</label><StateSelect value={dea.state} onChange={v => { const a = [...form.dea_certificates]; a[i] = { ...a[i], state: v }; setArray('dea_certificates', a); }} /></div>
                  <div style={{ width: 130 }}><label style={labelStyle}>Schedules</label>
                    <select style={selectStyle} value={dea.schedules} onChange={e => { const a = [...form.dea_certificates]; a[i] = { ...a[i], schedules: e.target.value }; setArray('dea_certificates', a); }}>
                      <option value="II,III,IV,V">II, III, IV, V</option>
                      <option value="II,IIN,III,IIIN,IV,V">II, IIN, III, IIIN, IV, V</option>
                      <option value="III,IV,V">III, IV, V</option>
                      <option value="IV,V">IV, V</option>
                    </select>
                  </div>
                  <div style={{ width: 120 }}><label style={labelStyle}>Expiration</label><input type="date" style={inputStyle} value={dea.expiration} onChange={e => { const a = [...form.dea_certificates]; a[i] = { ...a[i], expiration: e.target.value }; setArray('dea_certificates', a); }} /></div>
                  {form.dea_certificates.length > 1 && <button className="btn btn-ghost btn-sm" style={{ color: 'var(--brand-error)', marginTop: 14 }} onClick={() => setArray('dea_certificates', form.dea_certificates.filter((_: any, j: number) => j !== i))}>X</button>}
                </div>
              ))}
            </div>

            {/* CNED Certificates */}
            <div style={{ marginBottom: 'var(--space-4)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-secondary)' }}>Controlled Substance / CNED Certificates</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setArray('cned_certificates', [...(form.cned_certificates || []), { state: '', certificate_number: '', expiration: '' }])}>+ Add</button>
              </div>
              {(form.cned_certificates || []).map((cned: any, i: number) => (
                <div key={i} style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-1)', alignItems: 'center' }}>
                  <div style={{ width: 70 }}><label style={labelStyle}>State</label><StateSelect value={cned.state} onChange={v => { const a = [...form.cned_certificates]; a[i] = { ...a[i], state: v }; setArray('cned_certificates', a); }} /></div>
                  <div style={{ flex: 1 }}><label style={labelStyle}>Certificate #</label><input style={inputStyle} value={cned.certificate_number} onChange={e => { const a = [...form.cned_certificates]; a[i] = { ...a[i], certificate_number: e.target.value }; setArray('cned_certificates', a); }} /></div>
                  <div style={{ width: 120 }}><label style={labelStyle}>Expiration</label><input type="date" style={inputStyle} value={cned.expiration} onChange={e => { const a = [...form.cned_certificates]; a[i] = { ...a[i], expiration: e.target.value }; setArray('cned_certificates', a); }} /></div>
                  {form.cned_certificates.length > 1 && <button className="btn btn-ghost btn-sm" style={{ color: 'var(--brand-error)', marginTop: 14 }} onClick={() => setArray('cned_certificates', form.cned_certificates.filter((_: any, j: number) => j !== i))}>X</button>}
                </div>
              ))}
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'flex-end', borderTop: '1px solid var(--border-light)', paddingTop: 'var(--space-4)' }}>
              <button className="btn btn-ghost" onClick={() => { setShowAddModal(false); setEditingProvider(null); }}>Cancel</button>
              {editingProvider ? (
                <button className="btn btn-primary" disabled={updateMutation.isLoading} onClick={() => {
                  updateMutation.mutate({ providerId: editingProvider.provider_id, data: { ...form } });
                }}>
                  {updateMutation.isLoading ? 'Saving...' : 'Save Changes'}
                </button>
              ) : (
                <button className="btn btn-primary" disabled={createMutation.isLoading || !form.first_name || !form.last_name || !form.npi} onClick={() => {
                  createMutation.mutate(form);
                }}>
                  {createMutation.isLoading ? 'Creating...' : 'Add Provider'}
                </button>
              )}
            </div>
          </div>
        </div>
        );
      })()}
    </div>
  );
}

