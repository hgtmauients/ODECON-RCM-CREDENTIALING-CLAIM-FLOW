import React, { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import NotificationBell from '@/components/NotificationBell';
import GlobalSearch from '@/components/GlobalSearch';

interface NavItem {
  path: string;
  label: string;
  /** When set, the link only renders if the user holds one of the listed roles. */
  requiresAnyRole?: string[];
}

const navItems: NavItem[] = [
  { path: '/', label: 'Home' },
  { path: '/claims', label: 'Claims' },
  { path: '/denials', label: 'Denials' },
  { path: '/admin/payers', label: 'Payers' },
  { path: '/patients', label: 'Patients' },
  { path: '/edi', label: 'EDI Files' },
  { path: '/credentialing', label: 'Credentialing' },
  { path: '/payer-enrollment', label: 'Enrollment' },
  { path: '/admin/users', label: 'Users', requiresAnyRole: ['admin', 'super_admin'] },
  { path: '/admin/audit-log', label: 'Audit log', requiresAnyRole: ['admin', 'super_admin'] },
  { path: '/admin/settings', label: 'Settings', requiresAnyRole: ['admin', 'super_admin'] },
];

const MOBILE_BREAKPOINT = 768;

function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT,
  );
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);
  return isMobile;
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const isMobile = useIsMobile();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // Close drawer when route changes (mobile UX)
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // Lock body scroll when drawer is open on mobile
  useEffect(() => {
    if (drawerOpen && isMobile) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = prev; };
    }
  }, [drawerOpen, isMobile]);

  // Escape closes the drawer
  useEffect(() => {
    if (!drawerOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [drawerOpen]);

  const sidebarVisible = !isMobile || drawerOpen;

  return (
    <div style={{ display: 'flex', minHeight: '100vh', position: 'relative' }}>
      {/* Mobile top bar */}
      {isMobile && (
        <header
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            height: 56,
            background: '#0f172a',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            display: 'flex',
            alignItems: 'center',
            padding: '0 var(--space-4)',
            zIndex: 100,
          }}
        >
          <button
            type="button"
            aria-label={drawerOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(!drawerOpen)}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#e2e8f0',
              cursor: 'pointer',
              padding: 8,
              marginRight: 12,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            <span style={{ display: 'block', width: 22, height: 2, background: '#e2e8f0' }} />
            <span style={{ display: 'block', width: 22, height: 2, background: '#e2e8f0' }} />
            <span style={{ display: 'block', width: 22, height: 2, background: '#e2e8f0' }} />
          </button>
          <p style={{ margin: 0, fontSize: 13, color: '#e2e8f0', fontWeight: 600 }}>
            Provider Onboarding & RCM
          </p>
        </header>
      )}

      {/* Backdrop on mobile when drawer is open */}
      {isMobile && drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            zIndex: 90,
          }}
        />
      )}

      {/* Sidebar */}
      <aside
        className="sidebar"
        aria-label="Main navigation"
        style={{
          ...(isMobile
            ? {
                position: 'fixed',
                top: 0,
                left: 0,
                bottom: 0,
                width: 260,
                zIndex: 99,
                transform: sidebarVisible ? 'translateX(0)' : 'translateX(-100%)',
                transition: 'transform 0.2s ease',
                paddingTop: 0,
              }
            : {}),
        }}
      >
        <div className="sidebar-brand">
          <p style={{ margin: 0, fontSize: 13, color: '#e2e8f0', fontWeight: 600, lineHeight: 1.4 }}>
            Provider Onboarding and<br />Revenue Cycle Management
          </p>
        </div>

        <div style={{ padding: '0 var(--space-5) var(--space-3)' }}>
          <GlobalSearch />
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {navItems
            .filter((item) => {
              if (!item.requiresAnyRole || !item.requiresAnyRole.length) return true;
              const myRoles = user?.roles || [];
              return item.requiresAnyRole.some((r) => myRoles.includes(r));
            })
            .map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                {item.label}
              </NavLink>
            ))}
        </nav>

        <div style={{ padding: 'var(--space-5)', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <NotificationBell />
          </div>
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

      <main
        style={{
          flex: 1,
          padding: isMobile ? 'var(--space-4)' : 'var(--space-8)',
          paddingTop: isMobile ? `calc(56px + var(--space-4))` : 'var(--space-8)',
          background: 'var(--bg-primary)',
          overflowY: 'auto',
          minWidth: 0,
        }}
      >
        <div className="animate-in" style={{ maxWidth: 1400, margin: '0 auto' }}>
          {children}
        </div>
      </main>
    </div>
  );
}
