import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import {
  AppLayout,
  ErrorBoundary,
  LoadingBlock,
  ProtectedRoute,
  ToastProvider
} from "./components";
import { FEATURES } from "./config/features";
import { AuthProvider } from "./context/AuthContext";
import { OrgProvider } from "./context/OrgContext";
import { PipelineProvider } from "./context/PipelineContext";
import { RealtimeProvider } from "./realtime";

// Always-visible core pages — static import so navigating between them is
// instant (no chunk fetch, no Suspense fallback flash). The ~50-100KB they
// add to the initial bundle pays itself back on every nav click.
import AnalyticsPage from "./pages/AnalyticsPage";
import CustomersPage from "./pages/CustomersPage";
import DashboardPage from "./pages/DashboardPage";
import LeadsPage from "./pages/LeadsPage";
import { PlatformAdminPage } from "./pages/PlatformAdminPage";
import UsersPage from "./pages/UsersPage";

// Auth screens + feature-flagged modules stay lazy — they're rarely loaded
// or hidden by default, so the code-split saves the initial bundle.
const LoginPage = lazy(() => import("./pages/auth/LoginPage"));
const RegisterPage = lazy(() => import("./pages/auth/RegisterPage"));
const DealsPage = lazy(() => import("./pages/DealsPage"));
const TasksPage = lazy(() => import("./pages/TasksPage"));
const ActivitiesPage = lazy(() => import("./pages/ActivitiesPage"));
const FinancePage = lazy(() => import("./pages/FinancePage"));
const HRPage = lazy(() => import("./pages/HRPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));


export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <OrgProvider>
              <RealtimeProvider>
                <PipelineProvider>
                  <Suspense fallback={<LoadingBlock label="Loading…" />}>
                    <Routes>
                      <Route path="/login" element={<LoginPage />} />
                      <Route path="/register" element={<RegisterPage />} />

                      <Route
                        element={
                          <ProtectedRoute>
                            <AppLayout />
                          </ProtectedRoute>
                        }
                      >
                        <Route index element={<DashboardPage />} />
                        <Route path="customers" element={<CustomersPage />} />
                        <Route path="leads" element={<LeadsPage />} />
                        {/* Modules below are gated by `frontend/src/config/features.ts`.
                            When a flag is false the route doesn't mount, so direct URL
                            access falls through to the catch-all NotFoundPage below. */}
                        {FEATURES.deals && <Route path="deals" element={<DealsPage />} />}
                        {FEATURES.tasks && <Route path="tasks" element={<TasksPage />} />}
                        {FEATURES.activities && <Route path="activities" element={<ActivitiesPage />} />}
                        <Route path="analytics" element={<AnalyticsPage />} />
                        {FEATURES.finance && <Route path="finance" element={<FinancePage />} />}
                        {FEATURES.hr && <Route path="hr" element={<HRPage />} />}
                        <Route path="users" element={<UsersPage />} />
                        <Route path="admin" element={<PlatformAdminPage />} />
                        <Route path="*" element={<NotFoundPage />} />
                      </Route>
                    </Routes>
                  </Suspense>
                </PipelineProvider>
              </RealtimeProvider>
            </OrgProvider>
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
