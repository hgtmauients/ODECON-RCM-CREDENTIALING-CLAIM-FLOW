/**
 * CPT Guided Wizard
 * Step-by-step decision tree that narrows to the right CPT code + modifiers + POS.
 * Supports: Primary Care E/M, Psychiatry, Psychotherapy, Preventive, Procedures.
 */

import React, { useState } from 'react';

interface WizardResult {
  cpt_code: string;
  cpt_description: string;
  addon_code?: string;
  addon_description?: string;
  pos: string;
  pos_description: string;
  modifiers: string[];
  modifier_descriptions: string[];
  warnings: string[];
}

interface CPTWizardProps {
  onSelect: (result: WizardResult) => void;
  onCancel: () => void;
}

type Step = 'service_type' | 'specialty' | 'patient_status' | 'telehealth' | 'patient_location' | 'level' | 'psych_eval_type' | 'psychotherapy_time' | 'psychotherapy_with_em' | 'same_day_procedure' | 'result';

interface WizardState {
  service_type: string;
  specialty: string;
  patient_status: string;
  telehealth: string;
  patient_location: string;
  level: string;
  psych_eval_type: string;
  psychotherapy_time: string;
  psychotherapy_with_em: string;
  same_day_procedure: string;
}

export default function CPTWizard({ onSelect, onCancel }: CPTWizardProps) {
  const [step, setStep] = useState<Step>('service_type');
  const [state, setState] = useState<WizardState>({
    service_type: '', specialty: '', patient_status: '', telehealth: '',
    patient_location: '', level: '', psych_eval_type: '', psychotherapy_time: '',
    psychotherapy_with_em: '', same_day_procedure: '',
  });

  const set = (key: keyof WizardState, value: string, nextStep: Step) => {
    setState(prev => ({ ...prev, [key]: value }));
    setStep(nextStep);
  };

  const back = (targetStep: Step) => setStep(targetStep);

  const cardStyle: React.CSSProperties = { padding: '12px 16px', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', cursor: 'pointer', transition: 'all 0.15s', fontSize: 'var(--font-size-sm)' };
  const selectedStyle: React.CSSProperties = { ...cardStyle, borderColor: 'var(--brand-primary)', background: 'var(--brand-primary-light)' };

  const Option = ({ label, description, onClick }: { label: string; description?: string; onClick: () => void }) => (
    <div style={cardStyle} onClick={onClick} onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--brand-primary)'; e.currentTarget.style.background = 'var(--bg-secondary)'; }} onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-light)'; e.currentTarget.style.background = 'transparent'; }}>
      <div style={{ fontWeight: 600 }}>{label}</div>
      {description && <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 2 }}>{description}</div>}
    </div>
  );

  // Build result from wizard state
  const buildResult = (): WizardResult => {
    let cpt = '', desc = '', addon = '', addonDesc = '';
    let pos = '11', posDesc = 'Office';
    let modifiers: string[] = [], modDescs: string[] = [], warnings: string[] = [];

    // POS from telehealth
    if (state.telehealth === 'yes_home') { pos = '10'; posDesc = 'Telehealth (Patient Home)'; }
    else if (state.telehealth === 'yes_other') { pos = '02'; posDesc = 'Telehealth (Other)'; }
    else if (state.telehealth === 'audio_only') { pos = '02'; posDesc = 'Telehealth (Audio-Only)'; modifiers.push('FQ'); modDescs.push('FQ - Telehealth, audio-only'); }

    // Telehealth modifier
    if (state.telehealth && state.telehealth !== 'no') {
      modifiers.push('95'); modDescs.push('95 - Synchronous telehealth');
      warnings.push('Verify payer accepts modifier 95 for telehealth. Some payers use GT instead.');
    }

    // Service type routing
    if (state.service_type === 'em_office') {
      const isNew = state.patient_status === 'new';
      const codes: Record<string, [string, string]> = {
        straightforward: isNew ? ['99202', 'Office visit, new, straightforward MDM'] : ['99212', 'Office visit, established, straightforward MDM'],
        low: isNew ? ['99203', 'Office visit, new, low MDM'] : ['99213', 'Office visit, established, low MDM'],
        moderate: isNew ? ['99204', 'Office visit, new, moderate MDM'] : ['99214', 'Office visit, established, moderate MDM'],
        high: isNew ? ['99205', 'Office visit, new, high MDM'] : ['99215', 'Office visit, established, high MDM'],
      };
      [cpt, desc] = codes[state.level] || codes['moderate'];
    }
    else if (state.service_type === 'psych_eval') {
      if (state.psych_eval_type === 'with_medical') { cpt = '90792'; desc = 'Psychiatric diagnostic evaluation with medical services'; }
      else { cpt = '90791'; desc = 'Psychiatric diagnostic evaluation'; }
    }
    else if (state.service_type === 'psychotherapy') {
      if (state.psychotherapy_with_em === 'yes') {
        // E/M + psychotherapy add-on
        const isNew = state.patient_status === 'new';
        const emCodes: Record<string, [string, string]> = {
          straightforward: isNew ? ['99202', 'Office visit, new, straightforward'] : ['99212', 'Office visit, established, straightforward'],
          low: isNew ? ['99203', 'Office visit, new, low MDM'] : ['99213', 'Office visit, established, low MDM'],
          moderate: isNew ? ['99204', 'Office visit, new, moderate MDM'] : ['99214', 'Office visit, established, moderate MDM'],
          high: isNew ? ['99205', 'Office visit, new, high MDM'] : ['99215', 'Office visit, established, high MDM'],
        };
        [cpt, desc] = emCodes[state.level] || emCodes['moderate'];

        const addons: Record<string, [string, string]> = {
          '16-37': ['90833', 'Psychotherapy add-on, 16-37 minutes'],
          '38-52': ['90836', 'Psychotherapy add-on, 38-52 minutes'],
          '53+': ['90838', 'Psychotherapy add-on, 53+ minutes'],
        };
        [addon, addonDesc] = addons[state.psychotherapy_time] || addons['16-37'];
      } else {
        const therapy: Record<string, [string, string]> = {
          '16-37': ['90832', 'Psychotherapy, 30 minutes'],
          '38-52': ['90834', 'Psychotherapy, 45 minutes'],
          '53+': ['90837', 'Psychotherapy, 60 minutes'],
        };
        [cpt, desc] = therapy[state.psychotherapy_time] || therapy['38-52'];
      }
    }
    else if (state.service_type === 'preventive') {
      const isNew = state.patient_status === 'new';
      cpt = isNew ? '99386' : '99396';
      desc = isNew ? 'Preventive visit, new patient, age 40-64' : 'Preventive visit, established patient, age 40-64';
      warnings.push('Select specific age-range preventive code (99381-99397) based on patient age.');
    }

    // Same-day procedure modifier
    if (state.same_day_procedure === 'yes') {
      modifiers.push('25'); modDescs.push('25 - Significant, separately identifiable E/M');
    }

    return { cpt_code: cpt, cpt_description: desc, addon_code: addon || undefined, addon_description: addonDesc || undefined, pos, pos_description: posDesc, modifiers, modifier_descriptions: modDescs, warnings };
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: 40, zIndex: 100, overflowY: 'auto' }} onClick={onCancel}>
      <div style={{ background: 'var(--surface-primary)', borderRadius: 'var(--radius-xl)', padding: 'var(--space-6)', width: 560, marginBottom: 40 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700 }}>Find the Right CPT Code</h2>
          <button className="btn btn-ghost btn-sm" onClick={onCancel}>Cancel</button>
        </div>

        {/* Step 1: Service Type */}
        {step === 'service_type' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)', color: 'var(--text-primary)' }}>What kind of service is this?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="Office / Outpatient E/M" description="99202-99215 - Standard evaluation and management" onClick={() => set('service_type', 'em_office', 'patient_status')} />
              <Option label="Psychiatric Diagnostic Evaluation" description="90791 / 90792 - Initial psych assessment" onClick={() => set('service_type', 'psych_eval', 'psych_eval_type')} />
              <Option label="Psychotherapy" description="90832-90838 - Therapy with or without E/M" onClick={() => set('service_type', 'psychotherapy', 'psychotherapy_with_em')} />
              <Option label="Preventive Medicine" description="99381-99397 - Annual wellness / preventive visit" onClick={() => set('service_type', 'preventive', 'patient_status')} />
            </div>
          </div>
        )}

        {/* Step: Psych eval type */}
        {step === 'psych_eval_type' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)' }}>Does this evaluation include medical services?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="Yes - Includes medical evaluation" description="90792 - Psychiatric diagnostic eval with medical services" onClick={() => set('psych_eval_type', 'with_medical', 'telehealth')} />
              <Option label="No - Psychiatric evaluation only" description="90791 - Psychiatric diagnostic eval without medical" onClick={() => set('psych_eval_type', 'no_medical', 'telehealth')} />
            </div>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={() => back('service_type')}>Back</button>
          </div>
        )}

        {/* Step: Psychotherapy with E/M? */}
        {step === 'psychotherapy_with_em' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)' }}>Was medical evaluation / E/M also performed?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="Yes - E/M + Psychotherapy" description="E/M base code + 90833/90836/90838 add-on" onClick={() => set('psychotherapy_with_em', 'yes', 'patient_status')} />
              <Option label="No - Psychotherapy only" description="90832 / 90834 / 90837 standalone" onClick={() => set('psychotherapy_with_em', 'no', 'psychotherapy_time')} />
            </div>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={() => back('service_type')}>Back</button>
          </div>
        )}

        {/* Step: New or Established */}
        {step === 'patient_status' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)' }}>New or established patient?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="New Patient" description="First visit with this provider" onClick={() => set('patient_status', 'new', state.service_type === 'psychotherapy' && state.psychotherapy_with_em === 'yes' ? 'level' : state.service_type === 'preventive' ? 'telehealth' : 'level')} />
              <Option label="Established Patient" description="Has been seen by this provider before" onClick={() => set('patient_status', 'established', state.service_type === 'psychotherapy' && state.psychotherapy_with_em === 'yes' ? 'level' : state.service_type === 'preventive' ? 'telehealth' : 'level')} />
            </div>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={() => back('service_type')}>Back</button>
          </div>
        )}

        {/* Step: MDM Level */}
        {step === 'level' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)' }}>Medical Decision Making (MDM) complexity?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="Straightforward" description="1 self-limited problem, minimal data, minimal risk" onClick={() => set('level', 'straightforward', state.psychotherapy_with_em === 'yes' ? 'psychotherapy_time' : 'telehealth')} />
              <Option label="Low" description="2+ self-limited problems OR 1 stable chronic, limited data" onClick={() => set('level', 'low', state.psychotherapy_with_em === 'yes' ? 'psychotherapy_time' : 'telehealth')} />
              <Option label="Moderate" description="1+ chronic with exacerbation OR new problem with workup" onClick={() => set('level', 'moderate', state.psychotherapy_with_em === 'yes' ? 'psychotherapy_time' : 'telehealth')} />
              <Option label="High" description="1+ chronic illness with severe exacerbation OR acute threat to life" onClick={() => set('level', 'high', state.psychotherapy_with_em === 'yes' ? 'psychotherapy_time' : 'telehealth')} />
            </div>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={() => back('patient_status')}>Back</button>
          </div>
        )}

        {/* Step: Psychotherapy Time */}
        {step === 'psychotherapy_time' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)' }}>Psychotherapy duration?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="16-37 minutes" description={state.psychotherapy_with_em === 'yes' ? '90833 add-on' : '90832 - Psychotherapy, 30 min'} onClick={() => set('psychotherapy_time', '16-37', 'telehealth')} />
              <Option label="38-52 minutes" description={state.psychotherapy_with_em === 'yes' ? '90836 add-on' : '90834 - Psychotherapy, 45 min'} onClick={() => set('psychotherapy_time', '38-52', 'telehealth')} />
              <Option label="53+ minutes" description={state.psychotherapy_with_em === 'yes' ? '90838 add-on' : '90837 - Psychotherapy, 60 min'} onClick={() => set('psychotherapy_time', '53+', 'telehealth')} />
            </div>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={() => back(state.psychotherapy_with_em === 'yes' ? 'level' : 'psychotherapy_with_em')}>Back</button>
          </div>
        )}

        {/* Step: Telehealth */}
        {step === 'telehealth' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)' }}>Was this a telehealth visit?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="No - In-person" description="POS 11 (Office)" onClick={() => set('telehealth', 'no', 'same_day_procedure')} />
              <Option label="Yes - Patient at home" description="POS 10 (Telehealth, patient home)" onClick={() => set('telehealth', 'yes_home', 'same_day_procedure')} />
              <Option label="Yes - Patient NOT at home" description="POS 02 (Telehealth, other location)" onClick={() => set('telehealth', 'yes_other', 'same_day_procedure')} />
              <Option label="Audio-only (telephone)" description="POS 02 + Modifier FQ" onClick={() => set('telehealth', 'audio_only', 'same_day_procedure')} />
            </div>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={() => back(state.service_type === 'psych_eval' ? 'psych_eval_type' : state.service_type === 'preventive' ? 'patient_status' : 'level')}>Back</button>
          </div>
        )}

        {/* Step: Same-day procedure */}
        {step === 'same_day_procedure' && (
          <div>
            <p style={{ fontWeight: 600, marginBottom: 'var(--space-3)' }}>Was there a same-day procedure or preventive service?</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Option label="No" description="No modifier 25 needed" onClick={() => set('same_day_procedure', 'no', 'result')} />
              <Option label="Yes - Separate E/M with procedure" description="Modifier 25 will be added" onClick={() => set('same_day_procedure', 'yes', 'result')} />
            </div>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={() => back('telehealth')}>Back</button>
          </div>
        )}

        {/* Result */}
        {step === 'result' && (() => {
          const result = buildResult();
          return (
            <div>
              <p style={{ fontWeight: 600, marginBottom: 'var(--space-4)', color: 'var(--brand-success)' }}>Recommended Code Bundle</p>
              <div style={{ background: 'var(--bg-secondary)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)', marginBottom: 'var(--space-3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
                  <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>CPT Code</span>
                  <span style={{ fontWeight: 700, fontFamily: 'monospace', color: 'var(--brand-primary)', fontSize: 'var(--font-size-lg)' }}>{result.cpt_code}</span>
                </div>
                <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)', marginBottom: 'var(--space-2)' }}>{result.cpt_description}</div>
                {result.addon_code && (
                  <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Add-on Code</span>
                      <span style={{ fontWeight: 700, fontFamily: 'monospace', color: '#7c3aed' }}>+ {result.addon_code}</span>
                    </div>
                    <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)' }}>{result.addon_description}</div>
                  </div>
                )}
                <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 'var(--space-2)', marginTop: 'var(--space-2)', display: 'flex', gap: 'var(--space-4)' }}>
                  <div><span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>POS</span><div style={{ fontWeight: 600 }}>{result.pos} - {result.pos_description}</div></div>
                  {result.modifiers.length > 0 && (
                    <div><span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>Modifiers</span><div style={{ fontWeight: 600 }}>{result.modifiers.join(', ')}</div></div>
                  )}
                </div>
              </div>
              {result.warnings.length > 0 && (
                <div style={{ background: 'var(--brand-warning-light)', border: '1px solid var(--brand-warning)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3)', marginBottom: 'var(--space-3)', fontSize: 'var(--font-size-xs)' }}>
                  {result.warnings.map((w, i) => <div key={i} style={{ color: 'var(--brand-warning)' }}>{w}</div>)}
                </div>
              )}
              <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'flex-end' }}>
                <button className="btn btn-ghost" onClick={() => { setState({ service_type: '', specialty: '', patient_status: '', telehealth: '', patient_location: '', level: '', psych_eval_type: '', psychotherapy_time: '', psychotherapy_with_em: '', same_day_procedure: '' }); setStep('service_type'); }}>Start Over</button>
                <button className="btn btn-primary" onClick={() => onSelect(result)}>Use This Code</button>
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
