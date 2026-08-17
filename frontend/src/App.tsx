import { Route, Routes } from "react-router";

import { AppShell } from "./components/AppShell";
import { DesignSystemPage } from "./design-system/DesignSystemPage";
import { HomePage } from "./pages/HomePage";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/design-system" element={<DesignSystemPage />} />
      </Routes>
    </AppShell>
  );
}
