/**
 * Admin → Users
 *
 * Lists tenant users, lets admins create + edit + reset-password + deactivate.
 * Shows the role catalog as multi-select chips (admin / billing / credentialing
 * / readonly; super_admin gated on the caller already being super_admin).
 */

import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from 'react-query';
import { apiService } from '@/services/api';
import { useAuth } from '@/auth/AuthProvider';
import { Pagination } from '@/components/Pagination';
import toast from 'react-hot-toast';

const PAGE_SIZE = 50;

interface UserRow {
  id: string;
  email: string;
  full_name: string | null;
  roles: string[];
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

interface RoleMeta {
  name: string;
  expands_to: string[];
}

const SELECTABLE_ROLES_BASE = ['readonly', 'billing', 'credentialing', 'admin'];

export default function Users() {
  const { user: me } = useAuth();
  const meIsSuperAdmin = (me?.roles || []).includes('super_admin');
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('active');
  const [offset, setOffset] = useState(0);
  React.useEffect(() => { setOffset(0); }, [search, activeFilter]);

  const usersQuery = useQuery(
    ['admin-users', search, activeFilter, offset],
    () => {
      const params: Record<string, string | number | boolean | undefined> = {
        limit: PAGE_SIZE,
        offset,
      };
      if (search) params.search = search;
      if (activeFilter === 'active') params.is_active = true;
      if (activeFilter === 'inactive') params.is_active = false;
      return apiService.get('/admin/users', params);
    },
    { keepPreviousData: true },
  );

  const rolesQuery = useQuery('admin-users-roles', () => apiService.get('/admin/users/_meta/roles'));

  const roleCatalog: RoleMeta[] = rolesQuery.data?.data || [];
  const selectableRoles = meIsSuperAdmin
    ? [...SELECTABLE_ROLES_BASE, 'super_admin']
    : SELECTABLE_ROLES_BASE;

  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [resetting, setResetting] = useState<UserRow | null>(null);

  const createMutation = useMutation(
    (payload: any) => apiService.post('/admin/users', payload),
    {
      onSuccess: () => {
        toast.success('User created');
        setShowCreate(false);
        queryClient.invalidateQueries(['admin-users']);
      },
      onError: (e: any) => { toast.error(e?.message || 'Failed to create user'); },
    },
  );

  const updateMutation = useMutation(
    ({ id, payload }: { id: string; payload: any }) => apiService.put(`/admin/users/${id}`, payload),
    {
      onSuccess: () => {
        toast.success('User updated');
        setEditing(null);
        queryClient.invalidateQueries(['admin-users']);
      },
      onError: (e: any) => { toast.error(e?.message || 'Failed to update user'); },
    },
  );

  const resetMutation = useMutation(
    ({ id, password }: { id: string; password: string }) =>
      apiService.post(`/admin/users/${id}/reset-password`, { new_password: password }),
    {
      onSuccess: () => {
        toast.success('Password reset');
        setResetting(null);
      },
      onError: (e: any) => { toast.error(e?.message || 'Failed to reset password'); },
    },
  );

  const deactivateMutation = useMutation(
    (id: string) => apiService.delete(`/admin/users/${id}`),
    {
      onSuccess: () => {
        toast.success('User deactivated');
        queryClient.invalidateQueries(['admin-users']);
      },
      onError: (e: any) => { toast.error(e?.message || 'Failed to deactivate'); },
    },
  );

  const rows: UserRow[] = usersQuery.data?.data || [];
  const total: number = usersQuery.data?.total ?? rows.length;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-6)', gap: 'var(--space-4)' }}>
        <div>
          <h1 className="page-title">Users</h1>
          <p className="page-subtitle">Tenant user accounts and roles</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ New User</button>
      </div>

      <div className="card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)', display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          className="input"
          placeholder="Search email or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: 220 }}
        />
        <select
          className="input"
          value={activeFilter}
          onChange={(e) => setActiveFilter(e.target.value as any)}
          style={{ width: 160 }}
        >
          <option value="active">Active only</option>
          <option value="inactive">Inactive only</option>
          <option value="all">All</option>
        </select>
        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
          {total.toLocaleString()} user{total === 1 ? '' : 's'}
        </span>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        {usersQuery.isLoading ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>Loading...</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
            No users match these filters.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ background: 'var(--surface-secondary)', borderBottom: '2px solid var(--border-primary)' }}>
              <tr>
                {['Email', 'Name', 'Roles', 'Status', 'Last login', 'Actions'].map((h) => (
                  <th key={h} style={{ padding: 'var(--space-3)', textAlign: 'left', fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid var(--border-primary)' }}>
                  <td style={{ padding: 'var(--space-3)', fontFamily: 'monospace', fontSize: 'var(--font-size-sm)' }}>{u.email}</td>
                  <td style={{ padding: 'var(--space-3)' }}>{u.full_name || '—'}</td>
                  <td style={{ padding: 'var(--space-3)' }}>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {(u.roles || []).map((r) => (
                        <span key={r} style={{ padding: '2px 8px', borderRadius: 'var(--radius-sm)', background: 'var(--surface-secondary)', fontSize: 'var(--font-size-xs)', fontWeight: 600 }}>
                          {r}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ padding: 'var(--space-3)' }}>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-sm)',
                      background: u.is_active ? 'var(--brand-success)' : 'var(--text-tertiary)',
                      color: 'white',
                      fontSize: 'var(--font-size-xs)',
                      fontWeight: 600,
                    }}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ padding: 'var(--space-3)', fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}
                  </td>
                  <td style={{ padding: 'var(--space-3)' }}>
                    <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => setEditing(u)}>Edit</button>
                      <button className="btn btn-ghost btn-sm" onClick={() => setResetting(u)}>Reset PW</button>
                      {u.is_active && u.id !== me?.user_id && (
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ color: 'var(--brand-error)' }}
                          onClick={() => {
                            if (confirm(`Deactivate ${u.email}? They will be unable to sign in.`)) {
                              deactivateMutation.mutate(u.id);
                            }
                          }}
                        >
                          Deactivate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!usersQuery.isLoading && total > 0 && (
          <Pagination
            total={total}
            limit={PAGE_SIZE}
            offset={offset}
            onChange={setOffset}
            loading={usersQuery.isFetching}
            itemLabel="user"
          />
        )}
      </div>

      {showCreate && (
        <UserForm
          title="New user"
          selectableRoles={selectableRoles}
          roleCatalog={roleCatalog}
          submitLabel={createMutation.isLoading ? 'Creating…' : 'Create user'}
          onCancel={() => setShowCreate(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          showPassword
        />
      )}

      {editing && (
        <UserForm
          title={`Edit ${editing.email}`}
          selectableRoles={selectableRoles}
          roleCatalog={roleCatalog}
          initial={{ full_name: editing.full_name || '', roles: editing.roles, is_active: editing.is_active }}
          submitLabel={updateMutation.isLoading ? 'Saving…' : 'Save'}
          onCancel={() => setEditing(null)}
          onSubmit={(data) => updateMutation.mutate({ id: editing.id, payload: data })}
        />
      )}

      {resetting && (
        <PasswordResetModal
          userEmail={resetting.email}
          submitting={resetMutation.isLoading}
          onCancel={() => setResetting(null)}
          onSubmit={(pw) => resetMutation.mutate({ id: resetting.id, password: pw })}
        />
      )}
    </div>
  );
}

