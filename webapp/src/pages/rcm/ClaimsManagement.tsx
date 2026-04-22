/**
 * Claims Management Dashboard
 * List, create, validate, and submit claims
 * Core operational interface for billing staff
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { useNavigate } from 'react-router-dom';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatCurrency, formatDate } from '@/utils/formatters';
import toast from 'react-hot-toast';

interface Claim {
  id: number;
  claim_number: string;
  payer_claim_id?: string;
  payer_id: number;
  state: string;
  current_queue?: string;
  service_date_from: string;
  total_charges: number;
  total_paid?: number;
  created_date: string;
  submitted_date?: string;
}

export default function ClaimsManagement() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [stateFilter, setStateFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedClaims, setSelectedClaims] = useState<number[]>([]);

  // Fetch claims
  const { data, isLoading, error } = useQuery(
    ['claims', stateFilter],
    async () => {
      const params: Record<string, string> = {};
      if (stateFilter) params.state = stateFilter;
      return apiService.get('/rcm/claims', { params });
    }
  );

  const allClaims: Claim[] = data?.data || [];

  // Client-side search filter
  const claims = searchQuery
    ? allClaims.filter(c =>
        c.claim_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (c.service_date_from || '').includes(searchQuery) ||
        (c.payer_claim_id || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
    : allClaims;

  // Validate claims mutation
  const validateMutation = useMutation(
    (claimId: number) => apiService.post(`/rcm/claims/${claimId}/validate`),
    {
      onSuccess: (response, claimId) => {
        // Backend returns { success, data: { passed, errors, rules_matched, ... } }
        const result = response?.data;
        if (result?.passed) {
          toast.success(`Claim validated! ${result.rules_matched || 0} rules applied`);
        } else {
          const errs = (result?.errors || []).join(', ') || 'Unknown error';
          toast.error(`Validation failed: ${errs}`);
        }
        queryClient.invalidateQueries(['claims']);
        queryClient.invalidateQueries(['claim', claimId]);
        queryClient.invalidateQueries(['claim-events', claimId]);
      },
      onError: () => {
        toast.error('Failed to validate claim');
      }
    }
  );

  // Batch submit mutation
  const submitBatchMutation = useMutation(
    (data: { claim_ids: number[]; payer_id: number }) =>
      apiService.post('/rcm/claims/batch/submit', data),
    {
      onSuccess: (response, vars) => {
        // Backend returns { success, message, data: { filename, claim_count, ... } }
        const result = response?.data || {};
        const claimCount = result.claim_count ?? vars.claim_ids.length;
        const filename = result.filename ?? '';
        toast.success(`Batch submitted: ${claimCount} claims${filename ? ` in ${filename}` : ''}`);
        setSelectedClaims([]);
        queryClient.invalidateQueries(['claims']);
        // Invalidate detail caches for each submitted claim so open detail views refresh
        vars.claim_ids.forEach((id) => {
          queryClient.invalidateQueries(['claim', id]);
          queryClient.invalidateQueries(['claim-events', id]);
        });
      },
      onError: () => {
        toast.error('Failed to submit batch');
      }
    }
  );

  const deleteMutation = useMutation(
    (ids: number[]) => apiService.post('/rcm/claims/batch/delete', { claim_ids: ids }),
    {
      onSuccess: (response: any, ids) => {
        const data = response?.data || {};
        toast.success(`${data.deleted || 0} claim(s) deleted`);
        if (data.errors?.length) {
          data.errors.forEach((e: string) => toast.error(e));
        }
        setSelectedClaims([]);
        queryClient.invalidateQueries(['claims']);
        ids.forEach((id) => queryClient.invalidateQueries(['claim', id]));
      },
      onError: () => { toast.error('Failed to delete claims'); },
    }
  );

  const voidMutation = useMutation(
    (claimId: number) => apiService.post(`/rcm/claims/${claimId}/void`),
    {
      onSuccess: (_resp, claimId) => {
        toast.success('Claim voided');
        queryClient.invalidateQueries(['claims']);
        queryClient.invalidateQueries(['claim', claimId]);
        queryClient.invalidateQueries(['claim-events', claimId]);
      },
      onError: () => { toast.error('Failed to void claim'); },
    }
  );

  const csvImportMutation = useMutation(
    (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiService.upload('/rcm/claims/import/csv', fd);
    },
    {
      onSuccess: (response: any) => {
        const data = response?.data || response;
        const created = data?.message || `Imported ${(data?.created_claims || []).length} claims`;
        toast.success(created);
        if (data?.errors?.length) {
          toast.error(`${data.errors.length} row(s) had errors — check console for details`);
          console.error('[csv-import] errors:', data.errors);
        }
        queryClient.invalidateQueries(['claims']);
      },
      onError: (err: any) => { toast.error(err?.message || 'CSV import failed'); },
    },
  );

  const csvFileInputRef = React.useRef<HTMLInputElement>(null);
  const handleCsvSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      toast.error('Please select a .csv file');
      return;
    }
    csvImportMutation.mutate(file);
  };

  const getStateColor = (state: string) => {
    switch (state) {
      case 'paid': return 'var(--brand-success)';
      case 'denied': return 'var(--brand-error)';
      case 'submitted': return 'var(--brand-warning)';
      case 'validated': return '#009DDD';
      case 'ready_to_submit': return '#25D366';
      case 'draft': return 'var(--text-secondary)';
      default: return 'var(--text-secondary)';
    }
  };

  const handleSelectClaim = (claimId: number) => {
    if (selectedClaims.includes(claimId)) {
      setSelectedClaims(selectedClaims.filter(id => id !== claimId));
    } else {
      setSelectedClaims([...selectedClaims, claimId]);
    }
  };

  const handleSubmitBatch = () => {
    if (selectedClaims.length === 0) {
      toast.error('Please select claims to submit');
      return;
    }

    // Get payer_id from first selected claim
    const firstClaim = claims.find(c => c.id === selectedClaims[0]);
    if (!firstClaim) return;

    // Verify all selected claims are for same payer
    const allSamePayer = claims
      .filter(c => selectedClaims.includes(c.id))
      .every(c => c.payer_id === firstClaim.payer_id);

    if (!allSamePayer) {
      toast.error('All selected claims must be for the same payer');
      return;
    }

    if (confirm(`Submit ${selectedClaims.length} claims to clearinghouse?`)) {
      submitBatchMutation.mutate({
        claim_ids: selectedClaims,
        payer_id: firstClaim.payer_id
      });
    }
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)', padding: 'var(--space-6)' }}>
      <div style={{ maxWidth: '1600px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-xl)',
          padding: 'var(--space-6)',
          marginBottom: 'var(--space-6)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h1 style={{
                fontSize: 'var(--font-size-3xl)',
                fontWeight: 700,
                marginBottom: 'var(--space-2)',
                background: 'var(--gradient-primary)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent'
              }}>
                Claims Management
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-base)' }}>
                Create, validate, and submit insurance claims
              </p>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              {selectedClaims.length > 0 && (
                <>
                  <button
                    onClick={handleSubmitBatch}
                    disabled={submitBatchMutation.isLoading}
                    className="btn btn-success"
                  >
                    {submitBatchMutation.isLoading ? 'Submitting...' : `Submit ${selectedClaims.length}`}
                  </button>
                  <button
                    className="btn btn-ghost"
                    style={{ color: 'var(--brand-error)' }}
                    onClick={() => {
                      if (confirm(`Delete ${selectedClaims.length} selected claim(s)? Only draft/void claims will be deleted.`)) {
                        deleteMutation.mutate(selectedClaims);
                      }
                    }}
                  >
                    Delete {selectedClaims.length}
                  </button>
                  <button className="btn btn-ghost" onClick={() => setSelectedClaims([])}>
                    Clear Selection
                  </button>
                </>
              )}
              <button
                onClick={() => csvFileInputRef.current?.click()}
                className="btn btn-ghost btn-lg"
                disabled={csvImportMutation.isLoading}
                title="Import claims from a CSV file"
              >
                {csvImportMutation.isLoading ? 'Importing...' : 'Import CSV'}
              </button>
              <input
                type="file"
                accept=".csv"
                ref={csvFileInputRef}
                onChange={handleCsvSelected}
                style={{ display: 'none' }}
              />
              <button
                onClick={() => navigate('/claims/new')}
                className="btn btn-primary btn-lg"
              >
                + New Claim
              </button>
            </div>
          </div>
        </div>

        {/* Search + Filters */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          marginBottom: 'var(--space-6)',
          display: 'flex',
          gap: 'var(--space-3)',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}>
          <input
            type="text"
            placeholder="Search by claim number, date, or payer ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input"
            style={{ flex: 1, minWidth: 200 }}
          />

          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="input"
            style={{ width: 180 }}
          >
            <option value="">Claim Status: All</option>
            <option value="draft">Draft</option>
            <option value="validated">Validated</option>
            <option value="ready_to_submit">Ready to Submit</option>
            <option value="submitted">Submitted</option>
            <option value="accepted">Accepted</option>
            <option value="paid">Paid</option>
            <option value="partially_paid">Partially Paid</option>
            <option value="denied">Denied</option>
            <option value="appealed">Appealed</option>
            <option value="void">Voided</option>
          </select>

          {(stateFilter || searchQuery) && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => { setStateFilter(''); setSearchQuery(''); }}
            >
              Clear
            </button>
          )}

          <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
            {claims.length} claim{claims.length !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Claims Table */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden'
        }}>
          {isLoading ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
              <PremiumIcon name="spinner" spin size="xl" />
            </div>
          ) : error ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--brand-error)' }}>
              <p style={{ fontWeight: 600 }}>Failed to load claims</p>
              <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginTop: 'var(--space-2)' }}>Check your connection and try again.</p>
            </div>
          ) : claims.length === 0 ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <PremiumIcon name="billing" size="xl" />
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)', marginTop: 'var(--space-4)' }}>
                No Claims Yet
              </h3>
              <p style={{ marginBottom: 'var(--space-4)' }}>
                Create your first claim to start the billing process
              </p>
              <button
                onClick={() => navigate('/claims/new')}
                style={{
                  padding: 'var(--space-3) var(--space-6)',
                  background: 'var(--gradient-primary)',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  color: 'white',
                  fontSize: 'var(--font-size-base)',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Create First Claim
              </button>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{
                position: 'sticky',
                top: 0,
                background: 'var(--surface-secondary)',
                borderBottom: '2px solid var(--border-primary)',
                zIndex: 10
              }}>
                <tr>
                  <th style={{ padding: 'var(--space-3)' }}>
                    <input
                      type="checkbox"
                      checked={selectedClaims.length === claims.length && claims.length > 0}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedClaims(claims.map(c => c.id));
                        } else {
                          setSelectedClaims([]);
                        }
                      }}
                    />
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Claim Number
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Service Date
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Status
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Charges
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Paid
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {claims.map((claim) => (
                  <tr 
                    key={claim.id}
                    style={{
                      borderBottom: '1px solid var(--border-primary)',
                      background: selectedClaims.includes(claim.id) ? 'rgba(59, 130, 246, 0.05)' : 'transparent',
                      cursor: 'pointer'
                    }}
                    onClick={() => navigate(`/claims/${claim.id}`)}
                    onMouseEnter={(e) => e.currentTarget.style.background = selectedClaims.includes(claim.id) ? 'rgba(59, 130, 246, 0.1)' : 'var(--surface-hover)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = selectedClaims.includes(claim.id) ? 'rgba(59, 130, 246, 0.05)' : 'transparent'}
                  >
                    <td style={{ padding: 'var(--space-3)' }} onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedClaims.includes(claim.id)}
                        onChange={() => handleSelectClaim(claim.id)}
                      />
                    </td>
                    <td style={{ padding: 'var(--space-3)', fontFamily: 'monospace', fontWeight: 700, color: 'var(--brand-primary)' }}>
                      {claim.claim_number}
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-secondary)' }}>
                      {formatDate(claim.service_date_from)}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center' }}>
                      <span style={{
                        padding: 'var(--space-1) var(--space-2)',
                        background: getStateColor(claim.state),
                        color: 'white',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600
                      }}>
                        {claim.state.toUpperCase().replace('_', ' ')}
                      </span>
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right', color: 'var(--text-primary)', fontWeight: 600 }}>
                      {formatCurrency(claim.total_charges)}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right', color: claim.total_paid ? 'var(--text-success)' : 'var(--text-secondary)', fontWeight: 600 }}>
                      {claim.total_paid ? formatCurrency(claim.total_paid) : '—'}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
                        {claim.state === 'draft' && (
                          <button
                            onClick={() => validateMutation.mutate(claim.id)}
                            disabled={validateMutation.isLoading}
                            style={{
                              padding: 'var(--space-2) var(--space-3)',
                              background: '#009DDD',
                              border: 'none',
                              borderRadius: 'var(--radius-sm)',
                              color: 'white',
                              fontSize: 'var(--font-size-xs)',
                              fontWeight: 600,
                              cursor: validateMutation.isLoading ? 'not-allowed' : 'pointer'
                            }}
                          >
                            Validate
                          </button>
                        )}
                        <button
                          onClick={() => navigate(`/claims/${claim.id}`)}
                          style={{
                            padding: 'var(--space-2) var(--space-3)',
                            background: 'var(--gradient-primary)',
                            border: 'none',
                            borderRadius: 'var(--radius-sm)',
                            color: 'white',
                            fontSize: 'var(--font-size-xs)',
                            fontWeight: 600,
                            cursor: 'pointer'
                          }}
                        >
                          Details
                        </button>
                        {claim.state !== 'void' && claim.state !== 'paid' && (
                          <button
                            onClick={() => { if (confirm('Void this claim?')) voidMutation.mutate(claim.id); }}
                            className="btn btn-ghost btn-sm"
                            style={{ color: 'var(--brand-error)', fontSize: 'var(--font-size-xs)', padding: 'var(--space-1) var(--space-2)' }}
                          >
                            Void
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Help Text */}
        <div style={{
          background: 'rgba(59, 130, 246, 0.1)',
          border: '1px solid #009DDD',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          display: 'flex',
          gap: 'var(--space-3)',
          alignItems: 'flex-start'
        }}>
          <PremiumIcon name="info" style={{ color: '#009DDD', marginTop: 'var(--space-1)' }} />
          <div>
            <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Claims Workflow
            </h3>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.8 }}>
              <strong>1. Create</strong> - Enter claim manually, import CSV, or create from visit<br />
              <strong>2. Validate</strong> - System checks payer rules, adds modifiers, flags missing info<br />
              <strong>3. Generate 837P</strong> - Batch-select validated claims, generate ANSI X12 file<br />
              <strong>4. Submit</strong> - Transmit 837P to clearinghouse via SFTP/API (or download for manual upload)<br />
              <strong>5. 277CA Acknowledgment</strong> - Clearinghouse confirms receipt: accepted or rejected at claim level<br />
              <strong>6. 835 Remittance</strong> - Payer returns payment/denial info per claim line:<br />
              &nbsp;&nbsp;&nbsp;&nbsp;- <strong>Paid</strong> - Payment posted, claim moves to paid/partially paid<br />
              &nbsp;&nbsp;&nbsp;&nbsp;- <strong>Denied</strong> - Denial case auto-created with CARC/RARC codes and appeal playbook<br />
              &nbsp;&nbsp;&nbsp;&nbsp;- <strong>Adjusted</strong> - Contractual adjustments applied (CO-45, PR-1, etc.)<br />
              <strong>7. Appeal</strong> - Work denied claims through playbook, generate appeal letter, resubmit<br />
              <strong>8. Void</strong> - Cancel a claim (keeps audit trail)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

