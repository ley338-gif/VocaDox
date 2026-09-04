import { Route, Routes } from "react-router";

import { AppShell } from "./components/AppShell";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequirePermission } from "./auth/RequireAuth";
import { DesignSystemPage } from "./design-system/DesignSystemPage";
import { AdminAboutPage } from "./pages/AdminAboutPage";
import { AdminAnalyticsPage } from "./pages/AdminAnalyticsPage";
import { AdminAuditPage } from "./pages/AdminAuditPage";
import { AdminAuthenticationPage } from "./pages/AdminAuthenticationPage";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { AdminDiarizationPage } from "./pages/AdminDiarizationPage";
import { AdminEvaluationLabPage } from "./pages/AdminEvaluationLabPage";
import { AdminGroupsPage } from "./pages/AdminGroupsPage";
import { AdminJobsPage } from "./pages/AdminJobsPage";
import { AdminModelsPage } from "./pages/AdminModelsPage";
import { AdminOrganizationsPage } from "./pages/AdminOrganizationsPage";
import { AdminProfilesPage } from "./pages/AdminProfilesPage";
import { AdminPromptsPage } from "./pages/AdminPromptsPage";
import { AdminRetentionPage } from "./pages/AdminRetentionPage";
import { AdminServiceAccountsPage } from "./pages/AdminServiceAccountsPage";
import { AdminSpeechPage } from "./pages/AdminSpeechPage";
import { AdminStoragePage } from "./pages/AdminStoragePage";
import { AdminTemplatesPage } from "./pages/AdminTemplatesPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { AdminWebhooksPage } from "./pages/AdminWebhooksPage";
import { AdminWorkersPage } from "./pages/AdminWorkersPage";
import { AppHomePage } from "./pages/AppHomePage";
import { ConversationDetailPage } from "./pages/ConversationDetailPage";
import { ConversationsListPage } from "./pages/ConversationsListPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { NewConversationPage } from "./pages/NewConversationPage";

/**
 * Phase 7 Admin Portal routes (spec §48): each page is wrapped in its own
 * `RequirePermission` matching the exact permission its backend endpoint
 * enforces (never a single blanket gate) — `AdminLayout`'s sidebar link
 * visibility is a convenience only, this is the real security boundary.
 */
export function App() {
  return (
    <AuthProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/design-system" element={<DesignSystemPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/app"
            element={
              <RequireAuth>
                <AppHomePage />
              </RequireAuth>
            }
          />
          <Route
            path="/app/conversations"
            element={
              <RequireAuth>
                <ConversationsListPage />
              </RequireAuth>
            }
          />
          <Route
            path="/app/conversations/new"
            element={
              <RequireAuth>
                <NewConversationPage />
              </RequireAuth>
            }
          />
          <Route
            path="/app/conversations/:id"
            element={
              <RequireAuth>
                <ConversationDetailPage />
              </RequireAuth>
            }
          />

          <Route
            path="/admin"
            element={
              <RequirePermission code="system:admin">
                <AdminDashboardPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/users"
            element={
              <RequirePermission code="user:manage">
                <AdminUsersPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/groups"
            element={
              <RequirePermission code="group:manage">
                <AdminGroupsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/organizations"
            element={
              <RequirePermission code="organization:manage">
                <AdminOrganizationsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/templates"
            element={
              <RequirePermission code="template:read">
                <AdminTemplatesPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/models"
            element={
              <RequirePermission code="provider:read">
                <AdminModelsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/speech"
            element={
              <RequirePermission code="provider:read">
                <AdminSpeechPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/diarization"
            element={
              <RequirePermission code="provider:read">
                <AdminDiarizationPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/profiles"
            element={
              <RequirePermission code="processing-profile:read">
                <AdminProfilesPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/prompts"
            element={
              <RequirePermission code="template:read">
                <AdminPromptsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/jobs"
            element={
              <RequirePermission code="system:admin">
                <AdminJobsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/workers"
            element={
              <RequirePermission code="system:admin">
                <AdminWorkersPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/storage"
            element={
              <RequirePermission code="system:admin">
                <AdminStoragePage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/retention"
            element={
              <RequirePermission code="retention:read">
                <AdminRetentionPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/analytics"
            element={
              <RequirePermission code="analytics:read">
                <AdminAnalyticsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/evaluation"
            element={
              <RequirePermission code="analytics:read">
                <AdminEvaluationLabPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/service-accounts"
            element={
              <RequirePermission code="service-account:read">
                <AdminServiceAccountsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/webhooks"
            element={
              <RequirePermission code="webhook:read">
                <AdminWebhooksPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/authentication"
            element={
              <RequirePermission code="system:admin">
                <AdminAuthenticationPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/audit"
            element={
              <RequirePermission code="audit:read">
                <AdminAuditPage />
              </RequirePermission>
            }
          />
          <Route
            path="/admin/about"
            element={
              <RequirePermission code="system:admin">
                <AdminAboutPage />
              </RequirePermission>
            }
          />
        </Routes>
      </AppShell>
    </AuthProvider>
  );
}
