/**
 * ClaimFlow - Icon service
 * Renders CSS spinners for loading states.
 * All other icon references render as invisible (no stray letters).
 * Replace with a real icon library (lucide-react, heroicons) when ready.
 */

import React from 'react';

interface IconProps {
  name?: string;
  icon?: string;
  className?: string;
  size?: number | string;
  style?: React.CSSProperties;
  spin?: boolean;
}

const SIZE_MAP: Record<string, number> = {
  xs: 12, sm: 14, md: 16, lg: 20, xl: 24, '2xl': 32, '3xl': 40, '4xl': 48,
};

export const PremiumIcon: React.FC<IconProps> = ({ name, icon, className, size = 16, style, spin }) => {
  const iconName = name || icon || '';
  const numericSize = typeof size === 'number' ? size : (SIZE_MAP[size] || 16);

  // Spinner: CSS animated circle
  if (iconName === 'spinner' || spin) {
    return React.createElement('span', {
      className,
      style: {
        display: 'inline-block',
        width: numericSize,
        height: numericSize,
        border: '2px solid var(--border-light, #e2e8f0)',
        borderTopColor: 'var(--brand-primary, #2563eb)',
        borderRadius: '50%',
        animation: 'spin 0.6s linear infinite',
        ...style,
      },
    });
  }

  // Everything else: hidden (no stray letters)
  return React.createElement('span', {
    className,
    style: { display: 'none', ...style },
    'aria-hidden': true,
  });
};

export default PremiumIcon;
