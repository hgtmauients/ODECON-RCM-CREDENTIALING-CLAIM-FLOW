/**
 * Denial Management Dashboard
 * Work denials, generate appeals, track outcomes
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { useNavigate } from 'react-router-dom';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatCurrency, formatDate } from '@/utils/formatters';
import toast from 'react-hot-toast';

interface DenialCase {
  id: number;
  claim_id: number;
  claim_number: string;
  carc_code: string;
  rarc_code?: string;
  denial_description: string;
  denial_category: string;
  denied_amount: number;
  status: string;
  priority: string;
  appeal_due_date?: string;
  days_until_due?: number;
  assigned_to?: string;
}

export default function DenialDashboard() {
  const navigate = useNavigate();
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('');

  // Fetch denial cases
  const { data, isLoading, error } = useQuery(
    ['denial-cases', categoryFilter, priorityFilter],
    async () => {
      const params: Record<string, string> = {};
      if (categoryFilter) params.category = categoryFilter;
      if (priorityFilter) params.priority = priorityFilter;
      
      // TODO: Create this endpoint
      return apiService.get('/rcm/denials/cases', { params });
    }
  );

  const denials: DenialCase[] = data?.data || [];

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'critical': return 'var(--brand-error)';
      case 'high': return '#F98A33';
      case 'medium': return '#009DDD';
      case 'low': return 'var(--text-secondary)';
      default: return 'var(--text-secondary)';
    }
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'coding_error': return '#8b5cf6';
      case 'medical_policy': return '#ec4899';
      case 'missing_info': return '#009DDD';
      case 'timely_filing': return '#ef4444';
      case 'authorization': return '#F98A33';
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h1 style={{
                fontSize: 'var(--font-size-3xl)',
                fontWeight: 700,
                marginBottom: 'var(--space-2)',
                background: 'var(--gradient-primary)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}>
                Denial Management
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-base)' }}>
                Review denials, generate appeals, and track outcomes
              </p>
            </div>
            <button
              className="btn btn-ghost btn-lg"
              onClick={() => {
                const params: Record<string, string | number> = { limit: 10000 };
                if (categoryFilter) params.category = categoryFilter;
                if (priorityFilter) params.priority = priorityFilter;
                apiService
                  .downloadFile('/rcm/denials/cases/export.csv', 'denials.csv', params)
                  .catch((err: any) => toast.error(err?.message || 'Export failed'));
              }}
              title="Download denial cases as CSV"
            >
              Export CSV
            </button>
          </div>
        </div>

        {/* Summary Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-4)'
          }}>
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
              Total Denials
            </div>
            <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 700, color: 'var(--text-primary)' }}>
              {denials.length}
            </div>
          </div>

          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-4)'
          }}>
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
              Critical/High Priority
            </div>
            <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 700, color: '#ef4444' }}>
              {denials.filter(d => d.priority === 'critical' || d.priority === 'high').length}
            </div>
          </div>

          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-4)'
          }}>
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
              Total Denied Amount
            </div>
            <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 700, color: 'var(--text-primary)' }}>
              {formatCurrency(denials.reduce((sum, d) => sum + d.denied_amount, 0))}
            </div>
          </div>
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
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            style={{
              padding: 'var(--space-3) var(--space-4)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--surface-primary)',
              color: 'var(--text-primary)',
              fontSize: 'var(--font-size-sm)',
              minWidth: '200px'
            }}
          >
            <option value="">All Categories</option>
            <option value="coding_error">Coding Errors</option>
            <option value="medical_policy">Medical Policy</option>
            <option value="missing_info">Missing Information</option>
            <option value="timely_filing">Timely Filing</option>
            <option value="authorization">Authorization</option>
          </select>

          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            style={{
              padding: 'var(--space-3) var(--space-4)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--surface-primary)',
              color: 'var(--text-primary)',
              fontSize: 'var(--font-size-sm)',
              minWidth: '150px'
            }}
          >
            <option value="">All Priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        {/* Denials Table */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden'
        }}>
          {isLoading ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
              <PremiumIcon name="spinner" size="xl" />
            </div>
          ) : error ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--brand-error)' }}>
              <p style={{ fontWeight: 600 }}>Failed to load denial cases</p>
              <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginTop: 'var(--space-2)' }}>Check your connection and try again.</p>
            </div>
          ) : denials.length === 0 ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <PremiumIcon name="check" size="xl" />
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)', marginTop: 'var(--space-4)' }}>
                No Denials
              </h3>
              <p>
                Denials are automatically created when 835 files contain denial codes.
                Upload an 835 file or wait for automatic processing.
              </p>
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
                    Priority
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Claim
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    CARC/RARC
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Category
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Amount
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Due Date
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {denials.map((denial) => (
                  <tr 
                    key={denial.id}
                    style={{
                      borderBottom: '1px solid var(--border-primary)',
                      cursor: 'pointer'
                    }}
                    onClick={() => navigate(`/denials/${denial.id}`)}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'var(--surface-hover)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: 'var(--space-3)' }}>
                      <span style={{
                        padding: 'var(--space-1) var(--space-2)',
                        background: getPriorityColor(denial.priority),
                        color: 'white',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600
                      }}>
                        {denial.priority.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: 'var(--space-3)', fontFamily: 'monospace', fontWeight: 600, color: 'var(--brand-primary)' }}>
                      {denial.claim_number}
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)' }}>
                      <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>{denial.carc_code}</div>
                      {denial.rarc_code && (
                        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                          {denial.rarc_code}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 'var(--space-3)' }}>
                      <span style={{
                        padding: 'var(--space-1) var(--space-2)',
                        background: getCategoryColor(denial.denial_category),
                        color: 'white',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600
                      }}>
                        {denial.denial_category.replace('_', ' ').toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right', color: 'var(--brand-error)', fontWeight: 700 }}>
                      {formatCurrency(denial.denied_amount)}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center' }}>
                      {denial.appeal_due_date ? (
                        <div>
                          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)' }}>
                            {formatDate(denial.appeal_due_date)}
                          </div>
                          {denial.days_until_due !== undefined && (
                            <div style={{
                              fontSize: 'var(--font-size-xs)',
                              color: denial.days_until_due < 14 ? '#ef4444' : 
                                     denial.days_until_due < 30 ? '#F98A33' : 'var(--text-secondary)',
                              marginTop: 'var(--space-1)',
                              fontWeight: 600
                            }}>
                              {denial.days_until_due} days
                            </div>
                          )}
                        </div>
                      ) : '—'}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => navigate(`/denials/${denial.id}`)}
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
                        Work Denial
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Info Box */}
        <div style={{
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid #ef4444',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          display: 'flex',
          gap: 'var(--space-3)',
          alignItems: 'flex-start'
        }}>
          <PremiumIcon name="warning" style={{ color: '#ef4444', marginTop: 'var(--space-1)' }} />
          <div>
            <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Automated Denial Processing
            </h3>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              Denials are automatically created when 835 remittance files contain denial codes (CARC/RARC).
              Each denial is categorized, assigned a playbook, and routed to the appropriate queue.
              Appeal due dates are calculated based on payer appeal windows.
              <strong> Critical/high priority denials require immediate attention!</strong>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

