/**
 * Connectivity Tab Component
 * Clearinghouse connection details with test button
 */

import React from 'react';
import { payerProfileService } from '@/services/payerProfileService';
import toast from 'react-hot-toast';
import type { PayerProfile } from '@/services/payerProfileService';

interface ConnectivityTabProps {
  formData: Partial<PayerProfile>;
  onInputChange: (field: string, value: unknown) => void;
  payerId?: string;
  isNew: boolean;
}

export const ConnectivityTab: React.FC<ConnectivityTabProps> = ({
  formData,
  onInputChange,
  payerId,
  isNew
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
      <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
        Clearinghouse & Connectivity
      </h2>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          Clearinghouse
        </label>
        <select
          value={formData.clearinghouse || ''}
          onChange={(e) => onInputChange('clearinghouse', e.target.value)}
          style={{
            width: '100%',
            padding: 'var(--space-3)',
            border: '1px solid var(--border-primary)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-primary)',
            color: 'var(--text-primary)',
            fontSize: 'var(--font-size-sm)'
          }}
        >
          <option value="">Select clearinghouse...</option>
          <option value="Waystar">Waystar</option>
          <option value="Availity">Availity</option>
          <option value="Office Ally">Office Ally</option>
          <option value="Change Healthcare">Change Healthcare</option>
          <option value="Trizetto">Trizetto</option>
          <option value="Direct">Direct (No Clearinghouse)</option>
        </select>
      </div>

      {/* Trading Partner ID, Submitter ID, Receiver ID, etc. - similar pattern */}
      
      {/* Test Connection Button */}
      {!isNew && (
        <div style={{
          marginTop: 'var(--space-4)',
          padding: 'var(--space-4)',
          background: 'rgba(16, 185, 129, 0.1)',
          border: '1px solid #25D366',
          borderRadius: 'var(--radius-lg)'
        }}>
          <h4 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-3)', color: 'var(--text-primary)' }}>
            Connection Testing
          </h4>
          <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Test SFTP/API connection before going live. Make sure to save credentials first.
          </p>
          <button
            onClick={async () => {
              try {
                toast.loading('Testing connection...');
                const result = await payerProfileService.testConnection(Number(payerId));
                toast.dismiss();
                toast(result.message, { duration: 5000 });
              } catch (error) {
                toast.dismiss();
                toast.error('Connection test failed');
              }
            }}
            style={{
              padding: 'var(--space-3) var(--space-6)',
              background: 'var(--brand-success)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              color: 'white',
              fontSize: 'var(--font-size-base)',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Test Connection
          </button>
        </div>
      )}
    </div>
  );
};

