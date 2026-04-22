import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from 'react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './auth/AuthProvider';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import LoginPage from './pages/LoginPage';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const ClaimsManagement = lazy(() => import('./pages/rcm/ClaimsManagement'));
const ClaimCreate = lazy(() => import('./pages/rcm/ClaimCreate'));
const ClaimDetail = lazy(() => import('./pages/rcm/ClaimDetail'));
const ClaimEdit = lazy(() => import('./pages/rcm/ClaimEdit'));
const DenialDashboard = lazy(() => import('./pages/rcm/DenialDashboard'));
const DenialDetail = lazy(() => import('./pages/rcm/DenialDetail'));
const PayerEnrollment = lazy(() => import('./pages/rcm/PayerEnrollment'));
const PayerEnrollmentDetail = lazy(() => import('./pages/rcm/PayerEnrollmentDetail'));
const EDIFileManager = lazy(() => import('./pages/rcm/EDIFileManager'));
const CredentialingQueue = lazy(() => import('./pages/CredentialingQueue'));
const PayerProfiles = lazy(() => import('./pages/admin/PayerProfiles'));
const PayerProfileEditor = lazy(() => import('./pages/admin/PayerProfileEditor'));
const PayerWizard = lazy(() => import('./pages/admin/PayerWizard'));
const RuleBuilder = lazy(() => import('./pages/admin/RuleBuilder'));
const Settings = lazy(() => import('./pages/admin/Settings'));
const Users = lazy(() => import('./pages/admin/Users'));
const AuditLog = lazy(() => import('./pages/admin/AuditLog'));
const PatientManagement = lazy(() => import('./pages/rcm/PatientManagement'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PageLoader() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
      <div style={{ width: 24, height: 24, border: '3px solid var(--border-light)', borderTopColor: 'var(--brand-primary)', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Suspense fallback={<PageLoader />}>
                      <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/claims" element={<ClaimsManagement />} />
                        <Route path="/claims/new" element={<ClaimCreate />} />
                        <Route path="/claims/:claimId" element={<ClaimDetail />} />
                        <Route path="/claims/:claimId/edit" element={<ClaimEdit />} />
                        <Route path="/denials" element={<DenialDashboard />} />
                        <Route path="/denials/:denialId" element={<DenialDetail />} />
                        <Route path="/payer-enrollment" element={<PayerEnrollment />} />
                        <Route path="/payer-enrollment/:caseId" element={<PayerEnrollmentDetail />} />
                        <Route path="/edi" element={<EDIFileManager />} />
                        <Route path="/patients" element={<PatientManagement />} />
                        <Route path="/credentialing" element={<CredentialingQueue />} />
                        <Route path="/admin/payers" element={<PayerProfiles />} />
                        <Route path="/admin/payers/wizard" element={<PayerWizard />} />
                        <Route path="/admin/payers/:payerId" element={<PayerProfileEditor />} />
                        <Route path="/admin/payers/:payerId/rules" element={<RuleBuilder />} />
                        <Route path="/admin/payers/:payerId/rules/:ruleId" element={<RuleBuilder />} />
                        <Route path="/admin/settings" element={<Settings />} />
                        <Route path="/admin/users" element={<Users />} />
                        <Route path="/admin/audit-log" element={<AuditLog />} />
                      </Routes>
                    </Suspense>
                  </Layout>
                </ProtectedRoute>
              }
            />
            </Routes>
            <Toaster position="top-right" />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
