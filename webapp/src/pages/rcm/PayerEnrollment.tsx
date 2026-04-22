/**
 * Payer Enrollment Dashboard
 * Track provider enrollment with specific payers
 * Separate from provider verification queue
 */

import React, { useState } from 'react';
import { useQuery } from 'react-query';
import { useNavigate } from 'react-router-dom';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatDate } from '@/utils/formatters';

interface PayerEnrollmentCase {
  id: number;
  provider_id: string;
  provider_name: string;
  payer_id: number;
  payer_name: string;
  status: string;
  submitted_date?: string;
  effective_date?: string;
  expiration_date?: string;
  completion_percentage: number;
  assigned_to?: string;
  created_at: string;
}

export default function PayerEnrollment() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Fetch enrollment cases
  const { data, isLoading, isError, error } = useQuery(
    ['payer-enrollment-cases', statusFilter],
    async () => {
      const params: Record<string, string | undefined> = {};
      if (statusFilter) params.status = statusFilter;
      return apiService.get('/rcm/payer-enrollment/cases', { params });
    }
  );

  const cases: PayerEnrollmentCase[] = data?.data || [];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'var(--brand-success)';
      case 'submitted': return 'var(--brand-warning)';
      case 'in_review': return '#009DDD';
      case 'rejected': return 'var(--brand-error)';
      case 'draft': return 'var(--text-secondary)';
      default: return 'var(--text-secondary)';
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
          <h1 style={{
            fontSize: 'var(--font-size-3xl)',
            fontWeight: 700,
            marginBottom: 'var(--space-2)',
            background: 'var(--gradient-primary)',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}>
            Payer Enrollment Dashboard
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-base)' }}>
            Track provider enrollment with insurance payers. Auto-created after provider verification approval.
          </p>
        </div>

        {/* Filters */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          marginBottom: 'var(--space-6)',
          display: 'flex',
          gap: 'var(--space-3)',
          flexWrap: 'wrap'
        }}>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: 'var(--space-3) var(--space-4)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--surface-primary)',
              color: 'var(--text-primary)',
              fontSize: 'var(--font-size-sm)',
              minWidth: '180px'
            }}
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="ready_to_submit">Ready to Submit</option>
            <option value="submitted">Submitted</option>
            <option value="in_review">In Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>

          {statusFilter && (
            <button
              onClick={() => {
                setStatusFilter('');
              }}
              style={{
                padding: 'var(--space-3) var(--space-4)',
                background: 'transparent',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-secondary)',
                fontSize: 'var(--font-size-sm)',
                cursor: 'pointer'
              }}
            >
              Clear Filters
            </button>
          )}
        </div>

        {/* Cases Table */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden'
        }}>
          {isLoading ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <div style={{ width: 24, height: 24, margin: '0 auto', border: '3px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
              <div style={{ marginTop: 'var(--space-3)' }}>Loading enrollment cases...</div>
            </div>
          ) : isError ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--brand-error)' }}>
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                Failed to load enrollment cases
              </h3>
              <p style={{ color: 'var(--text-secondary)' }}>
                {(error as any)?.message || 'Please refresh the page or try again later.'}
              </p>
            </div>
          ) : cases.length === 0 ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <div style={{ fontSize: '4rem', marginBottom: 'var(--space-4)', opacity: 0.3 }}>
                <PremiumIcon name="check" size={48} />
              </div>
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                No Payer Enrollment Cases Yet
              </h3>
              <p style={{ marginBottom: 'var(--space-4)' }}>
                Cases are auto-created when providers are approved in the Credentialing Queue.
                Approve a provider to see payer enrollment cases appear here.
              </p>
              <button
                onClick={() => navigate('/credentialing')}
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
                Go to Credentialing Queue
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
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Provider
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Payer
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Status
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Progress
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Effective Date
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {cases.map((enrollmentCase) => (
                  <tr 
                    key={enrollmentCase.id}
                    style={{
                      borderBottom: '1px solid var(--border-primary)',
                      transition: 'background var(--transition-fast)',
                      cursor: 'pointer'
                    }}
                    onClick={() => navigate(`/payer-enrollment/${enrollmentCase.id}`)}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'var(--surface-hover)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: 'var(--space-3)' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {enrollmentCase.provider_name}
                      </div>
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                        ID: {enrollmentCase.provider_id}
                      </div>
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-secondary)' }}>
                      {enrollmentCase.payer_name}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center' }}>
                      <span style={{
                        padding: 'var(--space-1) var(--space-2)',
                        background: getStatusColor(enrollmentCase.status),
                        color: 'white',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600
                      }}>
                        {enrollmentCase.status.toUpperCase().replace('_', ' ')}
                      </span>
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-2)' }}>
                        <div style={{
                          width: '100px',
                          height: '8px',
                          background: 'var(--surface-secondary)',
                          borderRadius: 'var(--radius-full)',
                          overflow: 'hidden'
                        }}>
                          <div style={{
                            width: `${enrollmentCase.completion_percentage}%`,
                            height: '100%',
                            background: enrollmentCase.completion_percentage === 100 
                              ? 'var(--brand-success)' 
                              : 'var(--gradient-primary)',
                            transition: 'width var(--transition-normal)'
                          }} />
                        </div>
                        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', fontWeight: 600 }}>
                          {enrollmentCase.completion_percentage}%
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
                      {enrollmentCase.effective_date ? formatDate(enrollmentCase.effective_date) : '--'}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right' }}>
                      <span style={{
                        fontSize: 'var(--font-size-xs)',
                        color: 'var(--text-secondary)',
                      }}>
                        {enrollmentCase.assigned_to || 'Unassigned'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Info Box */}
        <div style={{
          marginTop: 'var(--space-6)',
          background: 'rgba(59, 130, 246, 0.1)',
          border: '1px solid #009DDD',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          display: 'flex',
          gap: 'var(--space-3)',
          alignItems: 'flex-start'
        }}>
          <PremiumIcon name="info" size={20} />
          <div>
            <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Two-Stage Credentialing Process
            </h3>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              <strong>Stage 1: Provider Verification</strong> (Credentialing Queue)<br />
              Verify NPI, licenses, background checks, OIG/SAM exclusions. Once approved, provider is ready for enrollment.<br /><br />
              <strong>Stage 2: Payer Enrollment</strong> (This Dashboard)<br />
              Enroll verified provider with each insurance payer. Track payer-specific checklists, submission status, and effective dates.
              Cases are auto-created when provider is approved in Stage 1.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

