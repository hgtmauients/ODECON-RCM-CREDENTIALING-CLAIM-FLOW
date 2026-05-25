import { describe, expect, it } from 'vitest';

import { getSafeInternalPath } from '../safeNavigation';

describe('getSafeInternalPath', () => {
  it('accepts in-app routes in allowed prefixes', () => {
    expect(getSafeInternalPath('/claims/123')).toBe('/claims/123');
    expect(getSafeInternalPath('/claims?state=draft')).toBe('/claims?state=draft');
    expect(getSafeInternalPath('/dashboard')).toBe('/dashboard');
  });

  it('rejects unsafe or out-of-scope paths', () => {
    expect(getSafeInternalPath('https://evil.example')).toBeNull();
    expect(getSafeInternalPath('//evil.example')).toBeNull();
    expect(getSafeInternalPath('/javascript:alert(1)')).toBeNull();
    expect(getSafeInternalPath('/unknown-area/path')).toBeNull();
  });
});
