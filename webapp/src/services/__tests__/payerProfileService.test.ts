import { beforeEach, describe, expect, it, vi } from 'vitest';
import { payerProfileService } from '../payerProfileService';
import { apiService } from '../api';

vi.mock('../api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    setAuthToken: vi.fn(),
    setTenantId: vi.fn(),
  },
}));

describe('payerProfileService response unwrapping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns rules from response.data envelope', async () => {
    vi.mocked(apiService.get).mockResolvedValue({
      success: true,
      data: [{ id: 1, rule_name: 'Telehealth modifier', priority: 1, conditions: {}, actions: {}, is_active: true }],
    });

    const rules = await payerProfileService.getPayerRules(123);

    expect(rules).toHaveLength(1);
    expect(rules[0].id).toBe(1);
  });

  it('returns connections from response.data envelope', async () => {
    vi.mocked(apiService.get).mockResolvedValue({
      success: true,
      data: [{ id: 5, payer_id: 123, connection_name: 'Waystar', clearinghouse_name: 'Waystar', connection_type: 'api', is_active: true }],
    });

    const connections = await payerProfileService.getPayerConnections(123);

    expect(connections).toHaveLength(1);
    expect(connections[0].id).toBe(5);
  });

  it('returns version history from response.data envelope', async () => {
    vi.mocked(apiService.get).mockResolvedValue({
      success: true,
      data: [{ id: 2, version_number: 4, change_summary: 'Updated filing limit', changed_by: 'ops@demo.test', changed_at: '2026-05-25T10:00:00Z', is_published: true }],
    });

    const versions = await payerProfileService.getVersionHistory(123);

    expect(versions).toHaveLength(1);
    expect(versions[0].version_number).toBe(4);
  });
});
