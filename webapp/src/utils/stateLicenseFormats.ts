/**
 * ClaimFlow - US State Medical License Format Reference
 * Each state has unique license number formats, prefixes, and renewal cycles.
 * Used for input validation, formatting hints, and expiration estimation.
 */

export interface StateLicenseFormat {
  state: string;
  name: string;
  board: string;
  format: string;           // Human-readable format description
  pattern: RegExp;          // Validation regex
  placeholder: string;      // Input placeholder
  renewalYears: number;     // Typical renewal cycle in years
  renewalNote: string;      // Special renewal rules
}

export const STATE_LICENSE_FORMATS: Record<string, StateLicenseFormat> = {
  AL: { state: 'AL', name: 'Alabama', board: 'Alabama Board of Medical Examiners', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 1, renewalNote: 'Annual, expires Dec 31' },
  AK: { state: 'AK', name: 'Alaska', board: 'Alaska State Medical Board', format: 'Numeric, typically 4-6 digits', pattern: /^\d{4,6}$/, placeholder: '123456', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  AZ: { state: 'AZ', name: 'Arizona', board: 'Arizona Medical Board', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  AR: { state: 'AR', name: 'Arkansas', board: 'Arkansas State Medical Board', format: 'Numeric, typically 5-6 digits', pattern: /^\d{4,7}$/, placeholder: '123456', renewalYears: 1, renewalNote: 'Annual, expires Jan 31' },
  CA: { state: 'CA', name: 'California', board: 'Medical Board of California', format: 'Letter prefix + digits (A/G/C + 5-6 digits)', pattern: /^[AGC]?\d{4,6}$/, placeholder: 'A12345', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  CO: { state: 'CO', name: 'Colorado', board: 'Colorado Medical Board', format: 'Numeric with DR prefix', pattern: /^(DR)?\d{4,7}$/, placeholder: 'DR.0012345', renewalYears: 2, renewalNote: 'Biennial, varies' },
  CT: { state: 'CT', name: 'Connecticut', board: 'CT Dept of Public Health', format: 'Numeric, typically 6 digits', pattern: /^\d{5,7}$/, placeholder: '012345', renewalYears: 1, renewalNote: 'Annual, birthday' },
  DE: { state: 'DE', name: 'Delaware', board: 'Delaware Board of Medical Licensure', format: 'Numeric, typically 4-5 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 2, renewalNote: 'Biennial, odd/even years' },
  DC: { state: 'DC', name: 'District of Columbia', board: 'DC Board of Medicine', format: 'MD + digits', pattern: /^(MD)?\d{4,7}$/, placeholder: 'MD12345', renewalYears: 2, renewalNote: 'Biennial, Dec 31' },
  FL: { state: 'FL', name: 'Florida', board: 'Florida Board of Medicine', format: 'ME + digits (e.g. ME12345)', pattern: /^ME\d{4,6}$/, placeholder: 'ME12345', renewalYears: 2, renewalNote: 'Biennial, birth month (odd/even)' },
  GA: { state: 'GA', name: 'Georgia', board: 'Georgia Composite Medical Board', format: 'Numeric, typically 6 digits', pattern: /^\d{4,7}$/, placeholder: '012345', renewalYears: 2, renewalNote: 'Biennial, even years' },
  HI: { state: 'HI', name: 'Hawaii', board: 'Hawaii Medical Board (DCCA)', format: 'MD- prefix + digits (e.g. MD-12345)', pattern: /^MD-?\d{4,6}$/, placeholder: 'MD-21277', renewalYears: 2, renewalNote: 'Biennial, odd years for MD' },
  ID: { state: 'ID', name: 'Idaho', board: 'Idaho Board of Medicine', format: 'M- prefix + digits', pattern: /^M-?\d{3,6}$/, placeholder: 'M-1234', renewalYears: 1, renewalNote: 'Annual, June 30' },
  IL: { state: 'IL', name: 'Illinois', board: 'Illinois DFPR', format: '036. prefix + 6 digits', pattern: /^036\.?\d{6}$/, placeholder: '036.012345', renewalYears: 3, renewalNote: 'Triennial, varies' },
  IN: { state: 'IN', name: 'Indiana', board: 'Indiana Medical Licensing Board', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, odd years Nov 1' },
  IA: { state: 'IA', name: 'Iowa', board: 'Iowa Board of Medicine', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  KS: { state: 'KS', name: 'Kansas', board: 'Kansas Board of Healing Arts', format: 'Numeric 04- prefix', pattern: /^(04-)?\d{4,6}$/, placeholder: '04-12345', renewalYears: 1, renewalNote: 'Annual, July 1' },
  KY: { state: 'KY', name: 'Kentucky', board: 'Kentucky Board of Medical Licensure', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 1, renewalNote: 'Annual, Oct 31' },
  LA: { state: 'LA', name: 'Louisiana', board: 'Louisiana State Board of Medical Examiners', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 1, renewalNote: 'Annual, Jan 31' },
  ME: { state: 'ME', name: 'Maine', board: 'Maine Board of Licensure in Medicine', format: 'Numeric, typically 4-5 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 2, renewalNote: 'Biennial, birthday' },
  MD: { state: 'MD', name: 'Maryland', board: 'Maryland Board of Physicians', format: 'D + 5 digits', pattern: /^D\d{5}$/, placeholder: 'D12345', renewalYears: 2, renewalNote: 'Biennial, Sep 30' },
  MA: { state: 'MA', name: 'Massachusetts', board: 'MA Board of Registration in Medicine', format: 'Numeric, typically 6 digits', pattern: /^\d{4,7}$/, placeholder: '123456', renewalYears: 2, renewalNote: 'Biennial, birth year' },
  MI: { state: 'MI', name: 'Michigan', board: 'Michigan LARA', format: '43-01- prefix + digits', pattern: /^(43-01-)?\d{4,8}$/, placeholder: '43-01-012345', renewalYears: 3, renewalNote: 'Triennial, varies' },
  MN: { state: 'MN', name: 'Minnesota', board: 'Minnesota Board of Medical Practice', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 1, renewalNote: 'Annual, birthday' },
  MS: { state: 'MS', name: 'Mississippi', board: 'Mississippi State Board of Medical Licensure', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, June 30' },
  MO: { state: 'MO', name: 'Missouri', board: 'Missouri Board of Registration', format: 'Numeric, typically 6-7 digits', pattern: /^\d{4,8}$/, placeholder: '2012345', renewalYears: 2, renewalNote: 'Biennial, odd/even years' },
  MT: { state: 'MT', name: 'Montana', board: 'Montana Board of Medical Examiners', format: 'Numeric, typically 4 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 2, renewalNote: 'Biennial, birthday' },
  NE: { state: 'NE', name: 'Nebraska', board: 'Nebraska DHHS', format: 'Numeric, typically 5 digits', pattern: /^\d{4,7}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, Oct 1' },
  NV: { state: 'NV', name: 'Nevada', board: 'Nevada State Board of Medical Examiners', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  NH: { state: 'NH', name: 'New Hampshire', board: 'NH Board of Medicine', format: 'Numeric, typically 4-5 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 2, renewalNote: 'Biennial, June 30' },
  NJ: { state: 'NJ', name: 'New Jersey', board: 'NJ State Board of Medical Examiners', format: '25MA + digits', pattern: /^(25MA)?\d{4,8}$/, placeholder: '25MA01234500', renewalYears: 2, renewalNote: 'Biennial, July 1' },
  NM: { state: 'NM', name: 'New Mexico', board: 'NM Medical Board', format: 'MD- prefix + digits', pattern: /^(MD-?)?\d{4,6}$/, placeholder: 'MD-1234', renewalYears: 3, renewalNote: 'Triennial, varies' },
  NY: { state: 'NY', name: 'New York', board: 'NY State Education Dept', format: 'Numeric, 6 digits', pattern: /^\d{6}$/, placeholder: '123456', renewalYears: 2, renewalNote: 'Registration triennial, birth month' },
  NC: { state: 'NC', name: 'North Carolina', board: 'NC Medical Board', format: 'Numeric, typically 5-6 digits', pattern: /^\d{4,7}$/, placeholder: '012345', renewalYears: 1, renewalNote: 'Annual, Oct 31' },
  ND: { state: 'ND', name: 'North Dakota', board: 'ND Board of Medicine', format: 'Numeric, typically 4 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  OH: { state: 'OH', name: 'Ohio', board: 'State Medical Board of Ohio', format: 'Numeric, 2-year + seq (e.g. 35.012345)', pattern: /^(\d{2}\.)?\d{4,8}$/, placeholder: '35.012345', renewalYears: 2, renewalNote: 'Biennial, varies' },
  OK: { state: 'OK', name: 'Oklahoma', board: 'Oklahoma Board of Medical Licensure', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 1, renewalNote: 'Annual, Jan 31' },
  OR: { state: 'OR', name: 'Oregon', board: 'Oregon Medical Board', format: 'MD + digits', pattern: /^(MD)?\d{4,6}$/, placeholder: 'MD12345', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  PA: { state: 'PA', name: 'Pennsylvania', board: 'PA State Board of Medicine', format: 'MD- prefix + 6 digits', pattern: /^(MD-?)?\d{4,7}$/, placeholder: 'MD-012345', renewalYears: 2, renewalNote: 'Biennial, Dec 31 even years' },
  RI: { state: 'RI', name: 'Rhode Island', board: 'RI Board of Medical Licensure', format: 'MD + digits', pattern: /^(MD)?\d{4,6}$/, placeholder: 'MD12345', renewalYears: 2, renewalNote: 'Biennial, July 1' },
  SC: { state: 'SC', name: 'South Carolina', board: 'SC Board of Medical Examiners', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, April 30 even years' },
  SD: { state: 'SD', name: 'South Dakota', board: 'SD Board of Medical and Osteopathic Examiners', format: 'Numeric, typically 4 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 1, renewalNote: 'Annual, June 30' },
  TN: { state: 'TN', name: 'Tennessee', board: 'TN Board of Medical Examiners', format: 'MD- prefix + digits', pattern: /^(MD-?)?\d{4,6}$/, placeholder: 'MD-12345', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  TX: { state: 'TX', name: 'Texas', board: 'Texas Medical Board', format: 'Letter prefix + digits (J/K/L/M + 4-5 digits)', pattern: /^[A-Z]?\d{4,6}$/, placeholder: 'M1234', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  UT: { state: 'UT', name: 'Utah', board: 'Utah DOPL', format: 'Numeric, typically 7 digits', pattern: /^\d{5,8}$/, placeholder: '1234567', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  VT: { state: 'VT', name: 'Vermont', board: 'Vermont Board of Medical Practice', format: 'Numeric, typically 4 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 2, renewalNote: 'Biennial, birthday' },
  VA: { state: 'VA', name: 'Virginia', board: 'Virginia Board of Medicine', format: 'Numeric 0101- prefix', pattern: /^(0101-)?\d{4,8}$/, placeholder: '0101-012345', renewalYears: 2, renewalNote: 'Biennial, birth month' },
  WA: { state: 'WA', name: 'Washington', board: 'WA Medical Commission', format: 'MD + 8 digits', pattern: /^(MD)?\d{5,9}$/, placeholder: 'MD00012345', renewalYears: 2, renewalNote: 'Biennial, birthday' },
  WV: { state: 'WV', name: 'West Virginia', board: 'WV Board of Medicine', format: 'Numeric, typically 5 digits', pattern: /^\d{4,6}$/, placeholder: '12345', renewalYears: 2, renewalNote: 'Biennial, June 30' },
  WI: { state: 'WI', name: 'Wisconsin', board: 'WI DSPS', format: 'Numeric, typically 6 digits', pattern: /^\d{4,7}$/, placeholder: '012345', renewalYears: 2, renewalNote: 'Biennial, Oct 31 even years' },
  WY: { state: 'WY', name: 'Wyoming', board: 'WY Board of Medicine', format: 'Numeric, typically 4 digits', pattern: /^\d{3,6}$/, placeholder: '1234', renewalYears: 2, renewalNote: 'Biennial, Jan 1' },
};

export function getStateLicenseFormat(state: string): StateLicenseFormat | null {
  return STATE_LICENSE_FORMATS[state.toUpperCase()] || null;
}

export function validateLicenseNumber(state: string, licenseNumber: string): { valid: boolean; message: string } {
  const fmt = getStateLicenseFormat(state);
  if (!fmt) return { valid: true, message: '' };
  if (!licenseNumber) return { valid: false, message: 'License number required' };
  if (fmt.pattern.test(licenseNumber.replace(/\s/g, ''))) {
    return { valid: true, message: '' };
  }
  return { valid: false, message: `Expected format for ${fmt.name}: ${fmt.format} (e.g. ${fmt.placeholder})` };
}
