/**
 * EDI Debug Panel.
 *
 * Side-by-side view of the raw EDI bytes and the parsed segments. Used by
 * billing operators to diagnose "why did this 277CA not move my claim",
 * "what CARC codes did the payer send on this 835", or simply confirm a
 * payer\'s ISA/GS envelope matches their spec.
 */

import React, { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from 'react-query';
import { apiService } from '@/services/api';

interface SegmentRow {
  index: number;
  tag: string;
  raw: string;
  elements: string[];
}

interface ParseResp {
  id: number;
  file_type: string;
  filename: string;
  file_size: number;
  status: string;
  error_message: string | null;
  raw: string;
  segments: SegmentRow[];
  summary: Record<string, any>;
}

export default function EdiFileDebug() {
  const navigate = useNavigate();
  const { fileId } = useParams<{ fileId: string }>();
  const [tagFilter, setTagFilter] = useState('');

  const { data, isLoading, error } = useQuery(
    ['edi-debug', fileId],
    () => apiService.get(`/rcm/edi/files/${fileId}/parsed`),
    { enabled: !!fileId },
  );

  const parsed: ParseResp | null = data?.data || null;
  const segments = useMemo(() => {
    if (!parsed) return [];
    if (!tagFilter.trim()) return parsed.segments;
    const t = tagFilter.trim().toUpperCase();
    return parsed.segments.filter((s) => s.tag.startsWith(t));
  }, [parsed, tagFilter]);

  const segmentCounts = useMemo(() => {
    if (!parsed) return [] as { tag: string; count: number }[];
    const counts: Record<string, number> = {};
    parsed.segments.forEach((s) => { counts[s.tag] = (counts[s.tag] || 0) + 1; });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([tag, count]) => ({ tag, count }));
  }, [parsed]);

  if (isLoading) {
    return (
      <div style={{ padding: 'var(--space-12)', textAlign: 'center' }}>
        <div style={{ width: 24, height: 24, margin: '0 auto', border: '3px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
      </div>
    );
  }
  if (error || !parsed) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
        <p style={{ color: 'var(--brand-error)', fontWeight: 600 }}>Failed to load EDI file</p>
        <button className="btn btn-ghost" onClick={() => navigate('/edi')} style={{ marginTop: 'var(--space-4)' }}>Back to EDI Files</button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-6)', gap: 'var(--space-4)' }}>
        <div>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/edi')} style={{ marginBottom: 'var(--space-2)' }}>
            ← Back to EDI Files
          </button>
          <h1 className="page-title" style={{ marginBottom: 4 }}>{parsed.filename}</h1>
          <p className="page-subtitle">
            {parsed.file_type} · {parsed.file_size.toLocaleString()} bytes · status&nbsp;
            <span style={{
              padding: '2px 8px',
              borderRadius: 'var(--radius-sm)',
              background: parsed.status === 'processed' ? 'var(--brand-success)' : parsed.status === 'error' ? 'var(--brand-error)' : 'var(--text-tertiary)',
              color: 'white',
              fontSize: 'var(--font-size-xs)',
              fontWeight: 600,
            }}>{parsed.status.toUpperCase()}</span>
          </p>
          {parsed.error_message && (
            <p style={{ color: 'var(--brand-error)', fontSize: 'var(--font-size-sm)', marginTop: 'var(--space-2)' }}>
              {parsed.error_message}
            </p>
          )}
        </div>
      </div>

      {/* Summary panel — file-type specific */}
      {Object.keys(parsed.summary).length > 0 && (
        <div className="card" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: 'var(--space-3)' }}>Summary</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 'var(--space-3)' }}>
            {Object.entries(parsed.summary)
              .filter(([k]) => !['payments', 'denials', 'parse_error'].includes(k))
              .map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    {k.replace(/_/g, ' ')}
                  </div>
                  <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700 }}>
                    {typeof v === 'number' ? v.toLocaleString() : String(v)}
                  </div>
                </div>
              ))}
          </div>
          {parsed.summary.parse_error && (
            <p style={{ color: 'var(--brand-error)', marginTop: 'var(--space-3)', fontSize: 'var(--font-size-sm)' }}>
              Parse error: <code>{parsed.summary.parse_error}</code>
            </p>
          )}
          {Array.isArray(parsed.summary.denials) && parsed.summary.denials.length > 0 && (
            <details style={{ marginTop: 'var(--space-3)' }}>
              <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{parsed.summary.denials.length} denial(s)</summary>
              <pre style={preStyle}>{JSON.stringify(parsed.summary.denials, null, 2)}</pre>
            </details>
          )}
          {Array.isArray(parsed.summary.payments) && parsed.summary.payments.length > 0 && (
            <details style={{ marginTop: 'var(--space-3)' }}>
              <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{parsed.summary.payments.length} payment(s)</summary>
              <pre style={preStyle}>{JSON.stringify(parsed.summary.payments, null, 2)}</pre>
            </details>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
        {/* Parsed segments */}
        <div className="card" style={{ padding: 'var(--space-4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
            <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, margin: 0 }}>Segments</h2>
            <input
              className="input"
              placeholder="Filter by tag (e.g. CLP, STC)"
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              style={{ maxWidth: 220 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 'var(--space-3)' }}>
            {segmentCounts.slice(0, 12).map(({ tag, count }) => (
              <button
                key={tag}
                onClick={() => setTagFilter(tag === tagFilter.toUpperCase() ? '' : tag)}
                style={{
                  padding: '2px 8px',
                  fontSize: 'var(--font-size-xs)',
                  fontFamily: 'monospace',
                  border: '1px solid var(--border-light)',
                  borderRadius: 'var(--radius-sm)',
                  background: tag === tagFilter.toUpperCase() ? 'var(--brand-primary)' : 'transparent',
                  color: tag === tagFilter.toUpperCase() ? 'white' : 'var(--text-primary)',
                  cursor: 'pointer',
                }}
              >
                {tag} <span style={{ opacity: 0.6 }}>{count}</span>
              </button>
            ))}
          </div>
          <div style={{ maxHeight: 600, overflowY: 'auto', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)' }}>
            {segments.length === 0 ? (
              <p style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
                No segments match the filter.
              </p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-size-xs)' }}>
                <thead style={{ background: 'var(--surface-secondary)', position: 'sticky', top: 0 }}>
                  <tr>
                    <th style={segmentTh}>#</th>
                    <th style={segmentTh}>Tag</th>
                    <th style={segmentTh}>Elements</th>
                  </tr>
                </thead>
                <tbody>
                  {segments.map((s) => (
                    <tr key={s.index} style={{ borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: 6, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>{s.index}</td>
                      <td style={{ padding: 6, fontFamily: 'monospace', fontWeight: 700 }}>{s.tag}</td>
                      <td style={{ padding: 6, fontFamily: 'monospace' }}>
                        {s.elements.map((e, i) => (
                          <span key={i} style={{ marginRight: 6, padding: '0 4px', background: 'var(--surface-secondary)', borderRadius: 2 }}>
                            <span style={{ color: 'var(--text-tertiary)' }}>[{i + 1}]</span>&nbsp;{e || <em style={{ color: 'var(--text-tertiary)' }}>—</em>}
                          </span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Raw bytes */}
        <div className="card" style={{ padding: 'var(--space-4)' }}>
          <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: 'var(--space-3)' }}>Raw</h2>
          <pre style={{ ...preStyle, maxHeight: 670 }}>{parsed.raw}</pre>
        </div>
      </div>
    </div>
  );
}

const preStyle: React.CSSProperties = {
  margin: 0,
  padding: 'var(--space-3)',
  background: 'var(--surface-secondary)',
  border: '1px solid var(--border-light)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--font-size-xs)',
  fontFamily: 'monospace',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  overflowY: 'auto',
};

const segmentTh: React.CSSProperties = {
  padding: '6px 8px',
  textAlign: 'left',
  fontSize: 'var(--font-size-xs)',
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};
