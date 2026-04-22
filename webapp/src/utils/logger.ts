/**
 * ClaimFlow - Logger utility
 */

export const logger = {
  info: (...args: any[]) => console.log('[ClaimFlow]', ...args),
  warn: (...args: any[]) => console.warn('[ClaimFlow]', ...args),
  error: (...args: any[]) => console.error('[ClaimFlow]', ...args),
  debug: (...args: any[]) => {
    if (import.meta.env?.DEV) {
      console.debug('[ClaimFlow]', ...args);
    }
  },
};

export default logger;
