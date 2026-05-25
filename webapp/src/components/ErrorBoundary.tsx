import React from 'react';

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

interface Props {
  children: React.ReactNode;
}

/**
 * Top-level error boundary. Catches render-time exceptions in the React tree
 * and renders a fallback UI instead of unmounting the entire app.
 */
export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    this.setState({ errorInfo });
    console.error('[ErrorBoundary]', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): React.ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div
        role="alert"
        style={{
          padding: 'var(--space-8)',
          maxWidth: 600,
          margin: '4rem auto',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
      >
        <div
          style={{
            padding: 'var(--space-6)',
            border: '1px solid var(--brand-error, #ef4444)',
            borderRadius: 'var(--radius-lg, 12px)',
            background: 'var(--surface-primary, #fff)',
          }}
        >
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--brand-error, #ef4444)', marginBottom: '1rem' }}>
            Something went wrong
          </h1>
          <p style={{ color: 'var(--text-secondary, #6b7280)', marginBottom: '1.5rem' }}>
            An unexpected error occurred. The error has been logged. You can try to recover or reload the page.
          </p>
          {this.state.error && (
            <details style={{ marginBottom: '1.5rem' }}>
              <summary style={{ cursor: 'pointer', fontSize: '0.875rem', color: 'var(--text-secondary, #6b7280)' }}>
                Technical details
              </summary>
              <pre
                style={{
                  marginTop: '0.5rem',
                  padding: '1rem',
                  background: 'var(--surface-secondary, #f3f4f6)',
                  borderRadius: 'var(--radius-md, 6px)',
                  fontSize: '0.75rem',
                  overflow: 'auto',
                  maxHeight: 240,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {this.state.error.message}
                {'\n\n'}
                {this.state.error.stack}
              </pre>
            </details>
          )}
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={this.handleReset}
              style={{
                padding: '0.5rem 1rem',
                background: 'transparent',
                border: '1px solid var(--border-primary, #e5e7eb)',
                borderRadius: 'var(--radius-md, 6px)',
                cursor: 'pointer',
                fontSize: '0.875rem',
              }}
            >
              Try Again
            </button>
            <button
              onClick={this.handleReload}
              style={{
                padding: '0.5rem 1rem',
                background: 'var(--brand-primary, #3b82f6)',
                color: 'white',
                border: 'none',
                borderRadius: 'var(--radius-md, 6px)',
                cursor: 'pointer',
                fontSize: '0.875rem',
                fontWeight: 600,
              }}
            >
              Reload Page
            </button>
          </div>
        </div>
      </div>
    );
  }
}
