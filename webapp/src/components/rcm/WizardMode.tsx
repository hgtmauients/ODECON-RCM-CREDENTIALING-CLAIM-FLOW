/**
 * Payer Configuration Wizard
 * Step-by-step guided setup for first-time users
 * Alternative to 11-tab editor
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from 'react-query';
import { payerProfileService } from '@/services/payerProfileService';
import { PremiumIcon } from '@/services/iconReplacementService';
import toast from 'react-hot-toast';

interface WizardModeProps {
  onComplete?: (payerId: number) => void;
  onCancel?: () => void;
}

type Step = 1 | 2 | 3 | 4 | 5;

export const PayerConfigurationWizard: React.FC<WizardModeProps> = ({ onComplete, onCancel }) => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<Step>(1);
  const [formData, setFormData] = useState<any>({
    // Smart defaults
    filing_limit_days: 365,
    appeal_window_days: 180,
    auth_response_days: 14,
    format_837_type: '837P',
    supports_270_271: true,
    supports_276_277: true,
    supports_835_era: true,
    requires_taxonomy: true,
    requires_tin: true
  });

  const saveMutation = useMutation(
    () => payerProfileService.createPayer(formData),
    {
      onSuccess: (response) => {
        toast.success('Payer created successfully!');
        if (onComplete) {
          onComplete(response.id);
        } else {
          navigate(`/admin/payers/${response.id}`);
        }
      },
      onError: () => {
        toast.error('Failed to create payer');
      }
    }
  );

  const steps = [
    { number: 1, title: 'Basic Information', description: 'Payer name and IDs' },
    { number: 2, title: 'Connection Setup', description: 'Clearinghouse details' },
    { number: 3, title: 'Secure Credentials', description: 'API keys and passwords' },
    { number: 4, title: 'Requirements & Rules', description: 'Configure settings' },
    { number: 5, title: 'Review & Publish', description: 'Confirm and go live' }
  ];

  const handleNext = () => {
    if (currentStep < 5) {
      setCurrentStep((currentStep + 1) as Step);
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep((currentStep - 1) as Step);
    }
  };

  const handleFinish = () => {
    saveMutation.mutate();
  };

  return (
    <div style={{
      background: 'var(--surface-glass)',
      backdropFilter: 'var(--glass-blur)',
      border: '1px solid var(--glass-border)',
      borderRadius: 'var(--radius-xl)',
      padding: 'var(--space-6)',
      maxWidth: '800px',
      margin: '0 auto'
    }}>
      {/* Progress Steps */}
      <div style={{ marginBottom: 'var(--space-8)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
          {steps.map((step) => (
            <div key={step.number} style={{ flex: 1, textAlign: 'center' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                background: currentStep >= step.number ? 'var(--gradient-primary)' : 'var(--surface-secondary)',
                color: 'white',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto',
                fontWeight: 700,
                fontSize: 'var(--font-size-lg)'
              }}>
                {currentStep > step.number ? '\u2713' : step.number}
              </div>
              <div style={{
                marginTop: 'var(--space-2)',
                fontSize: 'var(--font-size-xs)',
                fontWeight: 600,
                color: currentStep >= step.number ? 'var(--text-primary)' : 'var(--text-secondary)'
              }}>
                {step.title}
              </div>
            </div>
          ))}
        </div>
        <div style={{
          height: '4px',
          background: 'var(--surface-secondary)',
          borderRadius: 'var(--radius-full)',
          position: 'relative',
          marginTop: 'var(--space-4)'
        }}>
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            height: '100%',
            width: `${((currentStep - 1) / 4) * 100}%`,
            background: 'var(--gradient-primary)',
            borderRadius: 'var(--radius-full)',
            transition: 'width var(--transition-normal)'
          }} />
        </div>
      </div>

      {/* Step Content */}
      <div style={{ minHeight: '400px', marginBottom: 'var(--space-6)' }}>
        {currentStep === 1 && (
          <div>
            <h2 style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
              Basic Information
            </h2>
            {/* Step 1 fields - Name, Display Name, Payer ID, State */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                  Payer Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g., HMSA, UHA, Quest"
                  value={formData.name || ''}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: 'var(--font-size-sm)'
                  }}
                />
              </div>
              {/* Additional Step 1 fields */}
            </div>
          </div>
        )}

        {/* Other steps... */}
      </div>

      {/* Navigation Buttons */}
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <button
          onClick={onCancel || (() => navigate('/admin/payers'))}
          style={{
            padding: 'var(--space-3) var(--space-6)',
            background: 'transparent',
            border: '1px solid var(--border-primary)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--text-secondary)',
            fontWeight: 600,
            cursor: 'pointer'
          }}
        >
          Cancel
        </button>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {currentStep > 1 && (
            <button
              onClick={handleBack}
              style={{
                padding: 'var(--space-3) var(--space-6)',
                background: 'transparent',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Back
            </button>
          )}
          {currentStep < 5 ? (
            <button
              onClick={handleNext}
              style={{
                padding: 'var(--space-3) var(--space-8)',
                background: 'var(--gradient-primary)',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                color: 'white',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Next
            </button>
          ) : (
            <button
              onClick={handleFinish}
              disabled={saveMutation.isLoading}
              style={{
                padding: 'var(--space-3) var(--space-8)',
                background: 'var(--brand-success)',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                color: 'white',
                fontWeight: 600,
                cursor: saveMutation.isLoading ? 'not-allowed' : 'pointer',
                opacity: saveMutation.isLoading ? 0.5 : 1
              }}
            >
              {saveMutation.isLoading ? 'Creating...' : 'Create Payer'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

