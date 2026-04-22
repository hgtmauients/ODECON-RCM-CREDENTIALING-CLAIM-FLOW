/**
 * Patient Management Page
 * List, search, create, edit patients used in claim creation.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import { formatDate } from '@/utils/formatters';
import toast from 'react-hot-toast';

interface Patient {
  id: number;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender: string;
  member_id: string;
  payer_id?: number;
  city: string;
  state: string;
  phone?: string;
  email?: string;
  address_line_1?: string;
  zip_code?: string;
  group_number?: string;
}

const EMPTY_FORM = { first_name: '', last_name: '', date_of_birth: '', gender: 'M', address_line_1: '', city: '', state: '', zip_code: '', phone: '', email: '', member_id: '', group_number: '', payer_id: '' };

export default function PatientManagement() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const { data, isLoading, error } = useQuery(['patients', search], () =>
    apiService.get('/rcm/patients', search ? { search } : undefined)
  );
  const patients: Patient[] = data?.data || [];

  const { data: payersData } = useQuery('payers-list', () => apiService.get('/rcm/payers'));
  const payers: Array<{ id: number; name: string }> = payersData?.data || [];

  const saveMutation = useMutation(
    (data: Record<string, any>) => editingId
      ? apiService.put(`/rcm/patients/${editingId}`, data)
      : apiService.post('/rcm/patients', data),
    {
      onSuccess: () => {
        toast.success(editingId ? 'Patient updated' : 'Patient created');
        queryClient.invalidateQueries(['patients']);
        resetForm();
      },
      onError: () => { toast.error('Failed to save patient'); },
    }
  );

  const resetForm = () => { setShowForm(false); setEditingId(null); setForm(EMPTY_FORM); };

  const startEdit = (p: Patient) => {
    setForm({
      first_name: p.first_name, last_name: p.last_name, date_of_birth: p.date_of_birth || '',
      gender: p.gender, address_line_1: p.address_line_1 || '', city: p.city || '', state: p.state || '',
      zip_code: p.zip_code || '', phone: p.phone || '', email: p.email || '',
      member_id: p.member_id, group_number: p.group_number || '', payer_id: p.payer_id ? String(p.payer_id) : '',
    });
    setEditingId(p.id);
    setShowForm(true);
  };

  const handleSave = () => {
    if (!form.first_name || !form.last_name || !form.date_of_birth || !form.member_id) {
      toast.error('First name, last name, DOB, and member ID are required'); return;
    }
    saveMutation.mutate({ ...form, payer_id: form.payer_id ? parseInt(form.payer_id) : null });
  };

  const inputStyle: React.CSSProperties = { width: '100%', padding: '8px 12px', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-sm)' };
  const labelStyle: React.CSSProperties = { display: 'block', fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.04em' };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-6)' }}>
        <div>
          <h1 className="page-title">Patients</h1>
          <p className="page-subtitle">Manage patient demographics for claim creation</p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={() => { resetForm(); setShowForm(true); }}>+ New Patient</button>
      </div>

      <div className="card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
        <input className="input" placeholder="Search by name or member ID..." value={search} onChange={e => setSearch(e.target.value)} style={{ maxWidth: 400 }} />
        <span style={{ marginLeft: 'var(--space-3)', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>{patients.length} patient{patients.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Name</th><th>DOB</th><th>Gender</th><th>Member ID</th><th>City, State</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} style={{ textAlign: 'center', padding: 'var(--space-6)' }}>Loading...</td></tr>
            ) : error ? (
              <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--brand-error)' }}>Failed to load patients</td></tr>
            ) : patients.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: 'center', padding: 'var(--space-6)', color: 'var(--text-secondary)' }}>No patients yet. Click "+ New Patient" to add one.</td></tr>
            ) : patients.map(p => (
              <tr key={p.id}>
                <td style={{ fontWeight: 600 }}>{p.last_name}, {p.first_name}</td>
                <td>{formatDate(p.date_of_birth)}</td>
                <td>{p.gender}</td>
                <td><span className="mono">{p.member_id}</span></td>
                <td>{p.city}{p.state ? `, ${p.state}` : ''}</td>
                <td><button className="btn btn-ghost btn-sm" onClick={() => startEdit(p)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: 40, zIndex: 100, overflowY: 'auto' }} onClick={resetForm}>
          <div style={{ background: 'var(--surface-primary)', borderRadius: 'var(--radius-xl)', padding: 'var(--space-6)', width: 560, marginBottom: 40 }} onClick={e => e.stopPropagation()}>
            <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)' }}>{editingId ? 'Edit Patient' : 'New Patient'}</h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
              <div><label style={labelStyle}>First Name *</label><input style={inputStyle} value={form.first_name} onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} /></div>
              <div><label style={labelStyle}>Last Name *</label><input style={inputStyle} value={form.last_name} onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} /></div>
              <div><label style={labelStyle}>Date of Birth *</label><input type="date" style={inputStyle} value={form.date_of_birth} onChange={e => setForm(f => ({ ...f, date_of_birth: e.target.value }))} /></div>
              <div><label style={labelStyle}>Gender *</label>
                <select style={inputStyle} value={form.gender} onChange={e => setForm(f => ({ ...f, gender: e.target.value }))}>
                  <option value="M">Male</option><option value="F">Female</option><option value="U">Unknown</option>
                </select>
              </div>
              <div><label style={labelStyle}>Member ID *</label><input style={inputStyle} value={form.member_id} onChange={e => setForm(f => ({ ...f, member_id: e.target.value }))} placeholder="Insurance member ID" /></div>
              <div><label style={labelStyle}>Group Number</label><input style={inputStyle} value={form.group_number} onChange={e => setForm(f => ({ ...f, group_number: e.target.value }))} /></div>
              <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>Payer</label>
                <select style={inputStyle} value={form.payer_id} onChange={e => setForm(f => ({ ...f, payer_id: e.target.value }))}>
                  <option value="">Select payer...</option>
                  {payers.map(p => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
                </select>
              </div>
              <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>Address</label><input style={inputStyle} value={form.address_line_1} onChange={e => setForm(f => ({ ...f, address_line_1: e.target.value }))} /></div>
              <div><label style={labelStyle}>City</label><input style={inputStyle} value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} /></div>
              <div><label style={labelStyle}>State</label><input style={inputStyle} value={form.state} onChange={e => setForm(f => ({ ...f, state: e.target.value }))} maxLength={2} /></div>
              <div><label style={labelStyle}>ZIP</label><input style={inputStyle} value={form.zip_code} onChange={e => setForm(f => ({ ...f, zip_code: e.target.value }))} /></div>
              <div><label style={labelStyle}>Phone</label><input style={inputStyle} value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} /></div>
              <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>Email</label><input type="email" style={inputStyle} value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} /></div>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'flex-end', marginTop: 'var(--space-4)' }}>
              <button className="btn btn-ghost" onClick={resetForm}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saveMutation.isLoading}>{saveMutation.isLoading ? 'Saving...' : editingId ? 'Save Changes' : 'Create Patient'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
