/**
 * Payer Profiles Management
 * List, search, and manage payer profiles
 * Ops can add/edit payers entirely in this UI
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { useNavigate } from 'react-router-dom';
import { payerProfileService } from '@/services/payerProfileService';
import { PremiumIcon } from '@/services/iconReplacementService';
import { logger } from '@/utils/logger';
import toast from 'react-hot-toast';

export default function PayerProfiles() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [stateFilter, setStateFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'draft'>('active');

  // Fetch payers
  const { data, isLoading, error } = useQuery(
    ['payer-profiles', searchQuery, stateFilter, statusFilter],
    () => {
      const params: {
        search?: string;
        state_code?: string;
        is_active?: boolean;
        is_draft?: boolean;
      } = {
        search: searchQuery || undefined,
        state_code: stateFilter !== 'all' ? stateFilter : undefined,
      };
      if (statusFilter === 'active') {
        params.is_active = true;
        params.is_draft = false;
      } else if (statusFilter === 'draft') {
        params.is_draft = true;
      }
      // 'all' leaves both flags unset to return everything
      return payerProfileService.listPayers(params);
    },
    {
      keepPreviousData: true
    }
  );

  const payers = data?.data || [];
  const totalPayers = data?.total || 0;

  // Publish mutation
  const publishMutation = useMutation(
    (payerId: number) => payerProfileService.publishPayer(payerId),
    {
      onSuccess: () => {
        toast.success('Payer profile published successfully');
        queryClient.invalidateQueries(['payer-profiles']);
      },
      onError: (error) => {
        logger.error('Error publishing payer', { error });
        toast.error('Failed to publish payer profile');
      }
    }
  );

  // Delete mutation
  const deleteMutation = useMutation(
    (payerId: number) => payerProfileService.deletePayer(payerId),
    {
      onSuccess: () => {
        toast.success('Payer profile deactivated');
        queryClient.invalidateQueries(['payer-profiles']);
      },
      onError: (error) => {
        logger.error('Error deleting payer', { error });
        toast.error('Failed to deactivate payer profile');
      }
    }
  );

  const handlePublish = (payerId: number, payerName: string) => {
    if (confirm(`Publish "${payerName}"? This will make the payer configuration live.`)) {
      publishMutation.mutate(payerId);
    }
  };

  const handleDelete = (payerId: number, payerName: string) => {
    if (confirm(`Deactivate "${payerName}"? This payer will no longer be available for claims.`)) {
      deleteMutation.mutate(payerId);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)', padding: 'var(--space-6)' }}>
      <div style={{ maxWidth: '1600px', margin: '0 auto' }}>
        {/* Page Header */}
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
                Payer Profiles
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-base)' }}>
                Configure insurance payers with connection details, rules, and credentials
              </p>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
              <button
                onClick={() => navigate('/admin/payers/wizard')}
                className="btn btn-primary"
                style={{ padding: 'var(--space-3) var(--space-5)', display: 'flex', alignItems: 'center', gap: 6 }}
                title="Step-by-step guided setup"
              >
                + Wizard
              </button>
              <button
                onClick={() => navigate('/admin/payers/new')}
                className="btn btn-ghost"
                style={{ padding: 'var(--space-3) var(--space-5)' }}
                title="Open the full 11-tab editor"
              >
                Advanced editor
              </button>
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
          marginBottom: 'var(--space-6)'
        }}>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            {/* Search */}
            <div style={{ flex: 1, minWidth: '300px' }}>
              <div style={{ position: 'relative' }}>
                <PremiumIcon 
                  name="search" 
                  style={{
                    position: 'absolute',
                    left: 'var(--space-3)',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: 'var(--text-tertiary)'
                  }}
                />
                <input
                  type="text"
                  placeholder="Search payers by name, ID, or clearinghouse..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: 'var(--space-3) var(--space-3) var(--space-3) var(--space-10)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--surface-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-size-sm)'
                  }}
                />
              </div>
            </div>

            {/* State Filter */}
            <select
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
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
              <option value="all">All States</option>
              <option value="HI">Hawaii</option>
              <option value="AK">Alaska</option>
              <option value="AZ">Arizona</option>
              <option value="TX">Texas</option>
              <option value="FL">Florida</option>
              <option value="NY">New York</option>
            </select>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | 'active' | 'draft')}
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
              <option value="active">Active Only</option>
              <option value="draft">Drafts Only</option>
              <option value="all">All Statuses</option>
            </select>

            {/* Clear Filters */}
            {(searchQuery || stateFilter !== 'all' || statusFilter !== 'active') && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setStateFilter('all');
                  setStatusFilter('active');
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

          {/* Results Count */}
          <div style={{ 
            marginTop: 'var(--space-3)', 
            color: 'var(--text-secondary)',
            fontSize: 'var(--font-size-sm)'
          }}>
            {isLoading ? 'Loading...' : `${totalPayers} payer(s) found`}
          </div>
        </div>

        {/* Payer Table */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden'
        }}>
          {isLoading ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <PremiumIcon name="spinner" spin style={{ fontSize: '2rem', marginBottom: 'var(--space-2)' }} />
              <div>Loading payers...</div>
            </div>
          ) : error ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--brand-error)' }}>
              Error loading payers. Please try again.
            </div>
          ) : payers.length === 0 ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <PremiumIcon name="settings" style={{ fontSize: '4rem', marginBottom: 'var(--space-4)', opacity: 0.3 }} />
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                No Payers Yet
              </h3>
              <p style={{ marginBottom: 'var(--space-4)' }}>
                Create your first payer profile to start submitting claims
              </p>
              <button
                onClick={() => navigate('/admin/payers/new')}
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
                Create First Payer
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
                    Payer Name
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    State
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Clearinghouse
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Status
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Rules
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Fee Schedules
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {payers.map((payer) => (
                  <tr 
                    key={payer.id}
                    style={{
                      borderBottom: '1px solid var(--border-primary)',
                      transition: 'background var(--transition-fast)',
                      cursor: 'pointer'
                    }}
                    onClick={() => navigate(`/admin/payers/${payer.id}`)}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'var(--surface-hover)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: 'var(--space-3)' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {payer.display_name || payer.name}
                      </div>
                      {payer.payer_id && (
                        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)', fontFamily: 'monospace' }}>
                          ID: {payer.payer_id}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-secondary)' }}>
                      {payer.state_code || 'National'}
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-secondary)' }}>
                      {payer.clearinghouse || '—'}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center' }}>
                      {payer.is_draft ? (
                        <span style={{
                          padding: 'var(--space-1) var(--space-2)',
                          background: 'var(--brand-warning)',
                          color: 'white',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: 'var(--font-size-xs)',
                          fontWeight: 600
                        }}>
                          DRAFT
                        </span>
                      ) : payer.is_active ? (
                        <span style={{
                          padding: 'var(--space-1) var(--space-2)',
                          background: 'var(--brand-success)',
                          color: 'white',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: 'var(--font-size-xs)',
                          fontWeight: 600
                        }}>
                          ACTIVE
                        </span>
                      ) : (
                        <span style={{
                          padding: 'var(--space-1) var(--space-2)',
                          background: 'var(--text-secondary)',
                          color: 'white',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: 'var(--font-size-xs)',
                          fontWeight: 600
                        }}>
                          INACTIVE
                        </span>
                      )}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center', color: 'var(--text-secondary)' }}>
                      {payer.rules_count || 0}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center', color: 'var(--text-secondary)' }}>
                      {payer.fee_schedules_count || 0}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end' }} onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/admin/payers/${payer.id}`)}
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
                          title="Edit payer"
                        >
                          Edit
                        </button>
                        
                        {payer.is_draft && (
                          <button
                            onClick={() => handlePublish(payer.id, payer.name)}
                            style={{
                              padding: 'var(--space-2) var(--space-3)',
                              background: 'var(--brand-success)',
                              border: 'none',
                              borderRadius: 'var(--radius-sm)',
                              color: 'white',
                              fontSize: 'var(--font-size-xs)',
                              fontWeight: 600,
                              cursor: 'pointer'
                            }}
                            title="Publish payer"
                          >
                            Publish
                          </button>
                        )}
                        
                        {payer.is_active && (
                          <button
                            onClick={() => handleDelete(payer.id, payer.name)}
                            style={{
                              padding: 'var(--space-2) var(--space-3)',
                              background: 'transparent',
                              border: '1px solid var(--brand-error)',
                              borderRadius: 'var(--radius-sm)',
                              color: 'var(--brand-error)',
                              fontSize: 'var(--font-size-xs)',
                              fontWeight: 600,
                              cursor: 'pointer'
                            }}
                            title="Deactivate payer"
                          >
                            X
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

        {/* Info Box */}
        <div style={{
          background: 'rgba(59, 130, 246, 0.1)',
          border: '1px solid #009DDD',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          display: 'flex',
          gap: 'var(--space-3)',
          alignItems: 'flex-start'
        }}>
          <PremiumIcon name="info" style={{ fontSize: 'var(--font-size-xl)', color: '#009DDD', marginTop: 'var(--space-1)' }} />
          <div>
            <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Configure Payers in the UI
            </h3>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              Payer profiles are fully configurable in this interface. Add new payers, set up clearinghouse connections, 
              define decision table rules, upload fee schedules, and manage credentials - all without touching code. 
              Changes are versioned and can be rolled back if needed.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

