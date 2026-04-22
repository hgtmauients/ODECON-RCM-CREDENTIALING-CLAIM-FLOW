/**
 * Payer Profile Service
 * API client for RCM payer profile management
 */

import { apiService } from './api';
import { logger } from '@/utils/logger';

export interface PayerProfile {
  id: number;
  name: string;
  display_name?: string;
  payer_id?: string;
  naic_code?: string;
  plan_ids?: string[];
  
  // Connectivity
  clearinghouse?: string;
  trading_partner_id?: string;
  submitter_id?: string;
  receiver_id?: string;
  connection_method?: 'clearinghouse' | 'sftp' | 'api' | 'portal';
  endpoint_url?: string;
  
  // Formats
  format_837_type?: '837I' | '837P';
  supports_pwk_attachments?: boolean;
  attachment_method?: string;
  
  // Telehealth
  supports_telehealth?: boolean;
  telehealth_modifiers?: string[];
  telehealth_pos_codes?: string[];
  telehealth_parity?: boolean;
  
  // Requirements
  requires_taxonomy?: boolean;
  requires_npi_type_2?: boolean;
  requires_tin?: boolean;
  requires_clia?: boolean;
  
  // Eligibility/Auth
  supports_270_271?: boolean;
  supports_276_277?: boolean;
  supports_278_auth?: boolean;
  auth_portal_url?: string;
  
  // ERA/EFT
  supports_835_era?: boolean;
  era_enrollment_required?: boolean;
  era_enrollment_url?: string;
  era_enrollment_forms?: string[];
  eft_enrollment_required?: boolean;
  
  // SLAs
  filing_limit_days?: number;
  filing_limit_from?: string;
  auth_response_days?: number;
  appeal_window_days?: number;
  audit_response_days?: number;
  
  // Contract
  has_contract?: boolean;
  contract_type?: string;
  contract_effective_date?: string;
  contract_end_date?: string;
  contract_notes?: string;
  
  // Claim Frequency
  supports_corrected_claims?: boolean;
  accepts_secondary_claims?: boolean;
  
  // Paper
  paper_claim_supported?: boolean;
  paper_claim_address?: string;
  paper_claim_fax?: string;
  
  // State
  state_code?: string;
  state_specific_requirements?: Record<string, unknown>;
  
  // Metadata
  is_active: boolean;
  is_draft: boolean;
  version: number;
  created_at?: string;
  updated_at?: string;
  created_by?: string;
  updated_by?: string;
  notes?: string;
  
  // Counts
  rules_count?: number;
  connections_count?: number;
  fee_schedules_count?: number;

  // Credential fields (stored on backend, not in type system)
  sftp_username?: string;
  portal_username?: string;
  [key: string]: unknown;
}

export interface PayerRule {
  id?: number;
  payer_id: number;
  rule_name: string;
  description?: string;
  priority: number;
  conditions: Record<string, any>;
  actions: Record<string, any>;
  is_active: boolean;
  created_at?: string;
  created_by?: string;
}

export interface TradingPartnerConnection {
  id?: number;
  payer_id: number;
  connection_name: string;
  clearinghouse_name: string;
  connection_type: 'sftp' | 'api' | 'web_portal';
  
  // SFTP
  sftp_host?: string;
  sftp_port?: number;
  sftp_username?: string;
  sftp_password?: string; // Will be encrypted before sending
  sftp_inbound_path?: string;
  sftp_outbound_path?: string;
  
  // API
  api_endpoint?: string;
  api_version?: string;
  api_key?: string; // Will be encrypted
  api_secret?: string; // Will be encrypted
  api_auth_method?: string;
  
  // Portal
  portal_url?: string;
  portal_username?: string;
  portal_password?: string; // Will be encrypted
  
  // File naming
  file_name_pattern?: string;
  
  // Status
  is_active: boolean;
  last_tested?: string;
  last_test_status?: string;
  last_test_message?: string;
}

export interface FeeScheduleUpload {
  payer_id: number;
  file: File;
  state_code?: string;
  locality?: string;
  effective_date?: string;
}

export interface PayerVersion {
  id: number;
  version_number: number;
  change_summary: string;
  changed_by: string;
  changed_at: string;
  is_published: boolean;
  published_at?: string;
  published_by?: string;
}

