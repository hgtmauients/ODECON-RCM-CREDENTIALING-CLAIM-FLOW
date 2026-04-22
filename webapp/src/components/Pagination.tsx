/**
 * Reusable pagination control for list pages.
 *
 * Backend convention (B2 fix): list endpoints return { total, limit, offset }.
 * This component drives Prev / Next + a page indicator from those values.
 * The parent owns `offset` state and re-fetches on change.
 */

import React from 'react';

export interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (newOffset: number) => void;
  loading?: boolean;
  /** Optional label describing what is being paginated, e.g. "claim". */
  itemLabel?: string;
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
  loading,
  itemLabel = 'item',
}: PaginationProps) {
  if (total === 0) return null;

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);

  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 'var(--space-3) var(--space-2)',
        marginTop: 'var(--space-3)',
        fontSize: 'var(--font-size-sm)',
        color: 'var(--text-secondary)',
        gap: 'var(--space-3)',
        flexWrap: 'wrap',
      }}
    >
      <div>
        Showing <strong>{start.toLocaleString()}</strong>&ndash;
        <strong>{end.toLocaleString()}</strong> of{' '}
        <strong>{total.toLocaleString()}</strong> {itemLabel}
        {total === 1 ? '' : 's'}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={!hasPrev || loading}
          onClick={() => onChange(Math.max(0, offset - limit))}
          aria-label="Previous page"
        >
          Prev
        </button>
        <span style={{ minWidth: 70, textAlign: 'center' }}>
          Page <strong>{page.toLocaleString()}</strong> of{' '}
          {totalPages.toLocaleString()}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={!hasNext || loading}
          onClick={() => onChange(offset + limit)}
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </div>
  );
}

export default Pagination;