interface UserFormProps {
  title: string;
  selectableRoles: string[];
  roleCatalog: RoleMeta[];
  initial?: { full_name?: string; roles?: string[]; is_active?: boolean };
  submitLabel: string;
  showPassword?: boolean;
  onCancel: () => void;
  onSubmit: (payload: any) => void;
}

function UserForm({ title, selectableRoles, roleCatalog, initial, submitLabel, showPassword, onCancel, onSubmit }: UserFormProps) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState(initial?.full_name || '');
  const [password, setPassword] = useState('');
  const [roles, setRoles] = useState<string[]>(initial?.roles || ['readonly']);
  const [isActive, setIsActive] = useState<boolean>(initial?.is_active ?? true);

  const toggleRole = (r: string) => {
    setRoles(roles.includes(r) ? roles.filter((x) => x !== r) : [...roles, r]);
  };

  const submit = () => {
    const payload: any = { full_name: fullName || null, roles, is_active: isActive };
    if (showPassword) {
      payload.email = email;
      payload.password = password;
    }
    onSubmit(payload);
  };

  return (
    <Modal onClose={onCancel}>
      <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700, marginBottom: 'var(--space-4)' }}>{title}</h2>
      {showPassword && (
        <>
          <Field label="Email">
            <input type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password (≥ 8 chars)">
            <input type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        </>
      )}
      <Field label="Full name">
        <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </Field>
      <Field label="Roles">
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {selectableRoles.map((r) => {
            const active = roles.includes(r);
            const expansion = roleCatalog.find((c) => c.name === r)?.expands_to || [];
            return (
              <button
                key={r}
                type="button"
                onClick={() => toggleRole(r)}
                title={expansion.length ? `Includes: ${expansion.join(', ')}` : ''}
                style={{
                  padding: '4px 12px',
                  borderRadius: 'var(--radius-md)',
                  border: `1px solid ${active ? 'var(--brand-primary)' : 'var(--border-light)'}`,
                  background: active ? 'var(--brand-primary)' : 'transparent',
                  color: active ? 'white' : 'var(--text-primary)',
                  cursor: 'pointer',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 600,
                }}
              >
                {r}
              </button>
            );
          })}
        </div>
      </Field>
      <Field label="Status">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--font-size-sm)' }}>
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          Active (can sign in)
        </label>
      </Field>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', marginTop: 'var(--space-4)' }}>
        <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button className="btn btn-primary" onClick={submit}>{submitLabel}</button>
      </div>
    </Modal>
  );
}

function PasswordResetModal({ userEmail, submitting, onCancel, onSubmit }: { userEmail: string; submitting: boolean; onCancel: () => void; onSubmit: (pw: string) => void }) {
  const [pw, setPw] = useState('');
  return (
    <Modal onClose={onCancel}>
      <h2 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 700, marginBottom: 'var(--space-3)' }}>Reset password</h2>
      <p style={{ marginBottom: 'var(--space-3)', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
        Set a new password for <strong>{userEmail}</strong>. Share it via a secure channel.
      </p>
      <Field label="New password (≥ 8 chars)">
        <input type="password" className="input" value={pw} onChange={(e) => setPw(e.target.value)} />
      </Field>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', marginTop: 'var(--space-4)' }}>
        <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button className="btn btn-primary" disabled={pw.length < 8 || submitting} onClick={() => onSubmit(pw)}>
          {submitting ? 'Saving…' : 'Reset password'}
        </button>
      </div>
    </Modal>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 'var(--space-3)' }}>
      <label style={{ display: 'block', fontSize: 'var(--font-size-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function Modal({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 80, zIndex: 100 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--surface-primary)', padding: 'var(--space-6)', borderRadius: 'var(--radius-xl)', width: 480, maxWidth: '90vw' }}
      >
        {children}
      </div>
    </div>
  );
}
