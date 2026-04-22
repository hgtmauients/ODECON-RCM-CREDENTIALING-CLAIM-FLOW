/**
 * Payer Configuration Wizard route wrapper.
 * Renders the existing 5-step wizard component.
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { PayerConfigurationWizard } from '@/components/rcm/WizardMode';

export default function PayerWizard() {
  const navigate = useNavigate();
  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <button className="btn btn-ghost btn-sm" onClick={() => navigate('/admin/payers')} style={{ marginBottom: 'var(--space-3)' }}>
        ← Back to Payers
      </button>
      <PayerConfigurationWizard
        onComplete={(payerId) => navigate(`/admin/payers/${payerId}`)}
        onCancel={() => navigate('/admin/payers')}
      />
    </div>
  );
}
