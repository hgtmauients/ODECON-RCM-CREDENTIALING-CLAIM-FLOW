/**
 * Payer Profile Editor
 * Comprehensive tabbed editor for payer configuration
 * Ops can configure everything here - credentials entered directly on page
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { payerProfileService, type PayerProfile, type TradingPartnerConnection } from '@/services/payerProfileService';
import { PremiumIcon } from '@/services/iconReplacementService';
import { logger } from '@/utils/logger';
import toast from 'react-hot-toast';

type TabId = 'identity' | 'connectivity' | 'credentials' | 'requirements' | 'telehealth' | 'auth' | 'era_eft' | 'slas' | 'contract' | 'paper' | 'rules';

export default function PayerProfileEditor() {
  const { payerId } = useParams<{ payerId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isNew = payerId === 'new';
  
  const [activeTab, setActiveTab] = useState<TabId>('identity');
  const [formData, setFormData] = useState<Partial<PayerProfile>>({
    is_active: true,
    is_draft: true,
    version: 1,
    // Defaults
    filing_limit_days: 365,
    auth_response_days: 14,
    appeal_window_days: 180,
    audit_response_days: 14,
    format_837_type: '837P',
    supports_270_271: true,
    supports_276_277: true,
    supports_835_era: true,
    requires_taxonomy: true,
    requires_tin: true,
    supports_corrected_claims: true,
    accepts_secondary_claims: true,
    paper_claim_supported: true
  });

  // For credentials (entered directly on page)
  const [credentials, setCredentials] = useState({
    sftp_password: '',
    api_key: '',
    api_secret: '',
    oauth2_client_secret: '',
    portal_password: ''
  });

  // Fetch existing payer if editing
  const { data: existingPayer, isLoading } = useQuery(
    ['payer-profile', payerId],
    () => payerProfileService.getPayerProfile(Number(payerId)),
    {
      enabled: !isNew && !!payerId,
      onSuccess: (data) => {
        setFormData(data);
      }
    }
  );

  // Save mutation
  const saveMutation = useMutation(
    async () => {
      if (isNew) {
        return payerProfileService.createPayer(formData);
      } else {
        return payerProfileService.updatePayer(Number(payerId), formData);
      }
    },
    {
      onSuccess: (response) => {
        toast.success(isNew ? 'Payer profile created' : 'Payer profile updated');
        queryClient.invalidateQueries(['payer-profiles']);
        
        if (isNew && response.id) {
          navigate(`/admin/payers/${response.id}`);
        }
      },
      onError: (error) => {
        logger.error('Error saving payer profile', { error });
        toast.error('Failed to save payer profile');
      }
    }
  );

  // Publish mutation
  const publishMutation = useMutation(
    () => payerProfileService.publishPayer(Number(payerId)),
    {
      onSuccess: () => {
        toast.success('Payer profile published successfully');
        queryClient.invalidateQueries(['payer-profile', payerId]);
        queryClient.invalidateQueries(['payer-profiles']);
      },
      onError: (error) => {
        logger.error('Error publishing payer', { error });
        toast.error('Failed to publish payer profile');
      }
    }
  );

  const handleInputChange = (field: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleCredentialChange = (field: string, value: string) => {
    setCredentials(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = () => {
    if (!formData.name) {
      toast.error('Payer name is required');
      return;
    }
    
    // Merge credentials into form data if provided
    const dataToSave: Record<string, any> = { ...formData };
    Object.entries(credentials).forEach(([key, value]) => {
      if (value) {
        dataToSave[key] = value;
      }
    });
    
    saveMutation.mutate();
  };

  const handlePublish = () => {
    if (confirm('Publish this payer profile? It will become active for claim submissions.')) {
      publishMutation.mutate();
    }
  };

  const tabs = [
    { id: 'identity' as TabId, label: 'Identity', icon: 'user', description: 'Basic info' },
    { id: 'connectivity' as TabId, label: 'Connectivity', icon: 'settings', description: 'Clearinghouse' },
    { id: 'credentials' as TabId, label: 'Credentials', icon: 'key', description: 'Secure credentials' },
    { id: 'requirements' as TabId, label: 'Requirements', icon: 'check', description: 'NPI, TIN, CLIA' },
    { id: 'telehealth' as TabId, label: 'Telehealth', icon: 'video', description: 'Telehealth rules' },
    { id: 'auth' as TabId, label: 'Auth & Eligibility', icon: 'security', description: '270/271/278' },
    { id: 'era_eft' as TabId, label: 'ERA/EFT', icon: 'billing', description: '835 Enrollment' },
    { id: 'slas' as TabId, label: 'SLAs', icon: 'clock', description: 'Deadlines' },
    { id: 'contract' as TabId, label: 'Contract', icon: 'document', description: 'Contract info' },
    { id: 'paper' as TabId, label: 'Paper Fallback', icon: 'mail', description: 'Mail/Fax' },
    { id: 'rules' as TabId, label: 'Rules', icon: 'code', description: 'Decision tables' }
  ];

  if (isLoading) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
        <PremiumIcon name="spinner" spin style={{ fontSize: '2rem' }} />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)', padding: 'var(--space-6)' }}>
      <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
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
                WebkitTextFillColor: 'transparent'
              }}>
                {isNew ? 'New Payer Profile' : `Edit ${formData.name || 'Payer'}`}
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-base)' }}>
                {formData.is_draft ? 'Draft - Save and publish to activate' : `Version ${formData.version || 1}`}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button
                onClick={() => navigate('/admin/payers')}
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
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saveMutation.isLoading}
                style={{
                  padding: 'var(--space-3) var(--space-6)',
                  background: 'var(--gradient-primary)',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  color: 'white',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600,
                  cursor: saveMutation.isLoading ? 'not-allowed' : 'pointer',
                  opacity: saveMutation.isLoading ? 0.5 : 1
                }}
              >
                {saveMutation.isLoading ? 'Saving...' : 'Save Draft'}
              </button>
              {!isNew && formData.is_draft && (
                <button
                  onClick={handlePublish}
                  disabled={publishMutation.isLoading}
                  style={{
                    padding: 'var(--space-3) var(--space-6)',
                    background: 'var(--brand-success)',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    color: 'white',
                    fontSize: 'var(--font-size-sm)',
                    fontWeight: 600,
                    cursor: publishMutation.isLoading ? 'not-allowed' : 'pointer',
                    opacity: publishMutation.isLoading ? 0.5 : 1
                  }}
                >
                  {publishMutation.isLoading ? 'Publishing...' : 'Publish'}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{
          display: 'flex',
          gap: 'var(--space-2)',
          marginBottom: 'var(--space-6)',
          overflowX: 'auto',
          paddingBottom: 'var(--space-2)'
        }}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                flex: '0 0 auto',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: 'var(--space-1)',
                padding: 'var(--space-3) var(--space-4)',
                background: activeTab === tab.id ? 'var(--gradient-primary)' : 'var(--surface-glass)',
                backdropFilter: 'var(--glass-blur)',
                border: activeTab === tab.id ? 'none' : '1px solid var(--glass-border)',
                borderRadius: 'var(--radius-lg)',
                color: activeTab === tab.id ? 'white' : 'var(--text-primary)',
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
                minWidth: '130px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span style={{ fontWeight: 600, fontSize: 'var(--font-size-xs)' }}>{tab.label}</span>
              </div>
              <span style={{ 
                fontSize: 'var(--font-size-xs)', 
                opacity: 0.8,
                color: activeTab === tab.id ? 'white' : 'var(--text-secondary)'
              }}>
                {tab.description}
              </span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6)'
        }}>
          {/* IDENTITY TAB */}
          {activeTab === 'identity' && (
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
                  onChange={(e) => handleInputChange('name', e.target.value)}
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

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Display Name
                </label>
                <input
                  type="text"
                  placeholder="e.g., Hawaii Medical Service Association"
                  value={formData.display_name || ''}
                  onChange={(e) => handleInputChange('display_name', e.target.value)}
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

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Payer ID (for 837 submissions)
                </label>
                <input
                  type="text"
                  placeholder="Enter payer ID received from clearinghouse"
                  value={formData.payer_id || ''}
                  onChange={(e) => handleInputChange('payer_id', e.target.value)}
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--surface-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-size-sm)',
                    fontFamily: 'monospace'
                  }}
                />
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                  This ID will be used in 837 claim files. Check clearinghouse documentation.
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
                  onChange={(e) => handleInputChange('naic_code', e.target.value)}
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

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  State Code (if state-specific)
                </label>
                <select
                  value={formData.state_code || ''}
                  onChange={(e) => handleInputChange('state_code', e.target.value || undefined)}
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
                  <option value="">National (all states)</option>
                  <option value="HI">Hawaii</option>
                  <option value="AK">Alaska</option>
                  <option value="AZ">Arizona</option>
                  <option value="TX">Texas</option>
                  <option value="FL">Florida</option>
                  <option value="NY">New York</option>
                </select>
              </div>
            </div>
          )}

          {/* CONNECTIVITY TAB */}
          {activeTab === 'connectivity' && (
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
                  onChange={(e) => handleInputChange('clearinghouse', e.target.value)}
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

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Trading Partner ID
                </label>
                <input
                  type="text"
                  placeholder="Enter TP ID from clearinghouse"
                  value={formData.trading_partner_id || ''}
                  onChange={(e) => handleInputChange('trading_partner_id', e.target.value)}
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--surface-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-size-sm)',
                    fontFamily: 'monospace'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Submitter ID (Your ID)
                </label>
                <input
                  type="text"
                  placeholder="Your submitter ID from clearinghouse"
                  value={formData.submitter_id || ''}
                  onChange={(e) => handleInputChange('submitter_id', e.target.value)}
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--surface-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-size-sm)',
                    fontFamily: 'monospace'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Receiver ID (Payer's ID)
                </label>
                <input
                  type="text"
                  placeholder="Payer's receiver ID from clearinghouse"
                  value={formData.receiver_id || ''}
                  onChange={(e) => handleInputChange('receiver_id', e.target.value)}
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--surface-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-size-sm)',
                    fontFamily: 'monospace'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Connection Method
                </label>
                <select
                  value={formData.connection_method || ''}
                  onChange={(e) => handleInputChange('connection_method', e.target.value)}
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
                  <option value="">Select method...</option>
                  <option value="clearinghouse">Clearinghouse (Recommended)</option>
                  <option value="sftp">Direct SFTP</option>
                  <option value="api">Direct API</option>
                  <option value="portal">Web Portal Only</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Endpoint URL (if API/SFTP)
                </label>
                <input
                  type="url"
                  placeholder="https://api.clearinghouse.com or sftp://host.com"
                  value={formData.endpoint_url || ''}
                  onChange={(e) => handleInputChange('endpoint_url', e.target.value)}
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--surface-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-size-sm)',
                    fontFamily: 'monospace'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  837 Format Type
                </label>
                <select
                  value={formData.format_837_type || '837P'}
                  onChange={(e) => handleInputChange('format_837_type', e.target.value)}
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
                  <option value="837P">837P - Professional</option>
                  <option value="837I">837I - Institutional</option>
                </select>
              </div>

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
          )}

          {/* CREDENTIALS TAB - Enter directly on page */}
          {activeTab === 'credentials' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', maxWidth: '700px' }}>
              <div>
                <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Secure Credentials
                </h2>
                <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  Enter credentials directly here. All data is encrypted using AES-256-GCM before storage. 
                  Credentials are never shown after saving.
                </p>
              </div>

              {/* SFTP Credentials */}
              {(formData.connection_method === 'sftp' || formData.connection_method === 'clearinghouse' || !formData.connection_method) && (
              <div style={{
                padding: 'var(--space-4)',
                background: 'rgba(59, 130, 246, 0.05)',
                border: '1px solid rgba(59, 130, 246, 0.2)',
                borderRadius: 'var(--radius-lg)',
                opacity: formData.connection_method && formData.connection_method !== 'sftp' && formData.connection_method !== 'clearinghouse' ? 0.5 : 1,
              }}>
                <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-1)', color: 'var(--text-primary)' }}>
                  SFTP Credentials
                </h3>
                {(!formData.connection_method || formData.connection_method === 'sftp' || formData.connection_method === 'clearinghouse') ? (
                  <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
                    For clearinghouse SFTP file exchange. Set connection method on the Connectivity tab.
                  </p>
                ) : (
                  <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 'var(--space-3)' }}>
                    Not applicable - current connection method is "{formData.connection_method}". Change on Connectivity tab if needed.
                  </p>
                )}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        SFTP Username
                      </label>
                      <input
                        type="text"
                        placeholder="Enter SFTP username"
                        value={formData.sftp_username || ''}
                        onChange={(e) => handleInputChange('sftp_username', e.target.value)}
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

                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        SFTP Password
                        <span style={{ marginLeft: 'var(--space-2)', color: '#009DDD', fontSize: 'var(--font-size-xs)' }}>
                          Will be encrypted
                        </span>
                      </label>
                      <input
                        type="password"
                        placeholder="Enter SFTP password (will be encrypted on save)"
                        value={credentials.sftp_password}
                        onChange={(e) => handleCredentialChange('sftp_password', e.target.value)}
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
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                        Encrypted with AES-256-GCM. Never shown after save.
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* API Credentials */}
              {(formData.connection_method === 'api' || !formData.connection_method) && (
              <div style={{
                padding: 'var(--space-4)',
                background: 'rgba(16, 185, 129, 0.05)',
                border: '1px solid rgba(16, 185, 129, 0.2)',
                borderRadius: 'var(--radius-lg)',
                opacity: formData.connection_method && formData.connection_method !== 'api' ? 0.5 : 1,
              }}>
                <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-3)', color: 'var(--text-primary)' }}>
                  API Credentials
                </h3>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        API Key
                        <span style={{ marginLeft: 'var(--space-2)', color: '#25D366', fontSize: 'var(--font-size-xs)' }}>
                          Will be encrypted
                        </span>
                      </label>
                      <input
                        type="password"
                        placeholder="Paste API key here (will be encrypted on save)"
                        value={credentials.api_key}
                        onChange={(e) => handleCredentialChange('api_key', e.target.value)}
                        style={{
                          width: '100%',
                          padding: 'var(--space-3)',
                          border: '1px solid var(--border-primary)',
                          borderRadius: 'var(--radius-md)',
                          background: 'var(--surface-primary)',
                          color: 'var(--text-primary)',
                          fontSize: 'var(--font-size-sm)',
                          fontFamily: 'monospace'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        API Secret
                        <span style={{ marginLeft: 'var(--space-2)', color: '#25D366', fontSize: 'var(--font-size-xs)' }}>
                          Will be encrypted
                        </span>
                      </label>
                      <input
                        type="password"
                        placeholder="Paste API secret here (will be encrypted on save)"
                        value={credentials.api_secret}
                        onChange={(e) => handleCredentialChange('api_secret', e.target.value)}
                        style={{
                          width: '100%',
                          padding: 'var(--space-3)',
                          border: '1px solid var(--border-primary)',
                          borderRadius: 'var(--radius-md)',
                          background: 'var(--surface-primary)',
                          color: 'var(--text-primary)',
                          fontSize: 'var(--font-size-sm)',
                          fontFamily: 'monospace'
                        }}
                      />
                    </div>
                </div>
              </div>
              )}

              {/* Portal Credentials */}
              {(formData.connection_method === 'portal' || !formData.connection_method) && (
              <div style={{
                padding: 'var(--space-4)',
                background: 'rgba(249, 138, 51, 0.05)',
                border: '1px solid rgba(249, 138, 51, 0.2)',
                borderRadius: 'var(--radius-lg)',
                opacity: formData.connection_method && formData.connection_method !== 'portal' ? 0.5 : 1,
              }}>
                <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-3)', color: 'var(--text-primary)' }}>
                  Portal Credentials
                </h3>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        Portal URL
                      </label>
                      <input
                        type="url"
                        placeholder="https://portal.payer.com"
                        value={formData.auth_portal_url || ''}
                        onChange={(e) => handleInputChange('auth_portal_url', e.target.value)}
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

                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        Portal Username
                      </label>
                      <input
                        type="text"
                        placeholder="Enter portal username"
                        value={formData.portal_username || ''}
                        onChange={(e) => handleInputChange('portal_username', e.target.value)}
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

                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        Portal Password
                        <span style={{ marginLeft: 'var(--space-2)', color: '#F98A33', fontSize: 'var(--font-size-xs)' }}>
                          Will be encrypted
                        </span>
                      </label>
                      <input
                        type="password"
                        placeholder="Enter portal password (will be encrypted on save)"
                        value={credentials.portal_password}
                        onChange={(e) => handleCredentialChange('portal_password', e.target.value)}
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
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                        Encrypted with AES-256-GCM. Never shown after save.
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Security Notice */}
              <div style={{
                display: 'flex',
                gap: 'var(--space-3)',
                padding: 'var(--space-4)',
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid #25D366',
                borderRadius: 'var(--radius-md)'
              }}>
                <PremiumIcon name="security" style={{ fontSize: 'var(--font-size-xl)', color: '#25D366' }} />
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 'var(--space-1)', color: 'var(--text-primary)' }}>
                    Credentials are Encrypted
                  </div>
                  <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    All credentials are encrypted using AES-256-GCM before being stored in the database. 
                    Passwords and API keys are never shown in plaintext after saving. Only authorized personnel 
                    can update credentials, and all changes are logged for audit purposes.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* REQUIREMENTS TAB */}
          {activeTab === 'requirements' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Claim Requirements
              </h2>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.requires_taxonomy || false}
                    onChange={(e) => handleInputChange('requires_taxonomy', e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Requires Taxonomy Code</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      Provider taxonomy required in 837 claim
                    </div>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.requires_npi_type_2 || false}
                    onChange={(e) => handleInputChange('requires_npi_type_2', e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Requires NPI Type 2</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      Organization NPI required (in addition to provider NPI)
                    </div>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.requires_tin || false}
                    onChange={(e) => handleInputChange('requires_tin', e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Requires TIN</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      Tax Identification Number required
                    </div>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.requires_clia || false}
                    onChange={(e) => handleInputChange('requires_clia', e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Requires CLIA Number</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      Clinical Laboratory Improvement Amendments number (for lab services)
                    </div>
                  </div>
                </label>
              </div>
            </div>
          )}

          {/* TELEHEALTH TAB */}
          {activeTab === 'telehealth' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Telehealth Configuration
              </h2>

              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.supports_telehealth || false}
                  onChange={(e) => handleInputChange('supports_telehealth', e.target.checked)}
                  style={{ cursor: 'pointer' }}
                />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Supports Telehealth</div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                    This payer accepts telehealth claims
                  </div>
                </div>
              </label>

              {formData.supports_telehealth && (
                <>
                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                      Telehealth Modifiers (comma-separated)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., 95, GT, FQ"
                      value={formData.telehealth_modifiers?.join(', ') || ''}
                      onChange={(e) => handleInputChange('telehealth_modifiers', e.target.value.split(',').map(m => m.trim()))}
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
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                      Common: 95 (synchronous), GT (interactive audio/video), FQ (audio-only)
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                      Telehealth POS Codes (comma-separated)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., 02, 10"
                      value={formData.telehealth_pos_codes?.join(', ') || ''}
                      onChange={(e) => handleInputChange('telehealth_pos_codes', e.target.value.split(',').map(m => m.trim()))}
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
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                      Common: 02 (telehealth), 10 (patient's home)
                    </div>
                  </div>

                  <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={formData.telehealth_parity || false}
                      onChange={(e) => handleInputChange('telehealth_parity', e.target.checked)}
                      style={{ cursor: 'pointer' }}
                    />
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Telehealth Parity</div>
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                        Pays same rate as in-person visits
                      </div>
                    </div>
                  </label>
                </>
              )}
            </div>
          )}

          {/* AUTH & ELIGIBILITY TAB */}
          {activeTab === 'auth' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Authorization & Eligibility
              </h2>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.supports_270_271 || false}
                    onChange={(e) => handleInputChange('supports_270_271', e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Supports 270/271 Eligibility</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      Real-time eligibility verification via EDI
                    </div>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.supports_276_277 || false}
                    onChange={(e) => handleInputChange('supports_276_277', e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Supports 276/277 Claim Status</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      Real-time claim status inquiry
                    </div>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.supports_278_auth || false}
                    onChange={(e) => handleInputChange('supports_278_auth', e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Supports 278 Prior Authorization</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      Electronic prior auth via EDI
                    </div>
                  </div>
                </label>
              </div>

              {!formData.supports_278_auth && (
                <div>
                  <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                    Prior Auth Portal URL (if portal-only)
                  </label>
                  <input
                    type="url"
                    placeholder="https://auth.payer.com"
                    value={formData.auth_portal_url || ''}
                    onChange={(e) => handleInputChange('auth_portal_url', e.target.value)}
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
              )}
            </div>
          )}

          {/* ERA/EFT TAB */}
          {activeTab === 'era_eft' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                ERA/EFT Enrollment
              </h2>

              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.supports_835_era || false}
                  onChange={(e) => handleInputChange('supports_835_era', e.target.checked)}
                  style={{ cursor: 'pointer' }}
                />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Supports 835 ERA</div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                    Electronic Remittance Advice
                  </div>
                </div>
              </label>

              {formData.supports_835_era && (
                <>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={formData.era_enrollment_required || false}
                      onChange={(e) => handleInputChange('era_enrollment_required', e.target.checked)}
                      style={{ cursor: 'pointer' }}
                    />
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>ERA Enrollment Required</div>
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                        Providers must enroll separately for ERA
                      </div>
                    </div>
                  </label>

                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                      ERA Enrollment URL
                    </label>
                    <input
                      type="url"
                      placeholder="https://enroll.payer.com/era"
                      value={formData.era_enrollment_url || ''}
                      onChange={(e) => handleInputChange('era_enrollment_url', e.target.value)}
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

                  <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={formData.eft_enrollment_required || false}
                      onChange={(e) => handleInputChange('eft_enrollment_required', e.target.checked)}
                      style={{ cursor: 'pointer' }}
                    />
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>EFT Enrollment Required</div>
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                        Electronic Funds Transfer enrollment needed
                      </div>
                    </div>
                  </label>
                </>
              )}
            </div>
          )}

          {/* SLAs TAB */}
          {activeTab === 'slas' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Service Level Agreements & Deadlines
              </h2>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Timely Filing Limit (days)
                </label>
                <input
                  type="number"
                  placeholder="365"
                  value={formData.filing_limit_days || ''}
                  onChange={(e) => handleInputChange('filing_limit_days', Number(e.target.value))}
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
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                  Claims must be submitted within this many days from service date
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Prior Auth Response Time (days)
                </label>
                <input
                  type="number"
                  placeholder="14"
                  value={formData.auth_response_days || ''}
                  onChange={(e) => handleInputChange('auth_response_days', Number(e.target.value))}
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

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Appeal Window (days)
                </label>
                <input
                  type="number"
                  placeholder="180"
                  value={formData.appeal_window_days || ''}
                  onChange={(e) => handleInputChange('appeal_window_days', Number(e.target.value))}
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
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                  Time allowed to file an appeal after denial
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Audit Response Time (days)
                </label>
                <input
                  type="number"
                  placeholder="14"
                  value={formData.audit_response_days || ''}
                  onChange={(e) => handleInputChange('audit_response_days', Number(e.target.value))}
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
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                  Time allowed to respond to medical record requests
                </div>
              </div>
            </div>
          )}

          {/* CONTRACT TAB */}
          {activeTab === 'contract' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Contract Information
              </h2>

              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.has_contract || false}
                  onChange={(e) => handleInputChange('has_contract', e.target.checked)}
                  style={{ cursor: 'pointer' }}
                />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Has Active Contract</div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                    You have a signed contract with this payer
                  </div>
                </div>
              </label>

              {formData.has_contract && (
                <>
                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                      Contract Type
                    </label>
                    <select
                      value={formData.contract_type || ''}
                      onChange={(e) => handleInputChange('contract_type', e.target.value)}
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
                      <option value="">Select type...</option>
                      <option value="direct">Direct Contract</option>
                      <option value="network">Network Agreement</option>
                      <option value="non_par">Non-Par (Out of Network)</option>
                    </select>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        Effective Date
                      </label>
                      <input
                        type="date"
                        value={formData.contract_effective_date || ''}
                        onChange={(e) => handleInputChange('contract_effective_date', e.target.value)}
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

                    <div>
                      <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                        End Date (if applicable)
                      </label>
                      <input
                        type="date"
                        value={formData.contract_end_date || ''}
                        onChange={(e) => handleInputChange('contract_end_date', e.target.value)}
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
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                      Contract Notes
                    </label>
                    <textarea
                      placeholder="Add notes about contract terms, renewal dates, special agreements..."
                      value={formData.contract_notes || ''}
                      onChange={(e) => handleInputChange('contract_notes', e.target.value)}
                      rows={4}
                      style={{
                        width: '100%',
                        padding: 'var(--space-3)',
                        border: '1px solid var(--border-primary)',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--surface-primary)',
                        color: 'var(--text-primary)',
                        fontSize: 'var(--font-size-sm)',
                        resize: 'vertical'
                      }}
                    />
                  </div>
                </>
              )}
            </div>
          )}

          {/* PAPER FALLBACK TAB */}
          {activeTab === 'paper' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxWidth: '600px' }}>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Paper Claim Fallback
              </h2>

              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.paper_claim_supported || false}
                  onChange={(e) => handleInputChange('paper_claim_supported', e.target.checked)}
                  style={{ cursor: 'pointer' }}
                />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Supports Paper Claims</div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                    Can submit paper CMS-1500/UB-04 forms
                  </div>
                </div>
              </label>

              {formData.paper_claim_supported && (
                <>
                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                      Mailing Address
                    </label>
                    <textarea
                      placeholder="Enter complete mailing address for paper claims"
                      value={formData.paper_claim_address || ''}
                      onChange={(e) => handleInputChange('paper_claim_address', e.target.value)}
                      rows={4}
                      style={{
                        width: '100%',
                        padding: 'var(--space-3)',
                        border: '1px solid var(--border-primary)',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--surface-primary)',
                        color: 'var(--text-primary)',
                        fontSize: 'var(--font-size-sm)',
                        resize: 'vertical'
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                      Fax Number
                    </label>
                    <input
                      type="tel"
                      placeholder="(808) 555-1234"
                      value={formData.paper_claim_fax || ''}
                      onChange={(e) => handleInputChange('paper_claim_fax', e.target.value)}
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
                </>
              )}
            </div>
          )}

          {/* RULES TAB */}
          {activeTab === 'rules' && (
            <div>
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
                Decision Table Rules
              </h2>
              <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
                <PremiumIcon name="code" style={{ fontSize: '4rem', marginBottom: 'var(--space-4)', opacity: 0.3 }} />
                <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                  Visual Rule Builder
                </h3>
                <p style={{ maxWidth: '500px', margin: '0 auto var(--space-4)', lineHeight: 1.6 }}>
                  Save the payer profile first, then access the visual rule builder to configure claim validation rules, 
                  modifier assignments, and routing logic.
                </p>
                {!isNew && (
                  <button
                    onClick={() => navigate(`/admin/payers/${payerId}/rules`)}
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
                    Open Rule Builder
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Bottom Actions */}
        <div style={{
          marginTop: 'var(--space-6)',
          display: 'flex',
          justifyContent: 'space-between',
          padding: 'var(--space-4)',
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)'
        }}>
          <button
            onClick={() => navigate('/admin/payers')}
            style={{
              padding: 'var(--space-3) var(--space-6)',
              background: 'transparent',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-secondary)',
              fontSize: 'var(--font-size-base)',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Back to List
          </button>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button
              onClick={handleSave}
              disabled={saveMutation.isLoading}
              style={{
                padding: 'var(--space-3) var(--space-8)',
                background: 'var(--gradient-primary)',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                color: 'white',
                fontSize: 'var(--font-size-base)',
                fontWeight: 600,
                cursor: saveMutation.isLoading ? 'not-allowed' : 'pointer',
                opacity: saveMutation.isLoading ? 0.5 : 1
              }}
            >
              {saveMutation.isLoading ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

