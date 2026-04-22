/**
 * Identity Tab Component
 * Basic payer information (name, IDs, state)
 */

import React from 'react';
import type { PayerProfile } from '@/services/payerProfileService';

interface IdentityTabProps {
  formData: Partial<PayerProfile>;
  onInputChange: (field: string, value: unknown) => void;
}

const US_STATES = [
  { code: 'AL', name: 'Alabama' }, { code: 'AK', name: 'Alaska' }, { code: 'AZ', name: 'Arizona' },
  { code: 'AR', name: 'Arkansas' }, { code: 'CA', name: 'California' }, { code: 'CO', name: 'Colorado' },
  { code: 'CT', name: 'Connecticut' }, { code: 'DE', name: 'Delaware' }, { code: 'DC', name: 'District of Columbia' },
  { code: 'FL', name: 'Florida' }, { code: 'GA', name: 'Georgia' }, { code: 'HI', name: 'Hawaii' },
  { code: 'ID', name: 'Idaho' }, { code: 'IL', name: 'Illinois' }, { code: 'IN', name: 'Indiana' },
  { code: 'IA', name: 'Iowa' }, { code: 'KS', name: 'Kansas' }, { code: 'KY', name: 'Kentucky' },
  { code: 'LA', name: 'Louisiana' }, { code: 'ME', name: 'Maine' }, { code: 'MD', name: 'Maryland' },
  { code: 'MA', name: 'Massachusetts' }, { code: 'MI', name: 'Michigan' }, { code: 'MN', name: 'Minnesota' },
  { code: 'MS', name: 'Mississippi' }, { code: 'MO', name: 'Missouri' }, { code: 'MT', name: 'Montana' },
  { code: 'NE', name: 'Nebraska' }, { code: 'NV', name: 'Nevada' }, { code: 'NH', name: 'New Hampshire' },
  { code: 'NJ', name: 'New Jersey' }, { code: 'NM', name: 'New Mexico' }, { code: 'NY', name: 'New York' },
  { code: 'NC', name: 'North Carolina' }, { code: 'ND', name: 'North Dakota' }, { code: 'OH', name: 'Ohio' },
  { code: 'OK', name: 'Oklahoma' }, { code: 'OR', name: 'Oregon' }, { code: 'PA', name: 'Pennsylvania' },
  { code: 'RI', name: 'Rhode Island' }, { code: 'SC', name: 'South Carolina' }, { code: 'SD', name: 'South Dakota' },
  { code: 'TN', name: 'Tennessee' }, { code: 'TX', name: 'Texas' }, { code: 'UT', name: 'Utah' },
  { code: 'VT', name: 'Vermont' }, { code: 'VA', name: 'Virginia' }, { code: 'WA', name: 'Washington' },
  { code: 'WV', name: 'West Virginia' }, { code: 'WI', name: 'Wisconsin' }, { code: 'WY', name: 'Wyoming' },
  { code: 'AS', name: 'American Samoa' }, { code: 'GU', name: 'Guam' }, { code: 'MP', name: 'Northern Mariana Islands' },
  { code: 'PR', name: 'Puerto Rico' }, { code: 'VI', name: 'US Virgin Islands' },
];

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 'var(--space-3)',
  border: '1px solid var(--border-primary)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--surface-primary)',
  color: 'var(--text-primary)',
  fontSize: 'var(--font-size-sm)',
};

export const IdentityTab: React.FC<IdentityTabProps> = ({ formData, onInputChange }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
      <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
        Payer Identity
      </h2>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          Payer Name * <span style={{ color: 'var(--brand-error)' }}>Required</span>
        </label>
        <input
          type="text"
          placeholder="e.g., HMSA, UHA, Quest/Medicaid"
          value={formData.name || ''}
          onChange={(e) => onInputChange('name', e.target.value)}
          style={inputStyle}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          Display Name
        </label>
        <input
          type="text"
          placeholder="e.g., Hawaii Medical Service Association"
          value={formData.display_name || ''}
          onChange={(e) => onInputChange('display_name', e.target.value)}
          style={inputStyle}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          Payer ID (for 837P submissions)
        </label>
        <input
          type="text"
          placeholder="Enter payer ID received from clearinghouse"
          value={formData.payer_id || ''}
          onChange={(e) => onInputChange('payer_id', e.target.value)}
          style={{ ...inputStyle, fontFamily: 'monospace' }}
        />
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
          This ID will be used in 837P claim files. Check clearinghouse documentation.
        </div>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          NAIC Code
        </label>
        <input
          type="text"
          placeholder="5-digit NAIC code"
          value={formData.naic_code || ''}
          onChange={(e) => onInputChange('naic_code', e.target.value)}
          style={inputStyle}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          State Code (if state-specific)
        </label>
        <select
          value={formData.state_code || ''}
          onChange={(e) => onInputChange('state_code', e.target.value || undefined)}
          style={inputStyle}
        >
          <option value="">National (all states)</option>
          {US_STATES.map(s => (
            <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          Payer Status
        </label>
        <select
          value={(formData as any).payer_status || 'active'}
          onChange={(e) => onInputChange('payer_status', e.target.value)}
          style={inputStyle}
        >
          <option value="active">Active - Live claim submissions</option>
          <option value="testing">Testing - Validation only, no live submissions</option>
          <option value="disabled">Disabled - Payer temporarily disabled</option>
        </select>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          EDI Version
        </label>
        <select
          value={(formData as any).edi_version || '005010X222A1'}
          onChange={(e) => onInputChange('edi_version', e.target.value)}
          style={inputStyle}
        >
          <option value="005010X222A1">005010X222A1 - 837P Professional (Current)</option>
          <option value="005010X223A3">005010X223A3 - 837I Institutional</option>
          <option value="005010X224A3">005010X224A3 - 837D Dental</option>
          <option value="005010X279A1">005010X279A1 - 270/271 Eligibility</option>
          <option value="005010X212">005010X212 - 276/277 Claim Status</option>
          <option value="005010X221A1">005010X221A1 - 835 Remittance</option>
        </select>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
          X12 implementation guide version used for claim generation and parsing.
        </div>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          Supported Modifiers
        </label>
        <input
          type="text"
          placeholder="95, GT, GQ, 25, 59 (comma-separated)"
          value={Array.isArray((formData as any).supported_modifiers) ? (formData as any).supported_modifiers.join(', ') : (formData as any).supported_modifiers || ''}
          onChange={(e) => onInputChange('supported_modifiers', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={inputStyle}
        />
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
          Modifiers this payer accepts. Used by the rules engine for claim validation. Common: 25 (separate E/M), 59 (distinct service), 95/GT/GQ (telehealth).
        </div>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
          Last ERA (835) Received
        </label>
        <input
          type="date"
          value={(formData as any).last_era_received ? (formData as any).last_era_received.split('T')[0] : ''}
          onChange={(e) => onInputChange('last_era_received', e.target.value || null)}
          style={inputStyle}
        />
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
          Date of most recent 835 remittance file received from this payer. Used to monitor connectivity.
        </div>
      </div>
    </div>
  );
};
