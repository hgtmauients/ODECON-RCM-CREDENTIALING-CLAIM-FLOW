/**
 * Fee Schedule Viewer Component
 * Browse uploaded payer fee schedules
 * Reusable component for payer editor and state billing
 */

import React, { useState } from 'react';
import { useQuery } from 'react-query';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatCurrency } from '@/utils/formatters';

interface FeeScheduleViewerProps {
  payerId: number;
  stateCode?: string;
  showUploadButton?: boolean;
  onUploadClick?: () => void;
}

export const FeeScheduleViewer: React.FC<FeeScheduleViewerProps> = ({
  payerId,
  stateCode,
  showUploadButton = false,
  onUploadClick
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  // Fetch fee schedules
  const { data, isLoading } = useQuery(
    ['fee-schedules', payerId, stateCode],
    async () => {
      const params: Record<string, string> = { payer_id: String(payerId) };
      if (stateCode) params.state_code = stateCode;
      
      return apiService.get('/rcm/payers/fee-schedules', { params });
    }
  );

  const feeSchedules = data?.data || [];
  const filteredSchedules = feeSchedules.filter((fee: Record<string, unknown>) =>
    (fee.cpt_code as string || '').includes(searchQuery) ||
    ((fee.description as string) || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
            Fee Schedule
          </h3>
          <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
            {filteredSchedules.length} CPT codes configured
          </p>
        </div>
        {showUploadButton && onUploadClick && (
          <button
            onClick={onUploadClick}
            style={{
              padding: 'var(--space-3) var(--space-4)',
              background: 'var(--gradient-primary)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              color: 'white',
              fontSize: 'var(--font-size-sm)',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Upload CSV
          </button>
        )}
      </div>

      {/* Search */}
      <div style={{ position: 'relative' }}>
        <input
          type="text"
          placeholder="Search CPT codes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%',
            padding: 'var(--space-3)',
            border: '1px solid var(--border-primary)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-primary)',
            color: 'var(--text-primary)',
            fontSize: 'var(--font-size-sm)'
          }}
        />
      </div>

      {/* Table */}
      {isLoading ? (
        <div style={{ padding: 'var(--space-6)', textAlign: 'center' }}>
          <PremiumIcon name="spinner" size="lg" />
        </div>
      ) : filteredSchedules.length === 0 ? (
        <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <PremiumIcon name="revenue" size="xl" />
          <p style={{ marginTop: 'var(--space-2)' }}>
            No fee schedule uploaded yet. Upload a CSV to configure rates.
          </p>
        </div>
      ) : (
        <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid var(--border-primary)', borderRadius: 'var(--radius-md)' }}>
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
                  CPT Code
                </th>
                <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                  Description
                </th>
                <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                  Allowable
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredSchedules.map((fee: Record<string, any>) => (
                <tr key={String(fee.id)} style={{ borderBottom: '1px solid var(--border-primary)' }}>
                  <td style={{ padding: 'var(--space-3)', fontFamily: 'monospace', fontWeight: 700, color: 'var(--brand-primary)' }}>
                    {String(fee.cpt_code ?? '')}
                  </td>
                  <td style={{ padding: 'var(--space-3)', color: 'var(--text-primary)' }}>
                    {String(fee.description ?? '')}
                  </td>
                  <td style={{ padding: 'var(--space-3)', textAlign: 'right', color: 'var(--text-success)', fontWeight: 600 }}>
                    {formatCurrency(fee.allowable_amount as number)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

