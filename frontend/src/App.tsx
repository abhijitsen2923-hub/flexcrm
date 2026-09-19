import { Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { lazyWithReload } from "./utils/lazyWithReload";

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
const LoginPage = lazyWithReload(() => import("./pages/auth/LoginPage"));
const RegisterPage = lazyWithReload(() => import("./pages/auth/RegisterPage"));
const DealsPage = lazyWithReload(() => import("./pages/DealsPage"));
const TasksPage = lazyWithReload(() => import("./pages/TasksPage"));
const ActivitiesPage = lazyWithReload(() => import("./pages/ActivitiesPage"));
const FinancePage = lazyWithReload(() => import("./pages/FinancePage"));
const ExpensesPage = lazyWithReload(() => import("./pages/finance/ExpensesPage"));
const VendorsPage = lazyWithReload(() => import("./pages/finance/VendorsPage"));
const VendorPaymentsPage = lazyWithReload(() => import("./pages/finance/VendorPaymentsPage"));
const FinanceSettingsPage = lazyWithReload(() => import("./pages/finance/FinanceSettingsPage"));
const IncomePage = lazyWithReload(() => import("./pages/finance/IncomePage"));
const FinanceDashboardPage = lazyWithReload(() => import("./pages/finance/FinanceDashboardPage"));
const CustomerReceivablesPage = lazyWithReload(() => import("./pages/finance/CustomerReceivablesPage"));
const CustomerDemandsPage = lazyWithReload(() => import("./pages/finance/CustomerDemandsPage"));
const ReportsPage = lazyWithReload(() => import("./pages/finance/ReportsPage"));
const PayrollPage = lazyWithReload(() => import("./pages/finance/PayrollPage"));
const BudgetsPage = lazyWithReload(() => import("./pages/finance/BudgetsPage"));
const BankPage = lazyWithReload(() => import("./pages/finance/BankPage"));
const HRPage = lazyWithReload(() => import("./pages/HRPage"));
// Real-estate modules
const InventoryPage = lazyWithReload(() => import("./pages/inventory/InventoryPage"));
const ProjectsPage = lazyWithReload(() => import("./pages/inventory/ProjectsPage"));
const SiteVisitsPage = lazyWithReload(() => import("./pages/site-visits/SiteVisitsPage"));
const BookingsPage = lazyWithReload(() => import("./pages/bookings/BookingsPage"));
const IntegrationsPage = lazyWithReload(() => import("./pages/integrations/IntegrationsPage"));
const CallsPage = lazyWithReload(() => import("./pages/calls/CallsPage"));
// Registration & possession trackers
const RegistrationTrackerPage = lazyWithReload(() => import("./pages/trackers/RegistrationTrackerPage"));
const PossessionTrackerPage = lazyWithReload(() => import("./pages/trackers/PossessionTrackerPage"));
// Customer portal (PWA)
const CustomerLayout = lazyWithReload(() => import("./portals/customer/CustomerLayout").then((m) => ({ default: m.CustomerLayout })));
const PaymentStatusPage = lazyWithReload(() => import("./portals/customer/pages/PaymentStatusPage"));
const DocumentDownloadsPage = lazyWithReload(() => import("./portals/customer/pages/DocumentDownloadsPage"));
const ServiceRequestsPage = lazyWithReload(() => import("./portals/customer/pages/ServiceRequestsPage"));
const ReferralSubmitPage = lazyWithReload(() => import("./portals/customer/pages/ReferralSubmitPage"));
// Channel-partner portal
const PartnerLayout = lazyWithReload(() => import("./portals/partner/PartnerLayout").then((m) => ({ default: m.PartnerLayout })));
const PartnerDashboardPage = lazyWithReload(() => import("./portals/partner/pages/PartnerDashboardPage"));
const PartnerLeadFormPage = lazyWithReload(() => import("./portals/partner/pages/PartnerLeadFormPage"));
const PartnerLeadTrackerPage = lazyWithReload(() => import("./portals/partner/pages/PartnerLeadTrackerPage"));
const PartnerCommissionsPage = lazyWithReload(() => import("./portals/partner/pages/PartnerCommissionsPage"));
// Staff channel-partner management
const ChannelPartnersPage = lazyWithReload(() => import("./pages/channel-partners/ChannelPartnersPage"));
const NotFoundPage = lazyWithReload(() => import("./pages/NotFoundPage"));


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
                          <Route index element={<Navigate to="dashboard" replace />} />
                          <Route path="dashboard" element={<PartnerDashboardPage />} />
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
                        {FEATURES.finance && <Route path="finance" element={<ExpensesPage />} />}
                        {FEATURES.finance && <Route path="finance/vendors" element={<VendorsPage />} />}
                        {FEATURES.finance && <Route path="finance/vendor-payments" element={<VendorPaymentsPage />} />}
                        {FEATURES.finance && <Route path="finance/sales" element={<FinancePage />} />}
                        {FEATURES.finance && <Route path="finance/settings" element={<FinanceSettingsPage />} />}
                        {FEATURES.finance && <Route path="finance/dashboard" element={<FinanceDashboardPage />} />}
                        {FEATURES.finance && <Route path="finance/income" element={<IncomePage />} />}
                        {FEATURES.finance && <Route path="finance/receivables" element={<CustomerReceivablesPage />} />}
                        {FEATURES.finance && <Route path="finance/demands" element={<CustomerDemandsPage />} />}
                        {FEATURES.finance && <Route path="finance/reports" element={<ReportsPage />} />}
                        {FEATURES.finance && <Route path="finance/payroll" element={<PayrollPage />} />}
                        {FEATURES.finance && <Route path="finance/budgets" element={<BudgetsPage />} />}
                        {FEATURES.finance && <Route path="finance/bank" element={<BankPage />} />}
                        {FEATURES.hr && <Route path="hr" element={<HRPage />} />}
                        {/* Real-estate modules */}
                        {FEATURES.projects && <Route path="projects" element={<ProjectsPage />} />}
                        {FEATURES.inventory && <Route path="inventory" element={<InventoryPage />} />}
                        {FEATURES.site_visits && <Route path="site-visits" element={<SiteVisitsPage />} />}
                        {FEATURES.bookings && <Route path="bookings" element={<BookingsPage />} />}
                        {FEATURES.bookings && <Route path="trackers/registration" element={<RegistrationTrackerPage />} />}
                        {FEATURES.bookings && <Route path="trackers/possession" element={<PossessionTrackerPage />} />}
                        {FEATURES.bookings && <Route path="channel-partners" element={<ChannelPartnersPage />} />}
                        {(FEATURES.meta_facebook || FEATURES.meta_instagram || FEATURES.portal_99acres || FEATURES.sheet_leads || FEATURES.callyzer) && <Route path="integrations" element={<IntegrationsPage />} />}
                        {FEATURES.callyzer && <Route path="calls" element={<CallsPage />} />}
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
