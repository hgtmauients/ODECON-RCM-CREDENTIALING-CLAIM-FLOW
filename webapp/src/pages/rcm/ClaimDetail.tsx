/**
 * Claim Detail Page
 * Show complete claim info with event timeline
 */

import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from 'react-query';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatCurrency, formatDate } from '@/utils/formatters';

export default function ClaimDetail() {
  const { claimId } = useParams<{ claimId: string }>();
  const navigate = useNavigate();

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

