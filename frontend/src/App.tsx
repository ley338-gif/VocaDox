import { Route, Routes } from "react-router";

import { AppShell } from "./components/AppShell";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequirePermission } from "./auth/RequireAuth";
import { DesignSystemPage } from "./design-system/DesignSystemPage";
import { AdminHomePage } from "./pages/AdminHomePage";
import { AdminTemplatesPage } from "./pages/AdminTemplatesPage";
import { AppHomePage } from "./pages/AppHomePage";
import { ConversationDetailPage } from "./pages/ConversationDetailPage";
import { ConversationsListPage } from "./pages/ConversationsListPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { NewConversationPage } from "./pages/NewConversationPage";

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
                <AdminHomePage />
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
        </Routes>
      </AppShell>
    </AuthProvider>
  );
}
