/**
 * Denial Detail Page
 * Show denial details, playbook instructions, generate appeal
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from 'react-query';
import { apiService } from '@/services/api';
import { PremiumIcon } from '@/services/iconReplacementService';
import { formatCurrency, formatDate } from '@/utils/formatters';
import Modal from '@/components/Modal';
import toast from 'react-hot-toast';

export default function DenialDetail() {
  const { denialId } = useParams<{ denialId: string }>();
  const navigate = useNavigate();
  const [showAppealLetter, setShowAppealLetter] = useState(false);
  const [appealLetter, setAppealLetter] = useState('');

  // Fetch denial details
  const { data, isLoading, isError, error } = useQuery(
    ['denial-case', denialId],
    () => apiService.get(`/rcm/denials/cases/${denialId}`),
    { retry: 1 }
  );

  // Generate appeal mutation
  const generateAppealMutation = useMutation(
    () => apiService.post(`/rcm/denials/cases/${denialId}/generate-appeal`),
    {
      onSuccess: (response) => {
        const appealData = response.data;
        setAppealLetter(appealData.appeal_letter);
        setShowAppealLetter(true);
        toast.success('Appeal letter generated!');
      },
      onError: () => {
        toast.error('Failed to generate appeal');
      }
    }
  );

  if (isLoading) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
        <PremiumIcon name="spinner" size="xl" />
      </div>
    );
  }

  if (isError || !data?.data?.denial) {
    return (
      <div style={{ padding: 'var(--space-8)', maxWidth: 600, margin: '0 auto' }}>
        <div className="card" style={{ padding: 'var(--space-6)', borderColor: 'var(--brand-error)' }}>
          <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, color: 'var(--brand-error)', marginBottom: 'var(--space-3)' }}>
            Failed to load denial case
          </h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-4)' }}>
            {(error as any)?.message || 'The denial case could not be found or you do not have access.'}
          </p>
          <button
            className="btn btn-ghost"
            onClick={() => navigate('/denials')}
            style={{ padding: 'var(--space-3) var(--space-4)' }}
          >
            Back to Denials
          </button>
        </div>
      </div>
    );
  }

  const denial = data.data.denial;
  const playbook = data.data.playbook;

  const getPriorityColor = (priority: string) => {
    const colors: Record<string, string> = {
      'critical': 'var(--brand-error)',
      'high': '#F98A33',
      'medium': '#009DDD',
      'low': 'var(--text-secondary)'
    };
    return colors[priority] || 'var(--text-secondary)';
  };

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
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
                <h1 style={{
                  fontSize: 'var(--font-size-3xl)',
                  fontWeight: 700,
                  background: 'var(--gradient-primary)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent'
                }}>
                  Denial Case - {denial.claim_number}
                </h1>
                <span style={{
                  padding: 'var(--space-2) var(--space-3)',
                  background: getPriorityColor(denial.priority),
                  color: 'white',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600
                }}>
                  {denial.priority.toUpperCase()} PRIORITY
                </span>
              </div>
              <p style={{ color: 'var(--text-secondary)' }}>
                CARC: {denial.carc_code} {denial.rarc_code && `| RARC: ${denial.rarc_code}`}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }} className="no-print">
              <button
                onClick={() => window.print()}
                style={{
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'transparent',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--text-primary)',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                title="Print this denial case + appeal letter"
              >
                Print
              </button>
              <button
                onClick={() => navigate('/denials')}
                style={{
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'transparent',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Back to Denials
              </button>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
          {/* Denial Info */}
          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-6)'
          }}>
            <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
              Denial Information
            </h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Denied Amount</div>
                <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 700, color: 'var(--brand-error)' }}>
                  {formatCurrency(denial.denied_amount)}
                </div>
              </div>
              
              <div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Denial Reason</div>
                <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)' }}>
                  {denial.denial_description}
                </div>
              </div>
              
              <div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Category</div>
                <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {denial.denial_category.replace(/_/g, ' ').toUpperCase()}
                </div>
              </div>
              
              {denial.appeal_due_date && (
                <div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Appeal Deadline</div>
                  <div style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, color: denial.days_until_due < 14 ? 'var(--brand-error)' : 'var(--text-primary)' }}>
                    {formatDate(denial.appeal_due_date)}
                    <span style={{ fontSize: 'var(--font-size-sm)', marginLeft: 'var(--space-2)' }}>
                      ({denial.days_until_due} days)
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Playbook & Actions */}
          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-6)'
          }}>
            <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
              Appeal Playbook
            </h2>
            
            {playbook ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Strategy</div>
                  <div style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {playbook.name}
                  </div>
                </div>
                
                {playbook.instructions && (
                  <div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
                      Instructions
                    </div>
                    <div style={{
                      padding: 'var(--space-3)',
                      background: 'rgba(59, 130, 246, 0.1)',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--font-size-sm)',
                      color: 'var(--text-primary)',
                      whiteSpace: 'pre-wrap'
                    }}>
                      {playbook.instructions}
                    </div>
                  </div>
                )}
                
                {playbook.required_attachments && playbook.required_attachments.length > 0 && (
                  <div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
                      Required Attachments
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
                      {playbook.required_attachments.map((attachment: string, idx: number) => (
                        <div key={idx} style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)' }}>
                          - {attachment}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                <button
                  onClick={() => generateAppealMutation.mutate()}
                  disabled={generateAppealMutation.isLoading}
                  style={{
                    padding: 'var(--space-3) var(--space-6)',
                    background: 'var(--gradient-primary)',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    color: 'white',
                    fontSize: 'var(--font-size-base)',
                    fontWeight: 600,
                    cursor: generateAppealMutation.isLoading ? 'not-allowed' : 'pointer',
                    opacity: generateAppealMutation.isLoading ? 0.5 : 1
                  }}
                >
                  {generateAppealMutation.isLoading ? 'Generating...' : 'Generate Appeal Letter'}
                </button>
              </div>
            ) : (
              <p style={{ color: 'var(--text-secondary)' }}>
                No playbook assigned. Configure playbooks for this denial code.
              </p>
            )}
          </div>
        </div>

        {/* Appeal Letter Modal */}
        <Modal
          isOpen={showAppealLetter}
          onClose={() => setShowAppealLetter(false)}
          title="Appeal Letter"
          width={800}
        >
          <div style={{
            padding: 'var(--space-4)',
            background: 'var(--surface-secondary)',
            borderRadius: 'var(--radius-md)',
            fontFamily: 'monospace',
            fontSize: 'var(--font-size-sm)',
            whiteSpace: 'pre-wrap',
            maxHeight: '500px',
            overflowY: 'auto',
            marginBottom: 'var(--space-4)'
          }}>
            {appealLetter}
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
            <button
              onClick={() => {
                navigator.clipboard.writeText(appealLetter);
                toast.success('Copied to clipboard!');
              }}
              style={{
                padding: 'var(--space-3) var(--space-6)',
                background: 'transparent',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                fontSize: 'var(--font-size-base)',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Copy to Clipboard
            </button>
            <button
              onClick={() => {
                const blob = new Blob([appealLetter], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `appeal_${denial.claim_number}.txt`;
                a.click();
                URL.revokeObjectURL(url);
                toast.success('Appeal letter downloaded!');
              }}
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
              Download Letter
            </button>
          </div>
        </Modal>
      </div>
    </div>
  );
}

