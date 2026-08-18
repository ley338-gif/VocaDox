import { Route, Routes } from "react-router";

import { AppShell } from "./components/AppShell";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequirePermission } from "./auth/RequireAuth";
import { DesignSystemPage } from "./design-system/DesignSystemPage";
import { AdminHomePage } from "./pages/AdminHomePage";
import { AppHomePage } from "./pages/AppHomePage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";

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
            path="/admin"
            element={
              <RequirePermission code="system:admin">
                <AdminHomePage />
              </RequirePermission>
            }
          />
        </Routes>
      </AppShell>
    </AuthProvider>
  );
}