class PayerProfileService {
  /**
   * List all payer profiles with filters
   */
  async listPayers(params?: {
    state_code?: string;
    is_active?: boolean;
    is_draft?: boolean;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ data: PayerProfile[]; total: number }> {
    try {
      logger.debug('Listing payer profiles', params);
      
      const response = await apiService.get('/rcm/payers', params ? { params } as any : undefined);
      
      return {
        data: response.data || [],
        total: response.total || 0
      };
    } catch (error) {
      logger.error('Error listing payers', { error });
      throw error;
    }
  }

  /**
   * Get full payer profile details
   */
  async getPayerProfile(payerId: number): Promise<PayerProfile> {
    try {
      logger.debug('Getting payer profile', { payerId });
      
      const response = await apiService.get(`/rcm/payers/${payerId}`);
      
      return response.data;
    } catch (error) {
      logger.error('Error getting payer profile', { error, payerId });
      throw error;
    }
  }

  /**
   * Create new payer profile
   */
  async createPayer(payerData: Partial<PayerProfile>): Promise<{ id: number; version: number }> {
    try {
      logger.debug('Creating payer profile', { name: payerData.name });
      
      const response = await apiService.post('/rcm/payers', payerData);
      
      return response.data;
    } catch (error) {
      logger.error('Error creating payer profile', { error });
      throw error;
    }
  }

  /**
   * Update payer profile
   */
  async updatePayer(payerId: number, updates: Partial<PayerProfile>): Promise<{ id: number; version: number }> {
    try {
      logger.debug('Updating payer profile', { payerId });
      
      const response = await apiService.put(`/rcm/payers/${payerId}`, updates);
      
      return response.data;
    } catch (error) {
      logger.error('Error updating payer profile', { error, payerId });
      throw error;
    }
  }

  /**
   * Publish payer profile (Draft → Published)
   */
  async publishPayer(payerId: number): Promise<void> {
    try {
      logger.debug('Publishing payer profile', { payerId });
      
      await apiService.post(`/rcm/payers/${payerId}/publish`);
    } catch (error) {
      logger.error('Error publishing payer profile', { error, payerId });
      throw error;
    }
  }

  /**
   * Deactivate payer profile
   */
  async deletePayer(payerId: number): Promise<void> {
    try {
      logger.debug('Deleting payer profile', { payerId });
      
      await apiService.delete(`/rcm/payers/${payerId}`);
    } catch (error) {
      logger.error('Error deleting payer profile', { error, payerId });
      throw error;
    }
  }

  /**
   * Get payer rules
   */
  async getPayerRules(payerId: number, isActive: boolean = true): Promise<PayerRule[]> {
    try {
      logger.debug('Getting payer rules', { payerId });
      
      const response = await apiService.get(`/rcm/payers/${payerId}/rules`, {
        params: { is_active: isActive }
      });
      
      return response.data.data || [];
    } catch (error) {
      logger.error('Error getting payer rules', { error, payerId });
      throw error;
    }
  }

  /**
   * Create payer rule
   */
  async createRule(payerId: number, ruleData: Omit<PayerRule, 'id' | 'payer_id'>): Promise<{ id: number }> {
    try {
      logger.debug('Creating payer rule', { payerId, ruleName: ruleData.rule_name });
      
      const response = await apiService.post(`/rcm/payers/${payerId}/rules`, ruleData);
      
      return response.data;
    } catch (error) {
      logger.error('Error creating payer rule', { error, payerId });
      throw error;
    }
  }

  /**
   * Update payer rule
   */
  async updateRule(ruleId: number, updates: Partial<PayerRule>): Promise<void> {
    try {
      logger.debug('Updating payer rule', { ruleId });
      
      await apiService.put(`/rcm/payers/rules/${ruleId}`, updates);
    } catch (error) {
      logger.error('Error updating payer rule', { error, ruleId });
      throw error;
    }
  }

  /**
   * Delete payer rule
   */
  async deleteRule(ruleId: number): Promise<void> {
    try {
      logger.debug('Deleting payer rule', { ruleId });
      
      await apiService.delete(`/rcm/payers/rules/${ruleId}`);
    } catch (error) {
      logger.error('Error deleting payer rule', { error, ruleId });
      throw error;
    }
  }

  /**
   * Get payer connections
   */
  async getPayerConnections(payerId: number): Promise<TradingPartnerConnection[]> {
    try {
      logger.debug('Getting payer connections', { payerId });
      
      const response = await apiService.get(`/rcm/payers/${payerId}/connections`);
      
      return response.data.data || [];
    } catch (error) {
      logger.error('Error getting payer connections', { error, payerId });
      throw error;
    }
  }

  /**
   * Create payer connection
   */
  async createConnection(payerId: number, connectionData: Omit<TradingPartnerConnection, 'id' | 'payer_id'>): Promise<{ id: number }> {
    try {
      logger.debug('Creating payer connection', { payerId, connectionName: connectionData.connection_name });
      
      const response = await apiService.post(`/rcm/payers/${payerId}/connections`, connectionData);
      
      return response.data;
    } catch (error) {
      logger.error('Error creating payer connection', { error, payerId });
      throw error;
    }
  }

  /**
   * Upload fee schedule CSV
   */
  async uploadFeeSchedule(upload: FeeScheduleUpload): Promise<{ batch_id: string; count: number }> {
    try {
      logger.debug('Uploading fee schedule', { payerId: upload.payer_id });
      
      const formData = new FormData();
      formData.append('file', upload.file);
      if (upload.state_code) formData.append('state_code', upload.state_code);
      if (upload.locality) formData.append('locality', upload.locality);
      if (upload.effective_date) formData.append('effective_date', upload.effective_date);
      
      const response = await apiService.post(
        `/rcm/payers/${upload.payer_id}/fee-schedules/upload`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' }
        }
      );
      
      return response.data;
    } catch (error) {
      logger.error('Error uploading fee schedule', { error });
      throw error;
    }
  }

  /**
   * Get version history
   */
  async getVersionHistory(payerId: number, limit: number = 50): Promise<PayerVersion[]> {
    try {
      logger.debug('Getting version history', { payerId });
      
      const response = await apiService.get(`/rcm/payers/${payerId}/versions`, {
        params: { limit }
      });
      
      return response.data.data || [];
    } catch (error) {
      logger.error('Error getting version history', { error, payerId });
      throw error;
    }
  }

  /**
   * Test clearinghouse connection
   */
  async testConnection(payerId: number): Promise<{ success: boolean; message: string }> {
    try {
      logger.debug('Testing connection', { payerId });
      
      const response = await apiService.post(`/rcm/payers/${payerId}/test-connection`);
      
      return {
        success: response.data.success,
        message: response.data.message
      };
    } catch (error) {
      logger.error('Error testing connection', { error, payerId });
      throw error;
    }
  }
}

// Export singleton instance
export const payerProfileService = new PayerProfileService();

