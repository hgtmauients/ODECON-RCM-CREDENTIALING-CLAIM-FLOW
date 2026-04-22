/**
 * EDI File Manager
 * Manual upload for 835/277 files (fallback/testing)
 * View EDI file history
 */

import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from 'react-query';
import { useNavigate } from 'react-router-dom';
import { apiService } from '@/services/api';
import { formatDate } from '@/utils/formatters';
import toast from 'react-hot-toast';

export default function EDIFileManager() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileType, setFileType] = useState<string>('835');

  // Upload mutation
  const uploadMutation = useMutation(
    async (data: { file: File; fileType: string }) => {
      const formData = new FormData();
      formData.append('file', data.file);
      formData.append('file_type', data.fileType);
      
      return apiService.post('/rcm/edi/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
    },
    {
      onSuccess: (response) => {
        // Backend returns { success, message, data: { id, file_type, filename, status, parse_result: { payments, denials, claims_posted, total_paid } } }
        const data = response?.data || {};
        const parseResult = data.parse_result || {};
        toast.success(`${fileType} uploaded${data.status === 'processed' ? ' and processed' : ''}`);
        if (parseResult.claims_posted) {
          toast.success(`Posted ${parseResult.claims_posted} payment(s)${parseResult.total_paid ? ` ($${parseResult.total_paid.toFixed(2)})` : ''}`);
        }
        const denialCount = (parseResult.denials || []).length;
        if (denialCount) {
          toast.success(`${denialCount} denial(s) extracted`);
        }
        setSelectedFile(null);
        queryClient.invalidateQueries(['edi-files']);
      },
      onError: () => {
        toast.error('Failed to upload file');
      }
    }
  );

  // Fetch EDI files
  const { data: filesData } = useQuery(
    ['edi-files'],
    () => apiService.get('/rcm/edi/files')
  );

  const ediFiles = filesData?.data || [];

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleUpload = () => {
    if (!selectedFile) {
      toast.error('Please select a file first');
      return;
    }

    uploadMutation.mutate({ file: selectedFile, fileType });
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)', padding: 'var(--space-6)' }}>
      <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-xl)',
          padding: 'var(--space-6)',
          marginBottom: 'var(--space-6)'
        }}>
          <h1 style={{
            fontSize: 'var(--font-size-3xl)',
            fontWeight: 700,
            marginBottom: 'var(--space-2)',
            background: 'var(--gradient-primary)',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}>
            EDI File Manager
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-base)' }}>
            Upload and manage EDI transaction files (835, 277CA, 271, 999)
          </p>
        </div>

        {/* Upload Section */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6)',
          marginBottom: 'var(--space-6)'
        }}>
          <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
            Upload EDI File
          </h2>

          <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                File Type
              </label>
              <select
                value={fileType}
                onChange={(e) => setFileType(e.target.value)}
                style={{
                  width: '100%',
                  padding: 'var(--space-3)',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--surface-primary)',
                  color: 'var(--text-primary)',
                  fontSize: 'var(--font-size-sm)'
                }}
              >
                <option value="835">835 - Remittance Advice (Payment/Denial from payer)</option>
                <option value="277CA">277CA - Claim Acknowledgment (Clearinghouse accept/reject)</option>
                <option value="277">277 - Claim Status Response (Payer status update)</option>
                <option value="271">271 - Eligibility Response (Coverage verification result)</option>
                <option value="999">999 - Syntax Acknowledgment (File format validation)</option>
                <option value="837P">837P - Professional Claim (Review outbound claim file)</option>
              </select>
              <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-2)', lineHeight: 1.6 }}>
                {fileType === '835' && 'The 835 contains payment amounts, adjustments, and denial codes (CARC/RARC) per claim line. Upload when you receive remittance files from a payer or clearinghouse. System will auto-post payments and create denial cases.'}
                {fileType === '277CA' && 'The 277CA confirms whether the clearinghouse or payer accepted or rejected your submitted claims at the claim level. Upload after submitting an 837P to see which claims were acknowledged. Claims will be updated to Accepted or Rejected status.'}
                {fileType === '277' && 'The 277 is a response to a 276 claim status inquiry. It provides the current adjudication status of previously submitted claims. Upload to update claim statuses with the latest payer response.'}
                {fileType === '271' && 'The 271 is the response to a 270 eligibility inquiry. It contains patient coverage details, copay, deductible, and benefit information. Upload to review eligibility verification results.'}
                {fileType === '999' && 'The 999 confirms that your submitted file (usually an 837P) was syntactically valid and could be processed. A rejected 999 means the file had formatting errors and needs to be regenerated. This is not a claim-level response.'}
                {fileType === '837P' && 'Upload a previously generated 837P professional claim file to review its contents, validate structure, or re-process. This is typically used for troubleshooting or auditing outbound claims.'}
              </div>
            </div>

            <div style={{ flex: 2 }}>
              <label style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-2)', color: 'var(--text-primary)' }}>
                Select File
              </label>
              <input
                type="file"
                onChange={handleFileSelect}
                accept=".835,.277,.271,.999,.837,.x12,.edi,.txt,.dat"
                style={{
                  width: '100%',
                  padding: 'var(--space-3)',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--surface-primary)',
                  color: 'var(--text-primary)',
                  fontSize: 'var(--font-size-sm)'
                }}
              />
            </div>

            <button
              onClick={handleUpload}
              disabled={!selectedFile || uploadMutation.isLoading}
              style={{
                padding: 'var(--space-3) var(--space-8)',
                background: !selectedFile || uploadMutation.isLoading ? 'var(--surface-secondary)' : 'var(--gradient-primary)',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                color: 'white',
                fontSize: 'var(--font-size-base)',
                fontWeight: 600,
                cursor: !selectedFile || uploadMutation.isLoading ? 'not-allowed' : 'pointer',
                opacity: !selectedFile || uploadMutation.isLoading ? 0.5 : 1,
                whiteSpace: 'nowrap'
              }}
            >
              {uploadMutation.isLoading ? 'Processing...' : 'Upload & Process'}
            </button>
          </div>

          {selectedFile && (
            <div style={{
              marginTop: 'var(--space-3)',
              padding: 'var(--space-3)',
              background: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid #009DDD',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--font-size-sm)',
              color: 'var(--text-primary)'
            }}>
              Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)
            </div>
          )}
        </div>

        {/* EDI Files List */}
        <div style={{
          background: 'var(--surface-glass)',
          backdropFilter: 'var(--glass-blur)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6)'
        }}>
          <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)', color: 'var(--text-primary)' }}>
            EDI File History
          </h2>

          {ediFiles.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: 'var(--space-4)' }}>
              No EDI files uploaded yet
            </p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ borderBottom: '2px solid var(--border-primary)' }}>
                <tr>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    File Type
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Filename
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'center', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Status
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Uploaded
                  </th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {ediFiles.map((file: Record<string, any>) => (
                  <tr key={file.id as string} style={{ borderBottom: '1px solid var(--border-primary)', cursor: 'pointer', transition: 'background var(--transition-fast)' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-secondary)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: 'var(--space-3)', fontFamily: 'monospace', fontWeight: 700, color: 'var(--brand-primary)' }}>
                      {file.file_type as string}
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-primary)' }}>
                      {file.filename as string}
                      {file.transaction_count && (
                        <span style={{ marginLeft: 'var(--space-2)', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
                          ({file.transaction_count as number} transactions)
                        </span>
                      )}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'center' }}>
                      <span style={{
                        padding: 'var(--space-1) var(--space-2)',
                        background: file.status === 'processed' ? 'var(--brand-success)' : file.status === 'error' ? 'var(--brand-error)' : 'var(--brand-warning)',
                        color: 'white',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 'var(--font-size-xs)',
                        fontWeight: 600
                      }}>
                        {(file.status as string || '').toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: 'var(--space-3)', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
                      {formatDate(file.created_at as string)}
                    </td>
                    <td style={{ padding: 'var(--space-3)', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 8 }}>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/edi/${file.id}`);
                          }}
                          title="Inspect raw + parsed segments"
                        >
                          Debug
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              const blob: Blob = await apiService.downloadBlob(`/rcm/edi/files/${file.id}/download`);
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement('a');
                              a.href = url;
                              a.download = (file.filename as string) || 'edi_file';
                              a.click();
                              URL.revokeObjectURL(url);
                            } catch {
                              toast.error('Download failed');
                            }
                          }}
                        >
                          Download
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

