import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';

const navItems = [
  { path: '/claims', label: 'Claims' },
  { path: '/denials', label: 'Denials' },
  { path: '/admin/payers', label: 'Payers' },
  { path: '/patients', label: 'Patients' },
  { path: '/edi', label: 'EDI Files' },
  { path: '/credentialing', label: 'Credentialing' },
  { path: '/payer-enrollment', label: 'Enrollment' },
  { path: '/admin/settings', label: 'Settings' },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <p style={{ margin: 0, fontSize: 13, color: '#e2e8f0', fontWeight: 600, lineHeight: 1.4 }}>
            Provider Onboarding and<br />Revenue Cycle Management
          </p>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div style={{ padding: 'var(--space-5)', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <p style={{ fontSize: 12, color: 'var(--text-tertiary)', margin: 0 }}>Signed in as</p>
            <p style={{ fontSize: 13, color: '#e2e8f0', margin: '2px 0 0', fontWeight: 500 }} className="truncate">
              {user?.email}
            </p>
          </div>
          <button
            onClick={logout}
            className="btn btn-ghost"
            style={{ width: '100%', color: 'var(--text-tertiary)', borderColor: 'rgba(255,255,255,0.1)', fontSize: 12 }}
          >
            Sign Out
          </button>
        </div>
      </aside>

      <main style={{ flex: 1, padding: 'var(--space-8)', background: 'var(--bg-primary)', overflowY: 'auto' }}>
        <div className="animate-in" style={{ maxWidth: 1400, margin: '0 auto' }}>
          {children}
        </div>
      </main>
    </div>
  );
}
