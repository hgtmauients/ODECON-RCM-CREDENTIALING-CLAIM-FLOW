/**
 * Global search bar.
 *
 * Sits in the sidebar; expands into a dropdown of typed hits as the user
 * types. Cmd/Ctrl-K focuses it from anywhere. Keyboard navigation: ↑ / ↓
 * walk the list, Enter opens the selected hit, Esc closes the dropdown.
 */

import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from 'react-query';
import { apiService } from '@/services/api';

interface Hit {
  type: 'claim' | 'provider' | 'payer' | 'denial';
  id: string;
  title: string;
  subtitle?: string;
  link: string;
  extra?: Record<string, any>;
}

interface SearchResp {
  query: string;
  claims: Hit[];
  providers: Hit[];
  payers: Hit[];
  denials: Hit[];
  total: number;
}

const TYPE_LABEL: Record<Hit['type'], string> = {
  claim: 'Claim',
  provider: 'Provider',
  payer: 'Payer',
  denial: 'Denial',
};

const TYPE_COLOR: Record<Hit['type'], string> = {
  claim: 'var(--brand-primary)',
  provider: 'var(--brand-success)',
  payer: '#8b5cf6',
  denial: 'var(--brand-error)',
};

function useDebounced<T>(value: T, delay: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return v;
}

export default function GlobalSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const debounced = useDebounced(query, 200);
  const inputRef = useRef<HTMLInputElement>(null);

  // cmd-K / ctrl-K to focus the search box from anywhere
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const { data, isFetching } = useQuery(
    ['global-search', debounced],
    () => apiService.get('/search', { q: debounced }),
    {
      enabled: debounced.trim().length >= 2,
      keepPreviousData: true,
      staleTime: 15_000,
    },
  );

  const resp: SearchResp | null = data?.data || null;
  const hits: Hit[] = resp
    ? [...resp.claims, ...resp.providers, ...resp.payers, ...resp.denials]
    : [];

  // Reset highlight whenever the result list changes
  useEffect(() => { setActiveIdx(0); }, [debounced]);

  const goto = (h: Hit) => {
    setOpen(false);
    setQuery('');
    navigate(h.link);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || hits.length === 0) {
      if (e.key === 'Escape') (e.target as HTMLInputElement).blur();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(hits.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      goto(hits[activeIdx]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div style={{ position: 'relative' }}>
      <input
        ref={inputRef}
        value={query}
        placeholder="Search… (Ctrl/⌘ K)"
        aria-label="Global search"
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(query.trim().length >= 2)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        style={{
          width: '100%',
          padding: '6px 10px',
          fontSize: 13,
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 'var(--radius-md)',
          color: '#e2e8f0',
        }}
      />
      {open && debounced.trim().length >= 2 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 6,
            background: 'var(--surface-primary)',
            border: '1px solid var(--border-primary)',
            borderRadius: 'var(--radius-md)',
            boxShadow: '0 10px 30px rgba(0,0,0,0.18)',
            maxHeight: 480,
            overflowY: 'auto',
            zIndex: 220,
            color: 'var(--text-primary)',
          }}
        >
          {isFetching && hits.length === 0 ? (
            <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
              Searching…
            </div>
          ) : hits.length === 0 ? (
            <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
              No matches.
            </div>
          ) : (
            hits.map((h, idx) => (
              <button
                key={`${h.type}:${h.id}`}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => goto(h)}
                onMouseEnter={() => setActiveIdx(idx)}
                style={{
                  display: 'flex',
                  width: '100%',
                  textAlign: 'left',
                  padding: 'var(--space-2) var(--space-3)',
                  background: idx === activeIdx ? 'var(--surface-secondary)' : 'transparent',
                  border: 'none',
                  borderBottom: '1px solid var(--border-light)',
                  cursor: 'pointer',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span style={{
                  flex: '0 0 auto',
                  fontSize: 'var(--font-size-xs)',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  padding: '2px 6px',
                  borderRadius: 'var(--radius-sm)',
                  background: TYPE_COLOR[h.type],
                  color: 'white',
                }}>
                  {TYPE_LABEL[h.type]}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {h.title}
                  </div>
                  {h.subtitle && (
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {h.subtitle}
                    </div>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
