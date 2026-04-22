/**
 * Payer Enrollment Case Detail
 * View and manage a single payer enrollment case (checklist, status, documents)
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import { formatDate } from '@/utils/formatters';
import toast from 'react-hot-toast';

interface ChecklistItem {
  item: string;
  required: boolean;
  completed: boolean;
  doc_id?: number;
  completed_date?: string;
}

interface EnrollmentCaseDetail {
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
  checklist: ChecklistItem[];
  payer_rep_name?: string;
  payer_rep_email?: string;
  payer_rep_phone?: string;
  ticket_number?: string;
  notes?: string;
  created_at: string;
}

export default function PayerEnrollmentDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState('');

  const { data, isLoading } = useQuery(
    ['enrollment-case', caseId],
    () => apiService.get(`/rcm/payer-enrollment/cases/${caseId}`)
  );

  const enrollmentCase: EnrollmentCaseDetail | null = data?.data || null;

  const checklistMutation = useMutation(
    (updatedChecklist: ChecklistItem[]) =>
      apiService.put(`/rcm/payer-enrollment/cases/${caseId}/checklist`, updatedChecklist),
    {
      onSuccess: (response) => {
        toast.success(`Checklist updated - ${response?.data?.completion_percentage || 0}% complete`);
        queryClient.invalidateQueries(['enrollment-case', caseId]);
      },
      onError: () => { toast.error('Failed to update checklist'); },
    }
  );

  const handleChecklistToggle = (index: number) => {
    if (!enrollmentCase) return;
    const updated = [...enrollmentCase.checklist];
    updated[index] = { ...updated[index], completed: !updated[index].completed };
    if (updated[index].completed) {
      updated[index].completed_date = new Date().toISOString().split('T')[0];
    } else {
      updated[index].completed_date = undefined;
    }
    checklistMutation.mutate(updated);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'var(--brand-success)';
      case 'submitted': return 'var(--brand-warning)';
      case 'in_review': return '#009DDD';
      case 'rejected': return 'var(--brand-error)';
      case 'ready_to_submit': return '#25D366';
      case 'draft': return 'var(--text-secondary)';
      default: return 'var(--text-secondary)';
    }
  };

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <div style={{ width: 24, height: 24, border: '3px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
      </div>
    );
  }

  if (!enrollmentCase) {
    return (
      <div style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
        <h2 style={{ color: 'var(--text-primary)', marginBottom: 'var(--space-2)' }}>Case Not Found</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-4)' }}>This enrollment case could not be loaded.</p>
        <button className="btn btn-primary" onClick={() => navigate('/payer-enrollment')}>
          Back to Enrollment
        </button>
      </div>
    );
  }

  const completedCount = enrollmentCase.checklist?.filter(i => i.completed).length || 0;
  const totalCount = enrollmentCase.checklist?.length || 0;

  return (
    <div>
      {/* Back + Header */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => navigate('/payer-enrollment')}
          style={{ marginBottom: 'var(--space-3)' }}
        >
          Back to Enrollment
        </button>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 className="page-title">{enrollmentCase.provider_name}</h1>
            <p className="page-subtitle">
              Enrollment with {enrollmentCase.payer_name}
            </p>
          </div>
          <span style={{
            padding: '4px 12px',
            background: getStatusColor(enrollmentCase.status),
            color: 'white',
            borderRadius: 'var(--radius-full)',
            fontSize: 'var(--font-size-xs)',
            fontWeight: 600,
            textTransform: 'uppercase',
          }}>
            {enrollmentCase.status.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 'var(--space-6)' }}>
        {/* Left: Checklist */}
        <div>
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600 }}>Enrollment Checklist</h2>
              <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                {completedCount}/{totalCount} complete
              </span>
            </div>

            {/* Progress bar */}
            <div style={{ height: 6, background: 'var(--bg-secondary)', borderRadius: 'var(--radius-full)', marginBottom: 'var(--space-5)', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${enrollmentCase.completion_percentage}%`,
                background: enrollmentCase.completion_percentage === 100 ? 'var(--brand-success)' : 'var(--brand-primary)',
                borderRadius: 'var(--radius-full)',
                transition: 'width 0.3s ease',
              }} />
            </div>

            {/* Checklist items */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {(enrollmentCase.checklist || []).map((item, idx) => (
                <label
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-3)',
                    padding: 'var(--space-3)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-light)',
                    cursor: 'pointer',
                    transition: 'background var(--transition-fast)',
                    background: item.completed ? 'var(--brand-success-light)' : 'transparent',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={item.completed}
                    onChange={() => handleChecklistToggle(idx)}
                    style={{ width: 18, height: 18, cursor: 'pointer' }}
                  />
                  <div style={{ flex: 1 }}>
                    <span style={{
                      fontSize: 'var(--font-size-sm)',
                      fontWeight: 500,
                      color: item.completed ? 'var(--brand-success)' : 'var(--text-primary)',
                      textDecoration: item.completed ? 'line-through' : 'none',
                    }}>
                      {item.item}
                    </span>
                    {item.required && !item.completed && (
                      <span style={{ marginLeft: 'var(--space-2)', fontSize: 'var(--font-size-xs)', color: 'var(--brand-error)' }}>Required</span>
                    )}
                  </div>
                  {item.completed_date && (
                    <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
                      {item.completed_date}
                    </span>
                  )}
                </label>
              ))}
            </div>

            {totalCount === 0 && (
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)', textAlign: 'center', padding: 'var(--space-6)' }}>
                No checklist items configured for this payer.
              </p>
            )}
          </div>
        </div>

        {/* Right: Info sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Case Info */}
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>Case Details</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <InfoRow label="Provider ID" value={enrollmentCase.provider_id} />
              <InfoRow label="Payer" value={enrollmentCase.payer_name} />
              <InfoRow label="Assigned To" value={enrollmentCase.assigned_to || 'Unassigned'} />
              <InfoRow label="Created" value={formatDate(enrollmentCase.created_at)} />
              <InfoRow label="Submitted" value={enrollmentCase.submitted_date ? formatDate(enrollmentCase.submitted_date) : '--'} />
              <InfoRow label="Effective" value={enrollmentCase.effective_date ? formatDate(enrollmentCase.effective_date) : '--'} />
              <InfoRow label="Expiration" value={enrollmentCase.expiration_date ? formatDate(enrollmentCase.expiration_date) : '--'} />
            </div>
          </div>

          {/* Payer Contact */}
          {(enrollmentCase.payer_rep_name || enrollmentCase.payer_rep_email) && (
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>Payer Contact</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {enrollmentCase.payer_rep_name && <InfoRow label="Name" value={enrollmentCase.payer_rep_name} />}
                {enrollmentCase.payer_rep_email && <InfoRow label="Email" value={enrollmentCase.payer_rep_email} />}
                {enrollmentCase.payer_rep_phone && <InfoRow label="Phone" value={enrollmentCase.payer_rep_phone} />}
                {enrollmentCase.ticket_number && <InfoRow label="Ticket #" value={enrollmentCase.ticket_number} />}
              </div>
            </div>
          )}

          {/* Notes */}
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <h3 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>Notes</h3>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
              {enrollmentCase.notes || 'No notes added.'}
            </p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--font-size-sm)' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{value}</span>
    </div>
  );
}
