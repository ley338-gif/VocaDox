import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ user: { displayName: "Test" }, csrfToken: null, hasPermission: () => true, logout: vi.fn() }) }));
vi.mock("../recording/useOfflineQueueSync", () => ({ useOfflineQueueSync: () => ({ pendingCount: 0 }) }));
vi.mock("../api/admin", () => ({ getDashboard: () => new Promise(() => {}) }));

function show(components?: { healthy: boolean }[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  if (components) client.setQueryData(["appshell-health"], { components });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/app/conversations/test"]}><AppShell>Test</AppShell></MemoryRouter></QueryClientProvider>);
}
describe("verified system health", () => {
  it("does not claim healthy while health is unknown", () => {
    show();
    expect(screen.getByText("Systemstatus nicht verfügbar")).toBeInTheDocument();
    expect(screen.queryByText("Alle Systeme betriebsbereit")).not.toBeInTheDocument();
  });
  it("does not treat an empty component list as healthy", () => {
    show([]);
    expect(screen.getByText("Systemstatus nicht verfügbar")).toBeInTheDocument();
  });
  it("shows confirmed healthy status and preserves parent navigation on details", () => {
    show([{ healthy: true }]);
    expect(screen.getByText("Alle Systeme betriebsbereit")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gespräche" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });
  it("shows a failure when a component is unhealthy", () => {
    show([{ healthy: true }, { healthy: false }]);
    expect(screen.getByText("Systemstörung")).toBeInTheDocument();
  });
});
