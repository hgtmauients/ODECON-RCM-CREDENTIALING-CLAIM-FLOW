import React, { useState, useEffect } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import NotificationBell from '@/components/NotificationBell';
import GlobalSearch from '@/components/GlobalSearch';
import { useIsMobile } from '@/hooks/useIsMobile';

interface NavItem {
  path: string;
  label: string;
  section: 'Operations' | 'Data exchange' | 'Administration';
  /** When set, the link only renders if the user holds one of the listed roles. */
  requiresAnyRole?: string[];
}

const navItems: NavItem[] = [
  { path: '/', label: 'Home', section: 'Operations' },
  { path: '/claims', label: 'Claims', section: 'Operations' },
  { path: '/denials', label: 'Denials', section: 'Operations' },
  { path: '/patients', label: 'Patients', section: 'Operations' },
  { path: '/credentialing', label: 'Credentialing', section: 'Operations' },
  { path: '/payer-enrollment', label: 'Enrollment', section: 'Operations' },
  { path: '/edi', label: 'EDI Files', section: 'Data exchange' },
  { path: '/admin/payers', label: 'Payers', section: 'Administration', requiresAnyRole: ['admin', 'super_admin'] },
  { path: '/admin/users', label: 'Users', section: 'Administration', requiresAnyRole: ['admin', 'super_admin'] },
  { path: '/admin/audit-log', label: 'Audit log', section: 'Administration', requiresAnyRole: ['admin', 'super_admin'] },
  { path: '/admin/settings', label: 'Settings', section: 'Administration', requiresAnyRole: ['admin', 'super_admin'] },
];

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
  const visibleItems = navItems.filter((item) => {
    if (!item.requiresAnyRole || !item.requiresAnyRole.length) return true;
    const myRoles = user?.roles || [];
    return item.requiresAnyRole.some((r) => myRoles.includes(r));
  });
  const sectionOrder: Array<NavItem['section']> = ['Operations', 'Data exchange', 'Administration'];
  const currentLabel = visibleItems.find((item) => {
    if (item.path === '/') return location.pathname === '/';
    return location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
  })?.label || 'Workspace';

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

        <div className="sidebar-section">Quick actions</div>
        <div className="sidebar-quick-actions">
          <Link to="/claims/new" className="sidebar-quick-link">New claim</Link>
          <Link to="/denials" className="sidebar-quick-link">Review denials</Link>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {sectionOrder.map((section) => {
            const sectionItems = visibleItems.filter((item) => item.section === section);
            if (sectionItems.length === 0) return null;
            return (
              <React.Fragment key={section}>
                <div className="sidebar-section">{section}</div>
                {sectionItems.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === '/'}
                    className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                  >
                    {item.label}
                  </NavLink>
                ))}
              </React.Fragment>
            );
          })}
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
        {!isMobile && (
          <div
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: 'var(--space-3) var(--space-4)',
              marginBottom: 'var(--space-4)',
              borderRadius: 'var(--radius-xl)',
              border: '1px solid var(--glass-border)',
              background: 'var(--surface-glass)',
              backdropFilter: 'var(--glass-blur)',
            }}
          >
            <div>
              <p style={{ margin: 0, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-tertiary)', fontWeight: 700 }}>
                Workspace
              </p>
              <p style={{ margin: 0, fontSize: 'var(--font-size-sm)', fontWeight: 700, color: 'var(--text-primary)' }}>
                {currentLabel}
              </p>
            </div>
            <p style={{ margin: 0, fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
              {new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
            </p>
          </div>
        )}
        <div className="animate-in" style={{ maxWidth: 1400, margin: '0 auto' }}>
          {children}
        </div>
      </main>
    </div>
  );
}
