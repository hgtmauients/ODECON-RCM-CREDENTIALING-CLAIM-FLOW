/**
 * Create New Claim
 * Form for manual claim entry with patient, provider, payer, service lines, and diagnoses
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from 'react-query';
import { apiService } from '@/services/api';
import toast from 'react-hot-toast';
import CodeAutocomplete from '@/components/rcm/CodeAutocomplete';
import CPTWizard from '@/components/rcm/CPTWizard';

interface ClaimLine {
  cpt_code: string;
  cpt_description: string;
  units: number;
  charge_amount: string;
  place_of_service: string;
  modifiers: string;
}

interface Diagnosis {
  icd10_code: string;
  icd10_description: string;
  is_primary: boolean;
}

export default function ClaimCreate() {
  const navigate = useNavigate();

  // Fetch available payers and patients for dropdowns
  const { data: payersData } = useQuery('payers-for-claims', () => apiService.get('/rcm/payers'));
  const { data: patientsData } = useQuery('patients-for-claims', () => apiService.get('/rcm/patients'));
  const payers: Array<{ id: number; name: string; payer_id?: string }> = payersData?.data || [];
  const patients: Array<{ id: number; first_name: string; last_name: string; member_id: string }> = patientsData?.data || [];

  const [form, setForm] = useState({
    patient_id: '',
    provider_id: '',
    payer_id: '',
    service_date_from: '',
    service_date_to: '',
    claim_type: 'professional',
    billing_provider_npi: '',
    rendering_provider_npi: '',
    prior_auth_number: '',
  });

  const [lines, setLines] = useState<ClaimLine[]>([
    { cpt_code: '', cpt_description: '', units: 1, charge_amount: '', place_of_service: '11', modifiers: '' },
  ]);

  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([
    { icd10_code: '', icd10_description: '', is_primary: true },
  ]);

  const [wizardLineIndex, setWizardLineIndex] = useState<number | null>(null);

  const createMutation = useMutation(
    (data: Record<string, unknown>) => apiService.post('/rcm/claims', data),
    {
      onSuccess: (response: any) => {
        const claimId = response?.data?.id;
        toast.success(`Claim ${response?.data?.claim_number || ''} created`);
        navigate(claimId ? `/claims/${claimId}` : '/claims');
      },
      onError: () => { toast.error('Failed to create claim'); },
    }
  );

  const handleFieldChange = (field: string, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const handleLineChange = (index: number, field: keyof ClaimLine, value: string | number) => {
    setLines(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const addLine = () => {
    setLines(prev => [...prev, { cpt_code: '', cpt_description: '', units: 1, charge_amount: '', place_of_service: '11', modifiers: '' }]);
  };

  const removeLine = (index: number) => {
    if (lines.length <= 1) return;
    setLines(prev => prev.filter((_, i) => i !== index));
  };

  const handleDxChange = (index: number, field: keyof Diagnosis, value: string | boolean) => {
    setDiagnoses(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      if (field === 'is_primary' && value === true) {
        updated.forEach((d, i) => { if (i !== index) d.is_primary = false; });
      }
      return updated;
    });
  };

  const addDiagnosis = () => {
    setDiagnoses(prev => [...prev, { icd10_code: '', icd10_description: '', is_primary: false }]);
  };

  const removeDiagnosis = (index: number) => {
    if (diagnoses.length <= 1) return;
    setDiagnoses(prev => prev.filter((_, i) => i !== index));
  };

  const totalCharges = lines.reduce((sum, l) => sum + (parseFloat(l.charge_amount) || 0) * l.units, 0);

  const handleSubmit = () => {
    if (!form.service_date_from) { toast.error('Service date is required'); return; }
    if (!lines[0]?.cpt_code) { toast.error('At least one CPT code is required'); return; }
    if (!diagnoses[0]?.icd10_code) { toast.error('At least one diagnosis is required'); return; }

    createMutation.mutate({
      patient_id: form.patient_id ? parseInt(form.patient_id) : null,
      provider_id: form.provider_id ? parseInt(form.provider_id) : null,
      payer_id: form.payer_id ? parseInt(form.payer_id) : null,
      service_date_from: form.service_date_from,
      service_date_to: form.service_date_to || form.service_date_from,
      total_charges: totalCharges,
      claim_type: form.claim_type,
      billing_provider_npi: form.billing_provider_npi || null,
      rendering_provider_npi: form.rendering_provider_npi || null,
      prior_auth_number: form.prior_auth_number || null,
      lines: lines.filter(l => l.cpt_code).map((l, i) => ({
        line_number: i + 1,
        cpt_code: l.cpt_code,
        cpt_description: l.cpt_description,
        units: l.units,
        charge_amount: parseFloat(l.charge_amount) || 0,
        place_of_service: l.place_of_service,
        modifiers: l.modifiers ? l.modifiers.split(',').map(m => m.trim()) : null,
        diagnosis_pointers: [1],
      })),
      diagnoses: diagnoses.filter(d => d.icd10_code).map((d, i) => ({
        diagnosis_pointer: i + 1,
        icd10_code: d.icd10_code,
        icd10_description: d.icd10_description,
        is_primary: d.is_primary,
      })),
    });
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    border: '1px solid var(--border-light)',
    borderRadius: 'var(--radius-md)',
    fontSize: 'var(--font-size-sm)',
    background: 'var(--surface-primary)',
    color: 'var(--text-primary)',
  };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    marginBottom: 4,
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  };

  return (
    <div>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/claims')} style={{ marginBottom: 'var(--space-3)' }}>
          Back to Claims
        </button>
        <h1 className="page-title">New Claim</h1>
        <p className="page-subtitle">Enter claim details for manual submission</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
        {/* Left column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Claim Info */}
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>Claim Information</h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
              <div>
                <label style={labelStyle}>Service Date From</label>
                <input type="date" value={form.service_date_from} onChange={e => handleFieldChange('service_date_from', e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Service Date To</label>
                <input type="date" value={form.service_date_to} onChange={e => handleFieldChange('service_date_to', e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Claim Type</label>
                <select value={form.claim_type} onChange={e => handleFieldChange('claim_type', e.target.value)} style={inputStyle}>
                  <option value="professional">Professional (837P)</option>
                  <option value="institutional">Institutional (837I)</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>Prior Auth #</label>
                <input value={form.prior_auth_number} onChange={e => handleFieldChange('prior_auth_number', e.target.value)} placeholder="If required" style={inputStyle} />
              </div>
            </div>
          </div>

          {/* IDs */}
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-4)' }}>References</h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
              <div>
                <label style={labelStyle}>Patient</label>
                <div style={{ display: 'flex', gap: 4 }}>
                  <select value={form.patient_id} onChange={e => handleFieldChange('patient_id', e.target.value)} style={{ ...inputStyle, flex: 1 }}>
                    <option value="">Select patient...</option>
                    {patients.map(p => (
                      <option key={p.id} value={String(p.id)}>{p.last_name}, {p.first_name} ({p.member_id})</option>
                    ))}
                  </select>
                  <button className="btn btn-ghost btn-sm" style={{ whiteSpace: 'nowrap', fontSize: 10 }} onClick={() => navigate('/patients')}>Manage</button>
                </div>
              </div>
              <div>
                <label style={labelStyle}>Payer</label>
                <select value={form.payer_id} onChange={e => handleFieldChange('payer_id', e.target.value)} style={inputStyle}>
                  <option value="">Select payer...</option>
                  {payers.map(p => (
                    <option key={p.id} value={String(p.id)}>{p.name}{p.payer_id ? ` (${p.payer_id})` : ''}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={labelStyle}>Billing NPI</label>
                <input value={form.billing_provider_npi} onChange={e => handleFieldChange('billing_provider_npi', e.target.value)} placeholder="10-digit NPI" maxLength={10} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Rendering NPI</label>
                <input value={form.rendering_provider_npi} onChange={e => handleFieldChange('rendering_provider_npi', e.target.value)} placeholder="If different" maxLength={10} style={inputStyle} />
              </div>
            </div>
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Diagnoses */}
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600 }}>Diagnoses</h2>
              <button className="btn btn-ghost btn-sm" onClick={addDiagnosis}>+ Add</button>
            </div>
            {diagnoses.map((dx, i) => (
              <div key={i} style={{ marginBottom: 'var(--space-2)' }}>
                <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-end' }}>
                  <div style={{ width: 160 }}>
                    {i === 0 && <label style={labelStyle}>ICD-10 Code</label>}
                    <CodeAutocomplete type="icd10" value={dx.icd10_code} onChange={(code, desc) => { handleDxChange(i, 'icd10_code', code); handleDxChange(i, 'icd10_description', desc); }} placeholder="Search ICD-10..." />
                  </div>
                  <div style={{ flex: 1 }}>
                    {i === 0 && <label style={labelStyle}>Description</label>}
                    <input value={dx.icd10_description} onChange={e => handleDxChange(i, 'icd10_description', e.target.value)} placeholder="Auto-filled from code lookup" style={inputStyle} />
                  </div>
                  <div style={{ marginBottom: 2 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--font-size-xs)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
                      <input type="checkbox" checked={dx.is_primary} onChange={() => handleDxChange(i, 'is_primary', !dx.is_primary)} /> Primary
                    </label>
                  </div>
                  {diagnoses.length > 1 && (
                    <button className="btn btn-ghost btn-sm" onClick={() => removeDiagnosis(i)} style={{ color: 'var(--brand-error)', padding: '4px 8px' }}>X</button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Service Lines */}
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600 }}>Service Lines</h2>
              <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                <button className="btn btn-ghost btn-sm" onClick={addLine}>+ Add Line</button>
              </div>
            </div>
            {lines.map((line, i) => (
              <div key={i} style={{ marginBottom: 'var(--space-3)' }}>
                <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-end' }}>
                  <div style={{ width: 160 }}>
                    {i === 0 && <label style={labelStyle}>CPT Code</label>}
                    <div style={{ display: 'flex', gap: 4 }}>
                      <CodeAutocomplete type="cpt" value={line.cpt_code} onChange={(code, desc) => { handleLineChange(i, 'cpt_code', code); handleLineChange(i, 'cpt_description', desc); }} placeholder="Search CPT..." />
                      <button className="btn btn-ghost btn-sm" style={{ padding: '4px 8px', fontSize: 10, whiteSpace: 'nowrap' }} onClick={() => setWizardLineIndex(i)}>Guide</button>
                    </div>
                  </div>
                  <div style={{ width: 100 }}>
                    {i === 0 && <label style={labelStyle}>Charge ($)</label>}
                    <input value={line.charge_amount} onChange={e => handleLineChange(i, 'charge_amount', e.target.value)} placeholder="0.00" style={inputStyle} />
                  </div>
                  <div style={{ width: 60 }}>
                    {i === 0 && <label style={labelStyle}>Units</label>}
                    <input type="number" value={line.units} onChange={e => handleLineChange(i, 'units', parseInt(e.target.value) || 1)} min={1} style={inputStyle} />
                  </div>
                  <div style={{ width: 70 }}>
                    {i === 0 && <label style={labelStyle}>POS</label>}
                    <select value={line.place_of_service} onChange={e => handleLineChange(i, 'place_of_service', e.target.value)} style={inputStyle}>
                      <option value="11">11 - Office</option>
                      <option value="02">02 - Telehealth</option>
                      <option value="10">10 - Telehealth (Home)</option>
                      <option value="21">21 - Inpatient Hospital</option>
                      <option value="22">22 - Outpatient Hospital</option>
                      <option value="23">23 - Emergency Room</option>
                      <option value="24">24 - Ambulatory Surgery</option>
                      <option value="31">31 - Skilled Nursing</option>
                      <option value="32">32 - Nursing Facility</option>
                      <option value="12">12 - Home</option>
                      <option value="49">49 - Independent Clinic</option>
                      <option value="81">81 - Independent Lab</option>
                    </select>
                  </div>
                  <div style={{ width: 120 }}>
                    {i === 0 && <label style={labelStyle}>Modifier</label>}
                    <select value={(line.modifiers || '').split(',')[0] || ''} onChange={e => handleLineChange(i, 'modifiers', e.target.value)} style={inputStyle}>
                      <option value="">None</option>
                      <option value="25">25 - Significant, separate E/M</option>
                      <option value="59">59 - Distinct procedural service</option>
                      <option value="95">95 - Synchronous telehealth</option>
                      <option value="GT">GT - Via interactive telehealth</option>
                      <option value="FQ">FQ - Telehealth, audio-only</option>
                      <option value="26">26 - Professional component</option>
                      <option value="TC">TC - Technical component</option>
                      <option value="50">50 - Bilateral procedure</option>
                      <option value="51">51 - Multiple procedures</option>
                      <option value="52">52 - Reduced services</option>
                      <option value="57">57 - Decision for surgery</option>
                      <option value="76">76 - Repeat procedure, same physician</option>
                      <option value="77">77 - Repeat procedure, different physician</option>
                      <option value="78">78 - Unplanned return to OR</option>
                      <option value="79">79 - Unrelated procedure during postop</option>
                      <option value="80">80 - Assistant surgeon</option>
                      <option value="XE">XE - Separate encounter</option>
                      <option value="XS">XS - Separate structure</option>
                      <option value="XP">XP - Separate practitioner</option>
                      <option value="XU">XU - Unusual non-overlapping service</option>
                    </select>
                  </div>
                  {lines.length > 1 && (
                    <button className="btn btn-ghost btn-sm" onClick={() => removeLine(i)} style={{ color: 'var(--brand-error)', padding: '4px 8px' }}>X</button>
                  )}
                </div>
              </div>
            ))}
            <div style={{ marginTop: 'var(--space-3)', textAlign: 'right', fontSize: 'var(--font-size-base)', fontWeight: 700 }}>
              Total: ${totalCharges.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {/* Submit bar */}
      <div style={{ marginTop: 'var(--space-6)', display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)' }}>
        <button className="btn btn-ghost" onClick={() => navigate('/claims')}>Cancel</button>
        <button className="btn btn-primary btn-lg" onClick={handleSubmit} disabled={createMutation.isLoading}>
          {createMutation.isLoading ? 'Creating...' : 'Create Claim'}
        </button>
      </div>

      {/* CPT Wizard Modal */}
      {wizardLineIndex !== null && (
        <CPTWizard
          onCancel={() => setWizardLineIndex(null)}
          onSelect={(result) => {
            const i = wizardLineIndex;
            handleLineChange(i, 'cpt_code', result.cpt_code);
            handleLineChange(i, 'cpt_description', result.cpt_description);
            handleLineChange(i, 'place_of_service', result.pos);
            if (result.modifiers.length > 0) {
              handleLineChange(i, 'modifiers', result.modifiers[0]);
            }
            // If there's an add-on code, add a new line
            if (result.addon_code) {
              setLines(prev => [...prev, {
                cpt_code: result.addon_code || '',
                cpt_description: result.addon_description || '',
                units: 1,
                charge_amount: '',
                place_of_service: result.pos,
                modifiers: '',
              }]);
            }
            setWizardLineIndex(null);
          }}
        />
      )}
    </div>
  );
}
