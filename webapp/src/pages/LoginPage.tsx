import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import toast from 'react-hot-toast';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err: any) {
      toast.error(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Background decoration */}
      <div style={{
        position: 'absolute',
        top: '-20%',
        right: '-10%',
        width: 600,
        height: 600,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(37,99,235,0.15) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute',
        bottom: '-20%',
        left: '-10%',
        width: 500,
        height: 500,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(124,58,237,0.1) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <form
        onSubmit={handleSubmit}
        className="animate-in"
        style={{
          background: 'rgba(255,255,255,0.95)',
          backdropFilter: 'blur(20px)',
          padding: 48,
          borderRadius: 'var(--radius-2xl)',
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25), 0 0 0 1px rgba(255,255,255,0.1)',
          width: 400,
          position: 'relative',
          zIndex: 1,
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <h1 style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '-0.02em',
            color: 'var(--text-primary)',
            marginBottom: 8,
          }}>
            Provider Onboarding &amp; RCM
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)' }}>
            Sign in to your account
          </p>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="input"
            placeholder="you@company.com"
            style={{ padding: '10px 14px' }}
          />
        </div>

        <div style={{ marginBottom: 28 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="input"
            placeholder="Enter your password"
            style={{ padding: '10px 14px' }}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="btn btn-primary btn-lg"
          style={{
            width: '100%',
            padding: '12px 0',
            fontSize: 'var(--font-size-base)',
            fontWeight: 600,
            borderRadius: 'var(--radius-lg)',
          }}
        >
          {loading ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
              Signing in...
            </span>
          ) : 'Sign In'}
        </button>

        {import.meta.env?.DEV && (
          <p style={{ marginTop: 24, textAlign: 'center', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
            Dev: admin@app.io / admin
          </p>
        )}
      </form>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
