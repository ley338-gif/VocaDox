import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "./api/client";
import { App } from "./App";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof apiClient>();
  return { ...actual, me: vi.fn() };
});

function renderApp(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("App", () => {
  beforeEach(() => {
    vi.mocked(apiClient.me).mockRejectedValue(new apiClient.ApiError(401, "not authenticated"));
  });

  it("redirects an unauthenticated visitor from / to /login", async () => {
    renderApp("/");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Sign in to VocaDox" })).toBeInTheDocument()
    );
  });

  it("renders the design system route", () => {
    renderApp("/design-system");
    expect(screen.getByRole("heading", { name: "Design System" })).toBeInTheDocument();
  });
});
