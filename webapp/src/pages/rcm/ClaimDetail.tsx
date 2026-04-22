/**
 * Claim Detail Page
 * Show complete claim info with event timeline
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatCurrency, formatDate } from '@/utils/formatters';
import toast from 'react-hot-toast';

const FINALIZED_STATES = new Set([
  'accepted', 'paid', 'partially_paid', 'denied', 'appealed', 'appeal_won', 'appeal_lost',
]);

export default function ClaimDetail() {
  const { claimId } = useParams<{ claimId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [correctOpen, setCorrectOpen] = useState<null | 'replacement' | 'void'>(null);
  const [correctReason, setCorrectReason] = useState('');

  // Fetch claim details
  const { data: claimData, isLoading, error } = useQuery(
    ['claim', claimId],
    () => apiService.get(`/rcm/claims/${claimId}`)
  );

  // Fetch claim events (timeline)
  const { data: eventsData } = useQuery(
    ['claim-events', claimId],
    () => apiService.get(`/rcm/claims/${claimId}/events`),
    { enabled: !!claimData }
  );

  const claim = claimData?.data;
  const events = eventsData?.data || [];

  const correctMutation = useMutation(
    (kind: 'replacement' | 'void') =>
      apiService.post(`/rcm/claims/${claimId}/correct`, { kind, reason: correctReason }),
    {
      onSuccess: (resp: any) => {
        const newId = resp?.data?.id;
        const newNumber = resp?.data?.claim_number;
        const kind = resp?.data?.kind;
        toast.success(`${kind === 'void' ? 'Void' : 'Replacement'} drafted as ${newNumber}`);
        setCorrectOpen(null);
        setCorrectReason('');
        queryClient.invalidateQueries(['claim']);
        queryClient.invalidateQueries(['claims']);
        if (newId) navigate(`/claims/${newId}/edit`);
      },
      onError: (err: any) => { toast.error(err?.message || 'Failed to draft correction'); },
    },
  );

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <PremiumIcon name="spinner" spin size="xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
        <p style={{ color: 'var(--brand-error)', fontWeight: 600 }}>Failed to load claim</p>
        <button className="btn btn-ghost" onClick={() => navigate('/claims')} style={{ marginTop: 'var(--space-4)' }}>Back to Claims</button>
      </div>
    );
  }

  if (!claim) {
    return (
      <div style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
        <p style={{ fontWeight: 600 }}>Claim not found</p>
        <button className="btn btn-ghost" onClick={() => navigate('/claims')} style={{ marginTop: 'var(--space-4)' }}>Back to Claims</button>
      </div>
    );
  }

  const getStateColor = (state: string) => {
    const colors: Record<string, string> = {
      'paid': 'var(--brand-success)',
      'denied': 'var(--brand-error)',
      'submitted': 'var(--brand-warning)',
      'validated': '#009DDD',
      'draft': 'var(--text-secondary)'
    };
    return colors[state] || 'var(--text-secondary)';
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)', padding: 'var(--space-6)' }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
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
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
                <h1 style={{
                  fontSize: 'var(--font-size-3xl)',
                  fontWeight: 700,
                  background: 'var(--gradient-primary)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent'
                }}>
                  Claim {claim.claim_number}
                </h1>
                <span style={{
                  padding: 'var(--space-2) var(--space-3)',
                  background: getStateColor(claim.state),
                  color: 'white',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600
                }}>
                  {claim.state.toUpperCase().replace('_', ' ')}
                </span>
              </div>
              <p style={{ color: 'var(--text-secondary)' }}>
                Service Date: {formatDate(claim.service_date_from)}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }} className="no-print">
              {claim.state === 'draft' && (
                <button
                  onClick={() => navigate(`/claims/${claim.id}/edit`)}
                  style={{
                    padding: 'var(--space-3) var(--space-4)',
                    background: 'var(--brand-primary)',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    color: 'white',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title="Edit this draft claim"
                >
                  Edit Draft
                </button>
              )}
              {FINALIZED_STATES.has(claim.state) && (
                <>
                  <button
                    onClick={() => setCorrectOpen('replacement')}
                    style={{
                      padding: 'var(--space-3) var(--space-4)',
                      background: 'transparent',
                      border: '1px solid var(--brand-primary)',
                      borderRadius: 'var(--radius-md)',
                      color: 'var(--brand-primary)',
                      fontSize: 'var(--font-size-sm)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                    title="Draft a corrected (replacement) claim — payer-bound CLM05=7"
                  >
                    Correct Claim
                  </button>
                  <button
                    onClick={() => setCorrectOpen('void')}
                    style={{
                      padding: 'var(--space-3) var(--space-4)',
                      background: 'transparent',
                      border: '1px solid var(--brand-error)',
                      borderRadius: 'var(--radius-md)',
                      color: 'var(--brand-error)',
                      fontSize: 'var(--font-size-sm)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                    title="Draft a void/cancel of this claim — payer-bound CLM05=8"
                  >
                    Void Claim
                  </button>
                </>
              )}
              <button
                onClick={() => window.print()}
                style={{
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'transparent',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--text-primary)',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
                title="Print a clean copy of this claim"
              >
                Print
              </button>
              <button
                onClick={() => navigate('/claims')}
                style={{
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'transparent',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Back to Claims
              </button>
            </div>
          </div>

          {claim.original_claim_id && (
            <div
              style={{
                marginTop: 'var(--space-3)',
                padding: 'var(--space-3) var(--space-4)',
                borderLeft: '3px solid var(--brand-primary)',
                background: 'rgba(59, 130, 246, 0.06)',
                borderRadius: 'var(--radius-md)',
                fontSize: 'var(--font-size-sm)',
                color: 'var(--text-secondary)',
              }}
            >
              {claim.claim_frequency_code === '8'
                ? 'Void of '
                : claim.claim_frequency_code === '7'
                ? 'Replacement of '
                : 'Linked to original claim '}
              <button
                onClick={() => navigate(`/claims/${claim.original_claim_id}`)}
                className="btn btn-ghost btn-sm"
                style={{ padding: '0 4px', fontWeight: 600, color: 'var(--brand-primary)' }}
              >
                claim #{claim.original_claim_id} →
              </button>
              <span style={{ marginLeft: 'var(--space-2)', fontFamily: 'monospace', fontSize: 'var(--font-size-xs)' }}>
                CLM05={claim.claim_frequency_code}
              </span>
            </div>
          )}
        </div>

        {correctOpen && (
          <div
            onClick={() => setCorrectOpen(null)}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 80, zIndex: 100 }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{ background: 'var(--surface-primary)', padding: 'var(--space-6)', borderRadius: 'var(--radius-xl)', width: 520, maxWidth: '92vw' }}
            >
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
                {correctOpen === 'void' ? 'Void this claim' : 'Correct this claim'}
              </h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)', marginBottom: 'var(--space-3)' }}>
                {correctOpen === 'void'
                  ? 'A void/cancel (CLM05=8) tells the payer to reverse the prior adjudication. The new claim is created in draft so you can review before submitting.'
                  : 'A replacement (CLM05=7) supersedes the prior adjudication with corrected data. Lines, diagnoses, charges, and references are copied; edit anything that needs to change before submitting.'}
              </p>
              <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 'var(--space-3)' }}>
                Original payer claim ID: <code>{claim.payer_claim_id || '— missing —'}</code>
              </p>
              <label style={{ display: 'block', fontSize: 'var(--font-size-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Reason (audit log + notes)
              </label>
              <textarea
                value={correctReason}
                onChange={(e) => setCorrectReason(e.target.value)}
                rows={4}
                placeholder={correctOpen === 'void' ? 'e.g. Wrong patient billed.' : 'e.g. Corrected place-of-service from 11 to 02.'}
                style={{ width: '100%', padding: 'var(--space-3)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)', fontFamily: 'inherit', fontSize: 'var(--font-size-sm)', resize: 'vertical' }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', marginTop: 'var(--space-4)' }}>
                <button className="btn btn-ghost" onClick={() => setCorrectOpen(null)}>Cancel</button>
                <button
                  className="btn btn-primary"
                  disabled={correctMutation.isLoading}
                  onClick={() => correctMutation.mutate(correctOpen)}
                  style={correctOpen === 'void' ? { background: 'var(--brand-error)' } : undefined}
                >
                  {correctMutation.isLoading
                    ? 'Drafting…'
                    : correctOpen === 'void'
                    ? 'Draft void'
                    : 'Draft replacement'}
                </button>
              </div>
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-6)' }}>
          {/* Event Timeline */}
          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-6)'
          }}>
            <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
              Claim Timeline
            </h2>
            
            {events.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)' }}>No events yet</p>
            ) : (
              <div style={{ position: 'relative', paddingLeft: 'var(--space-6)' }}>
                {/* Timeline line */}
                <div style={{
                  position: 'absolute',
                  left: '8px',
                  top: '12px',
                  bottom: '12px',
                  width: '2px',
                  background: 'var(--border-primary)'
                }} />
                
                {events.map((event: Record<string, any>, idx: number) => (
                  <div key={idx} style={{ marginBottom: 'var(--space-4)', position: 'relative' }}>
                    {/* Timeline dot */}
                    <div style={{
                      position: 'absolute',
                      left: '-22px',
                      top: '4px',
                      width: '12px',
                      height: '12px',
                      borderRadius: '50%',
                      background: 'var(--brand-primary)',
                      border: '2px solid var(--surface-primary)'
                    }} />
                    
                    <div>
                      <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {event.event_type.replace(/_/g, ' ').toUpperCase()}
                      </div>
                      {event.message && (
                        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                          {event.message}
                        </div>
                      )}
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginTop: 'var(--space-1)' }}>
                        {formatDate(event.timestamp)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Claim Details */}
          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-6)'
          }}>
            <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
              Details
            </h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Total Charges</div>
                <div style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {formatCurrency(claim.total_charges)}
                </div>
              </div>
              
              {claim.total_allowed && (
                <div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Allowed Amount</div>
                  <div style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {formatCurrency(claim.total_allowed)}
                  </div>
                </div>
              )}
              
              {claim.total_paid && (
                <div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Paid Amount</div>
                  <div style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, color: 'var(--text-success)' }}>
                    {formatCurrency(claim.total_paid)}
                  </div>
                </div>
              )}
              
              {claim.current_queue && (
                <div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Current Queue</div>
                  <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {claim.current_queue.replace(/_/g, ' ').toUpperCase()}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

