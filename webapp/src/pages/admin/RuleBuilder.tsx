/**
 * Visual Rule Builder
 * Ops can configure decision table rules without code
 * Rules automatically applied to claims before submission
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from 'react-query';
import { payerProfileService, type PayerRule } from '@/services/payerProfileService';
import { PremiumIcon } from '@/services/iconReplacementService';
import { logger } from '@/utils/logger';
import toast from 'react-hot-toast';

export default function RuleBuilder() {
  const { payerId } = useParams<{ payerId: string }>();
  const navigate = useNavigate();
  const [showNewRuleModal, setShowNewRuleModal] = useState(false);
  const [editingRule, setEditingRule] = useState<PayerRule | null>(null);

  // Fetch payer info
  const { data: payer } = useQuery(
    ['payer-profile', payerId],
    () => payerProfileService.getPayerProfile(Number(payerId)),
    { enabled: !!payerId }
  );

  // Fetch rules
  const { data: rules, isLoading, refetch } = useQuery(
    ['payer-rules', payerId],
    () => payerProfileService.getPayerRules(Number(payerId!)),
    { enabled: !!payerId }
  );

  // Create rule mutation
  const createRuleMutation = useMutation(
    (ruleData: Omit<PayerRule, 'id' | 'payer_id'>) => 
      payerProfileService.createRule(Number(payerId), ruleData),
    {
      onSuccess: () => {
        toast.success('Rule created successfully');
        refetch();
        setShowNewRuleModal(false);
        setEditingRule(null);
      },
      onError: (error) => {
        logger.error('Error creating rule', { error });
        toast.error('Failed to create rule');
      }
    }
  );

  // Update rule mutation
  const updateRuleMutation = useMutation(
    ({ ruleId, updates }: { ruleId: number; updates: Partial<PayerRule> }) =>
      payerProfileService.updateRule(ruleId, updates),
    {
      onSuccess: () => {
        toast.success('Rule updated successfully');
        refetch();
        setEditingRule(null);
      },
      onError: (error) => {
        logger.error('Error updating rule', { error });
        toast.error('Failed to update rule');
      }
    }
  );

  // Delete rule mutation
  const deleteRuleMutation = useMutation(
    (ruleId: number) => payerProfileService.deleteRule(ruleId),
    {
      onSuccess: () => {
        toast.success('Rule deleted successfully');
        refetch();
      },
      onError: (error) => {
        logger.error('Error deleting rule', { error });
        toast.error('Failed to delete rule');
      }
    }
  );

  const handleDeleteRule = (rule: PayerRule) => {
    if (confirm(`Delete rule "${rule.rule_name}"?`)) {
      deleteRuleMutation.mutate(rule.id!);
    }
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
              <h1 style={{
                fontSize: 'var(--font-size-3xl)',
                fontWeight: 700,
                marginBottom: 'var(--space-2)',
                background: 'var(--gradient-primary)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent'
              }}>
                Decision Table Rules: {payer?.name}
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-base)' }}>
                Configure rules that are automatically applied to claims before submission
              </p>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button
                onClick={() => navigate(`/admin/payers/${payerId}`)}
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
                Back to Payer
              </button>
              <button
                onClick={() => setShowNewRuleModal(true)}
                style={{
                  padding: 'var(--space-3) var(--space-6)',
                  background: 'var(--gradient-primary)',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  color: 'white',
                  fontSize: 'var(--font-size-base)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)'
                }}
              >
                + New Rule
              </button>
            </div>
          </div>
        </div>

        {/* Rules List */}
        {isLoading ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <PremiumIcon name="spinner" spin style={{ fontSize: '2rem' }} />
          </div>
        ) : !rules || rules.length === 0 ? (
          <div style={{
            background: 'var(--surface-glass)',
            backdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-8)',
            textAlign: 'center'
          }}>
            <PremiumIcon name="code" style={{ fontSize: '4rem', marginBottom: 'var(--space-4)', opacity: 0.3, color: 'var(--text-secondary)' }} />
            <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              No Rules Yet
            </h3>
            <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-4)' }}>
              Create your first rule to automate claim validation and modifier assignment
            </p>
            <button
              onClick={() => setShowNewRuleModal(true)}
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
              Create First Rule
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {rules.map((rule) => (
              <div key={rule.id} style={{
                background: 'var(--surface-glass)',
                backdropFilter: 'var(--glass-blur)',
                border: '1px solid var(--glass-border)',
                borderRadius: 'var(--radius-lg)',
                padding: 'var(--space-6)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-4)' }}>
                  <div>
                    <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: 'var(--space-1)', color: 'var(--text-primary)' }}>
                      {rule.rule_name}
                    </h3>
                    {rule.description && (
                      <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                        {rule.description}
                      </p>
                    )}
                    <div style={{ marginTop: 'var(--space-2)', display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
                      <span style={{
                        padding: 'var(--space-1) var(--space-2)',
                        background: rule.is_active ? 'var(--brand-success)' : 'var(--text-secondary)',
                        color: 'white',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600
                      }}>
                        {rule.is_active ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                      <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                        Priority: {rule.priority}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                    <button
                      onClick={() => setEditingRule(rule)}
                      style={{
                        padding: 'var(--space-2) var(--space-3)',
                        background: 'var(--gradient-primary)',
                        border: 'none',
                        borderRadius: 'var(--radius-sm)',
                        color: 'white',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeleteRule(rule)}
                      style={{
                        padding: 'var(--space-2) var(--space-3)',
                        background: 'transparent',
                        border: '1px solid var(--brand-error)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--brand-error)',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
                  {/* Conditions */}
                  <div>
                    <h4 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-3)', color: 'var(--text-secondary)' }}>
                      Conditions (When)
                    </h4>
                    <div style={{
                      padding: 'var(--space-3)',
                      background: 'rgba(59, 130, 246, 0.1)',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      borderRadius: 'var(--radius-md)',
                      fontFamily: 'monospace',
                      fontSize: 'var(--font-size-sm)',
                      color: 'var(--text-primary)'
                    }}>
                      <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(rule.conditions, null, 2)}
                      </pre>
                    </div>
                  </div>

                  {/* Actions */}
                  <div>
                    <h4 style={{ fontSize: 'var(--font-size-base)', fontWeight: 600, marginBottom: 'var(--space-3)', color: 'var(--text-secondary)' }}>
                      Actions (Then)
                    </h4>
                    <div style={{
                      padding: 'var(--space-3)',
                      background: 'rgba(16, 185, 129, 0.1)',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                      borderRadius: 'var(--radius-md)',
                      fontFamily: 'monospace',
                      fontSize: 'var(--font-size-sm)',
                      color: 'var(--text-primary)'
                    }}>
                      <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(rule.actions, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Example Rules Helper */}
        <div style={{
          marginTop: 'var(--space-6)',
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.3)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6)'
        }}>
          <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
            Example Rules
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div style={{
              padding: 'var(--space-4)',
              background: 'var(--surface-primary)',
              borderRadius: 'var(--radius-md)'
            }}>
              <h4 style={{ fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Telehealth Modifier 95
              </h4>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <strong>When:</strong> CPT in [99214, 99215] AND POS in [02, 10]<br />
                <strong>Then:</strong> Add modifier 95, Set telehealth_parity flag
              </div>
              <details style={{ marginTop: 'var(--space-2)' }}>
                <summary style={{ cursor: 'pointer', fontSize: 'var(--font-size-xs)', color: 'var(--brand-primary)' }}>
                  View JSON
                </summary>
                <pre style={{ 
                  marginTop: 'var(--space-2)', 
                  padding: 'var(--space-2)', 
                  background: 'var(--surface-secondary)', 
                  borderRadius: 'var(--radius-sm)', 
                  fontSize: 'var(--font-size-xs)',
                  overflow: 'auto'
                }}>
{`{
  "name": "Telehealth Modifier 95",
  "conditions": {
    "cpt_codes": ["99214", "99215"],
    "pos": ["02", "10"]
  },
  "actions": {
    "add_modifiers": ["95"],
    "set_flags": ["telehealth_parity"]
  }
}`}
                </pre>
              </details>
            </div>

            <div style={{
              padding: 'var(--space-4)',
              background: 'var(--surface-primary)',
              borderRadius: 'var(--radius-md)'
            }}>
              <h4 style={{ fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Require Prior Auth for High-Cost Procedures
              </h4>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <strong>When:</strong> CPT in [20610, 20611] (Joint injections)<br />
                <strong>Then:</strong> Require prior authorization, Route to "Auth Required" queue
              </div>
              <details style={{ marginTop: 'var(--space-2)' }}>
                <summary style={{ cursor: 'pointer', fontSize: 'var(--font-size-xs)', color: 'var(--brand-primary)' }}>
                  View JSON
                </summary>
                <pre style={{ 
                  marginTop: 'var(--space-2)', 
                  padding: 'var(--space-2)', 
                  background: 'var(--surface-secondary)', 
                  borderRadius: 'var(--radius-sm)', 
                  fontSize: 'var(--font-size-xs)',
                  overflow: 'auto'
                }}>
{`{
  "name": "Require Auth for Joint Injections",
  "conditions": {
    "cpt_codes": ["20610", "20611"]
  },
  "actions": {
    "require_auth": true,
    "route_to_queue": "auth_required"
  }
}`}
                </pre>
              </details>
            </div>

            <div style={{
              padding: 'var(--space-4)',
              background: 'var(--surface-primary)',
              borderRadius: 'var(--radius-md)'
            }}>
              <h4 style={{ fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                SUD Coverage Policy Attachment
              </h4>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <strong>When:</strong> Diagnosis starts with F11 (Opioid use disorder)<br />
                <strong>Then:</strong> Add PWK attachment with SUD coverage policy
              </div>
              <details style={{ marginTop: 'var(--space-2)' }}>
                <summary style={{ cursor: 'pointer', fontSize: 'var(--font-size-xs)', color: 'var(--brand-primary)' }}>
                  View JSON
                </summary>
                <pre style={{ 
                  marginTop: 'var(--space-2)', 
                  padding: 'var(--space-2)', 
                  background: 'var(--surface-secondary)', 
                  borderRadius: 'var(--radius-sm)', 
                  fontSize: 'var(--font-size-xs)',
                  overflow: 'auto'
                }}>
{`{
  "name": "SUD Coverage Policy",
  "conditions": {
    "diagnosis_pattern": "F11.*"
  },
  "actions": {
    "add_attachment": "SUD_coverage_policy",
    "set_flags": ["requires_documentation"]
  }
}`}
                </pre>
              </details>
            </div>
          </div>

          <div style={{ marginTop: 'var(--space-4)', padding: 'var(--space-3)', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid #009DDD', borderRadius: 'var(--radius-md)' }}>
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-start' }}>
              <PremiumIcon name="info" style={{ color: '#009DDD', marginTop: 'var(--space-1)' }} />
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <strong>How Rules Work:</strong> Rules are evaluated in priority order (highest first) when a claim is validated before submission. 
                If conditions match, actions are executed automatically. Use the examples above as templates for common scenarios.
              </div>
            </div>
          </div>
        </div>

        {/* New Rule Modal */}
        {showNewRuleModal && (
          <RuleEditorModal
            payerId={Number(payerId)}
            onClose={() => setShowNewRuleModal(false)}
            onSave={(ruleData) => createRuleMutation.mutate(ruleData)}
            isSaving={createRuleMutation.isLoading}
          />
        )}

        {/* Edit Rule Modal */}
        {editingRule && (
          <RuleEditorModal
            payerId={Number(payerId)}
            existingRule={editingRule}
            onClose={() => setEditingRule(null)}
            onSave={(ruleData) => updateRuleMutation.mutate({ ruleId: editingRule.id!, updates: ruleData })}
            isSaving={updateRuleMutation.isLoading}
          />
        )}
      </div>
    </div>
  );
}

// Rule Editor Modal Component
interface RuleEditorModalProps {
  payerId: number;
  existingRule?: PayerRule;
  onClose: () => void;
  onSave: (ruleData: Omit<PayerRule, 'id' | 'payer_id'>) => void;
  isSaving: boolean;
}

const RuleEditorModal: React.FC<RuleEditorModalProps> = ({ existingRule, onClose, onSave, isSaving }) => {
  const [ruleName, setRuleName] = useState(existingRule?.rule_name || '');
  const [description, setDescription] = useState(existingRule?.description || '');
  const [priority, setPriority] = useState(existingRule?.priority || 0);
  const [conditionsJson, setConditionsJson] = useState(
    JSON.stringify(existingRule?.conditions || { cpt_codes: [], pos: [] }, null, 2)
  );
  const [actionsJson, setActionsJson] = useState(
    JSON.stringify(existingRule?.actions || { add_modifiers: [] }, null, 2)
  );

  const handleSave = () => {
    try {
      const conditions = JSON.parse(conditionsJson);
      const actions = JSON.parse(actionsJson);

      onSave({
        rule_name: ruleName,
        description,
        priority,
        conditions,
        actions,
        is_active: true
      });
    } catch (error) {
      toast.error('Invalid JSON in conditions or actions');
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: 'var(--space-6)'
    }}>
      <div style={{
        background: 'var(--surface-primary)',
        borderRadius: 'var(--radius-xl)',
        padding: 'var(--space-6)',
        maxWidth: '800px',
        width: '100%',
        maxHeight: '90vh',
        overflow: 'auto'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-6)' }}>
          <h2 style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 700, color: 'var(--text-primary)' }}>
            {existingRule ? 'Edit Rule' : 'New Rule'}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-secondary)',
              fontSize: 'var(--font-size-xl)',
              cursor: 'pointer'
            }}
          >
            X
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Rule Name *
            </label>
            <input
              type="text"
              placeholder="e.g., Telehealth Modifier 95"
              value={ruleName}
              onChange={(e) => setRuleName(e.target.value)}
              style={{
                width: '100%',
                padding: 'var(--space-3)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--surface-secondary)',
                color: 'var(--text-primary)',
                fontSize: 'var(--font-size-sm)'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Description
            </label>
            <textarea
              placeholder="What does this rule do?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              style={{
                width: '100%',
                padding: 'var(--space-3)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--surface-secondary)',
                color: 'var(--text-primary)',
                fontSize: 'var(--font-size-sm)',
                resize: 'vertical'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Priority (higher runs first)
            </label>
            <input
              type="number"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              style={{
                width: '100%',
                padding: 'var(--space-3)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--surface-secondary)',
                color: 'var(--text-primary)',
                fontSize: 'var(--font-size-sm)'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Conditions (JSON) *
            </label>
            <textarea
              value={conditionsJson}
              onChange={(e) => setConditionsJson(e.target.value)}
              rows={8}
              style={{
                width: '100%',
                padding: 'var(--space-3)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--surface-secondary)',
                color: 'var(--text-primary)',
                fontSize: 'var(--font-size-sm)',
                fontFamily: 'monospace',
                resize: 'vertical'
              }}
            />
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
              Supported fields: cpt_codes, pos, diagnosis_pattern, state, age, sex, telehealth
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
              Actions (JSON) *
            </label>
            <textarea
              value={actionsJson}
              onChange={(e) => setActionsJson(e.target.value)}
              rows={8}
              style={{
                width: '100%',
                padding: 'var(--space-3)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--surface-secondary)',
                color: 'var(--text-primary)',
                fontSize: 'var(--font-size-sm)',
                fontFamily: 'monospace',
                resize: 'vertical'
              }}
            />
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
              Supported actions: add_modifiers, require_auth, route_to_queue, set_flags, add_attachment, reject_with_reason
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end', marginTop: 'var(--space-6)' }}>
          <button
            onClick={onClose}
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
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !ruleName}
            style={{
              padding: 'var(--space-3) var(--space-8)',
              background: 'var(--gradient-primary)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              color: 'white',
              fontSize: 'var(--font-size-base)',
              fontWeight: 600,
              cursor: isSaving || !ruleName ? 'not-allowed' : 'pointer',
              opacity: isSaving || !ruleName ? 0.5 : 1
            }}
          >
            {isSaving ? 'Saving...' : 'Save Rule'}
          </button>
        </div>
      </div>
    </div>
  );
};

