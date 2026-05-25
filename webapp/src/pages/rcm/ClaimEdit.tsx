/**
 * Claim Edit (drafts only)
 *
 * Allows editing the editable fields of a draft claim. Submitted/paid/etc claims
 * are immutable (backend returns 409 on PUT). For corrections, the user should
 * void + re-create or use the corrected-claim flow (TODO).
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import toast from 'react-hot-toast';
import { useIsMobile } from '@/hooks/useIsMobile';

export default function ClaimEdit() {
  const { claimId } = useParams<{ claimId: string }>();
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: claimResp, isLoading, isError } = useQuery(
    ['claim', claimId],
    () => apiService.get(`/rcm/claims/${claimId}`),
  );

  const { data: payersResp, isLoading: loadingPayers } = useQuery(
    'payers-for-claims',
    () => apiService.get('/rcm/payers'),
  );
  const { data: patientsResp, isLoading: loadingPatients } = useQuery(
    'patients-for-claims',
    () => apiService.get('/rcm/patients'),
  );

  const claim = claimResp?.data;
  const payers: Array<{ id: number; name: string; payer_id?: string }> = payersResp?.data || [];
  const patients: Array<{ id: number; first_name: string; last_name: string; member_id: string }> = patientsResp?.data || [];

  const [form, setForm] = useState({
    patient_id: '',
    payer_id: '',
    service_date_from: '',
    service_date_to: '',
    claim_type: 'professional',
    billing_provider_npi: '',
    rendering_provider_npi: '',
    prior_auth_number: '',
  });

  useEffect(() => {
    if (!claim) return;
    setForm({
      patient_id: claim.patient_id ? String(claim.patient_id) : '',
      payer_id: claim.payer_id ? String(claim.payer_id) : '',
      service_date_from: claim.service_date_from ? String(claim.service_date_from).substring(0, 10) : '',
      service_date_to: claim.service_date_to ? String(claim.service_date_to).substring(0, 10) : '',
      claim_type: claim.claim_type || 'professional',
      billing_provider_npi: claim.billing_provider_npi || '',
      rendering_provider_npi: claim.rendering_provider_npi || '',
      prior_auth_number: claim.prior_auth_number || '',
    });
  }, [claim]);

  const saveMutation = useMutation(
    () => {
      const payload: Record<string, unknown> = {
        patient_id: form.patient_id ? parseInt(form.patient_id) : null,
        payer_id: form.payer_id ? parseInt(form.payer_id) : null,
        service_date_from: form.service_date_from || null,
        service_date_to: form.service_date_to || null,
        claim_type: form.claim_type,
        billing_provider_npi: form.billing_provider_npi || null,
        rendering_provider_npi: form.rendering_provider_npi || null,
        prior_auth_number: form.prior_auth_number || null,
      };
      return apiService.put(`/rcm/claims/${claimId}`, payload);
    },
    {
      onSuccess: () => {
        toast.success('Draft claim updated');
        queryClient.invalidateQueries(['claim', claimId]);
        queryClient.invalidateQueries(['claims']);
        navigate(`/claims/${claimId}`);
      },
      onError: (err: any) => { toast.error(err?.message || 'Failed to update claim'); },
    },
  );

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    border: '1px solid var(--border-light)',
    borderRadius: 'var(--radius-md)',
    fontSize: 'var(--font-size-sm)',
    background: 'var(--surface-primary)',
    color: 'var(--text-primary)',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: 4,
    fontSize: 'var(--font-size-xs)', fontWeight: 600,
    color: 'var(--text-secondary)', textTransform: 'uppercase' as const, letterSpacing: '0.04em',
  };
  const formColumns = isMobile ? '1fr' : '1fr 1fr';

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--space-8)' }}>
        <div style={{ width: 24, height: 24, border: '3px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
      </div>
    );
  }

  if (isError || !claim) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
        <p style={{ color: 'var(--brand-error)', fontWeight: 600 }}>Claim not found</p>
        <button className="btn btn-ghost" onClick={() => navigate('/claims')} style={{ marginTop: 'var(--space-4)' }}>Back to Claims</button>
      </div>
    );
  }

  if (claim.state !== 'draft') {
    return (
      <div style={{ padding: 'var(--space-8)', maxWidth: 600, margin: '0 auto' }}>
        <div className="card" style={{ padding: 'var(--space-6)', borderColor: 'var(--brand-warning)' }}>
          <h2 style={{ fontWeight: 700, marginBottom: 'var(--space-3)' }}>This claim cannot be edited</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-4)' }}>
            Only claims in <strong>draft</strong> state are editable. This claim is currently in state <strong>{claim.state}</strong>.
            For corrections, use the corrected-claim flow (replacement/void).
          </p>
          <button className="btn btn-primary" onClick={() => navigate(`/claims/${claimId}`)}>Back to Claim</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/claims/${claimId}`)} style={{ marginBottom: 'var(--space-3)' }}>
          Back to Claim
        </button>
        <h1 className="page-title">Edit Draft Claim {claim.claim_number}</h1>
        <p className="page-subtitle">Service lines and diagnoses are not edited here — void this draft and recreate if those need to change.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: formColumns, gap: 'var(--space-6)', maxWidth: 900 }}>
        <div className="card" style={{ padding: 'var(--space-5)' }}>
          <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>Claim Information</h2>
          <div style={{ display: 'grid', gridTemplateColumns: formColumns, gap: 'var(--space-3)' }}>
            <div>
              <label style={labelStyle}>Service Date From *</label>
              <input type="date" value={form.service_date_from} onChange={e => setForm({ ...form, service_date_from: e.target.value })} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Service Date To</label>
              <input type="date" value={form.service_date_to} onChange={e => setForm({ ...form, service_date_to: e.target.value })} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Claim Type</label>
              <select value={form.claim_type} onChange={e => setForm({ ...form, claim_type: e.target.value })} style={inputStyle}>
                <option value="professional">Professional (837P)</option>
                <option value="institutional">Institutional (837I)</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Prior Auth #</label>
              <input value={form.prior_auth_number} onChange={e => setForm({ ...form, prior_auth_number: e.target.value })} style={inputStyle} />
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: 'var(--space-5)' }}>
          <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>References</h2>
          <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
            <div>
              <label style={labelStyle}>Patient *</label>
              <select value={form.patient_id} onChange={e => setForm({ ...form, patient_id: e.target.value })} style={inputStyle} disabled={loadingPatients}>
                <option value="">{loadingPatients ? 'Loading...' : 'Select patient...'}</option>
                {patients.map(p => (
                  <option key={p.id} value={String(p.id)}>{p.last_name}, {p.first_name} ({p.member_id})</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Payer *</label>
              <select value={form.payer_id} onChange={e => setForm({ ...form, payer_id: e.target.value })} style={inputStyle} disabled={loadingPayers}>
                <option value="">{loadingPayers ? 'Loading...' : 'Select payer...'}</option>
                {payers.map(p => (
                  <option key={p.id} value={String(p.id)}>{p.name}{p.payer_id ? ` (${p.payer_id})` : ''}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Billing NPI</label>
              <input value={form.billing_provider_npi} onChange={e => setForm({ ...form, billing_provider_npi: e.target.value })} maxLength={10} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Rendering NPI</label>
              <input value={form.rendering_provider_npi} onChange={e => setForm({ ...form, rendering_provider_npi: e.target.value })} maxLength={10} style={inputStyle} />
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-6)', display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', flexDirection: isMobile ? 'column-reverse' : 'row' }}>
        <button className="btn btn-ghost" onClick={() => navigate(`/claims/${claimId}`)}>Cancel</button>
        <button className="btn btn-primary btn-lg" onClick={() => saveMutation.mutate()} disabled={saveMutation.isLoading} style={{ width: isMobile ? '100%' : undefined }}>
          {saveMutation.isLoading ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}
