import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import {
  AppLayout,
  ErrorBoundary,
  LoadingBlock,
  ProtectedRoute,
  ToastProvider
} from "./components";
import { PartnerRoute } from "./portals/partner/PartnerRoute";
import { CustomerRoute } from "./portals/customer/CustomerRoute";
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
// Real-estate modules
const InventoryPage = lazy(() => import("./pages/inventory/InventoryPage"));
const ProjectsPage = lazy(() => import("./pages/inventory/ProjectsPage"));
const SiteVisitsPage = lazy(() => import("./pages/site-visits/SiteVisitsPage"));
const BookingsPage = lazy(() => import("./pages/bookings/BookingsPage"));
// Registration & possession trackers
const RegistrationTrackerPage = lazy(() => import("./pages/trackers/RegistrationTrackerPage"));
const PossessionTrackerPage = lazy(() => import("./pages/trackers/PossessionTrackerPage"));
// Customer portal (PWA)
const CustomerLayout = lazy(() => import("./portals/customer/CustomerLayout").then((m) => ({ default: m.CustomerLayout })));
const PaymentStatusPage = lazy(() => import("./portals/customer/pages/PaymentStatusPage"));
const DocumentDownloadsPage = lazy(() => import("./portals/customer/pages/DocumentDownloadsPage"));
const ServiceRequestsPage = lazy(() => import("./portals/customer/pages/ServiceRequestsPage"));
const ReferralSubmitPage = lazy(() => import("./portals/customer/pages/ReferralSubmitPage"));
// Channel-partner portal
const PartnerLayout = lazy(() => import("./portals/partner/PartnerLayout").then((m) => ({ default: m.PartnerLayout })));
const PartnerLeadFormPage = lazy(() => import("./portals/partner/pages/PartnerLeadFormPage"));
const PartnerLeadTrackerPage = lazy(() => import("./portals/partner/pages/PartnerLeadTrackerPage"));
const PartnerCommissionsPage = lazy(() => import("./portals/partner/pages/PartnerCommissionsPage"));
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

                      {/* Customer portal (PWA) — own layout, role-gated to "customer" */}
                      <Route path="/customer" element={<CustomerRoute />}>
                        <Route element={<CustomerLayout />}>
                          <Route index element={<Navigate to="payments" replace />} />
                          <Route path="payments"  element={<PaymentStatusPage />} />
                          <Route path="documents" element={<DocumentDownloadsPage />} />
                          <Route path="service"   element={<ServiceRequestsPage />} />
                          <Route path="refer"     element={<ReferralSubmitPage />} />
                        </Route>
                      </Route>

                      {/* Channel-partner portal — own layout, role-gated */}
                      <Route path="/partner" element={<PartnerRoute />}>
                        <Route element={<PartnerLayout />}>
                          <Route index element={<Navigate to="leads" replace />} />
                          <Route path="submit" element={<PartnerLeadFormPage />} />
                          <Route path="leads" element={<PartnerLeadTrackerPage />} />
                          <Route path="commissions" element={<PartnerCommissionsPage />} />
                        </Route>
                      </Route>

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
                        {/* Real-estate modules */}
                        {FEATURES.projects && <Route path="projects" element={<ProjectsPage />} />}
                        {FEATURES.inventory && <Route path="inventory" element={<InventoryPage />} />}
                        {FEATURES.site_visits && <Route path="site-visits" element={<SiteVisitsPage />} />}
                        {FEATURES.bookings && <Route path="bookings" element={<BookingsPage />} />}
                        {FEATURES.bookings && <Route path="trackers/registration" element={<RegistrationTrackerPage />} />}
                        {FEATURES.bookings && <Route path="trackers/possession" element={<PossessionTrackerPage />} />}
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
