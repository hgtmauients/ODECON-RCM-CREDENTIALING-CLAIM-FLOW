const DEFAULT_ALLOWED_PREFIXES = [
  '/claims',
  '/denials',
  '/providers',
  '/credentialing',
  '/payer-enrollment',
  '/admin',
  '/dashboard',
  '/settings',
];

export function getSafeInternalPath(
  path: string | null | undefined,
  allowedPrefixes: string[] = DEFAULT_ALLOWED_PREFIXES,
): string | null {
  if (!path) return null;
  const trimmed = path.trim();
  if (!trimmed.startsWith('/')) return null;
  if (trimmed.startsWith('//')) return null;
  if (trimmed.toLowerCase().startsWith('/javascript:')) return null;
  if (!allowedPrefixes.some((prefix) => trimmed === prefix || trimmed.startsWith(`${prefix}/`) || trimmed.startsWith(`${prefix}?`))) {
    return null;
  }
  return trimmed;
}
