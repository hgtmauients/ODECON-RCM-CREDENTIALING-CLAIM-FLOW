import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// Optional Sentry initialization. Loaded dynamically so the bundle stays
// lean when SENTRY_DSN is not configured. Build-time env var:
//   VITE_SENTRY_DSN — DSN
//   VITE_SENTRY_ENV — environment label (defaults to mode)
const sentryDsn = (import.meta.env as any)?.VITE_SENTRY_DSN;
if (sentryDsn) {
  import('@sentry/react').then(({ init, browserTracingIntegration }) => {
    init({
      dsn: sentryDsn,
      environment: (import.meta.env as any)?.VITE_SENTRY_ENV || import.meta.env.MODE,
      release: (import.meta.env as any)?.VITE_RELEASE_VERSION,
      tracesSampleRate: 0.1,
      integrations: [browserTracingIntegration()],
    });
  }).catch(() => {
    // Sentry SDK not installed; ignore.
  });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
