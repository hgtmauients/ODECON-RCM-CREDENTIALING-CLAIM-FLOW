/**
 * Code Autocomplete Component
 * Searchable dropdown for ICD-10 and CPT codes with debounced API lookup.
 */

import React, { useState, useEffect, useRef } from 'react';
import { apiService } from '@/services/api';

interface CodeResult {
  code: string;
  description: string;
  category?: string;
  subcategory?: string;
}

interface CodeAutocompleteProps {
  type: 'icd10' | 'cpt';
  value: string;
  onChange: (code: string, description: string) => void;
  placeholder?: string;
  style?: React.CSSProperties;
}

export default function CodeAutocomplete({ type, value, onChange, placeholder, style }: CodeAutocompleteProps) {
  const [query, setQuery] = useState(value || '');
  const [results, setResults] = useState<CodeResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(value || '');
  }, [value]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const search = (q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.length < 1) { setResults([]); setIsOpen(false); return; }

    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const endpoint = type === 'icd10' ? '/rcm/codes/icd10' : '/rcm/codes/cpt';
        const resp = await apiService.get(endpoint, { q, limit: 15 });
        setResults(resp?.data || []);
        setIsOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
  };

  const handleInputChange = (val: string) => {
    setQuery(val);
    if (!val) {
      onChange('', '');
      setResults([]);
      setIsOpen(false);
    } else {
      search(val);
    }
  };

  const handleSelect = (item: CodeResult) => {
    setQuery(item.code);
    onChange(item.code, item.description);
    setIsOpen(false);
  };

  return (
    <div ref={wrapperRef} style={{ position: 'relative', ...style }}>
      <input
        type="text"
        value={query}
        onChange={(e) => handleInputChange(e.target.value)}
        onFocus={() => { if (query.length >= 1) search(query); }}
        placeholder={placeholder || (type === 'icd10' ? 'Search ICD-10...' : 'Search CPT...')}
        style={{
          width: '100%',
          padding: '6px 10px',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          fontSize: 'var(--font-size-sm)',
          background: 'var(--surface-primary)',
          color: 'var(--text-primary)',
        }}
      />
      {loading && (
        <span style={{ position: 'absolute', right: 8, top: 8, width: 12, height: 12, border: '2px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite', display: 'inline-block' }} />
      )}
      {isOpen && results.length > 0 && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          maxHeight: 280,
          overflowY: 'auto',
          background: 'var(--surface-primary)',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 50,
          marginTop: 2,
        }}>
          {results.map((item) => (
            <div
              key={item.code}
              onClick={() => handleSelect(item)}
              style={{
                padding: '8px 12px',
                cursor: 'pointer',
                borderBottom: '1px solid var(--border-light)',
                fontSize: 'var(--font-size-sm)',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-secondary)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              <span style={{ fontWeight: 700, fontFamily: 'monospace', color: 'var(--brand-primary)', marginRight: 8 }}>
                {item.code}
              </span>
              <span style={{ color: 'var(--text-primary)' }}>{item.description}</span>
              {item.category && (
                <span style={{ float: 'right', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
                  {item.category}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
