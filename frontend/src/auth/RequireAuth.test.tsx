import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { AuthProvider } from "./AuthContext";
import { RequireAuth, RequirePermission } from "./RequireAuth";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof apiClient>();
  return { ...actual, me: vi.fn() };
});

describe("RequireAuth", () => {
  beforeEach(() => {
    vi.mocked(apiClient.me).mockReset();
  });

  it("redirects to /login when no session exists", async () => {
    vi.mocked(apiClient.me).mockRejectedValue(new apiClient.ApiError(401, "not authenticated"));

    render(
      <MemoryRouter initialEntries={["/app"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login page</div>} />
            <Route
              path="/app"
              element={
                <RequireAuth>
                  <div>Protected content</div>
                </RequireAuth>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("renders protected content once a session is confirmed", async () => {
    vi.mocked(apiClient.me).mockResolvedValue({
      user_id: "u1",
      username: "alice",
      display_name: "Alice",
      email: null,
      permissions: [],
    });

    render(
      <MemoryRouter initialEntries={["/app"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login page</div>} />
            <Route
              path="/app"
              element={
                <RequireAuth>
                  <div>Protected content</div>
                </RequireAuth>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument());
  });
});

describe("RequirePermission", () => {
  beforeEach(() => {
    vi.mocked(apiClient.me).mockReset();
  });

  it("shows an access-denied message when the user lacks the permission", async () => {
    vi.mocked(apiClient.me).mockResolvedValue({
      user_id: "u1",
      username: "alice",
      display_name: "Alice",
      email: null,
      permissions: ["conversation:read"],
    });

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login page</div>} />
            <Route
              path="/admin"
              element={
                <RequirePermission code="system:admin">
                  <div>Admin content</div>
                </RequirePermission>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Access denied")).toBeInTheDocument());
    expect(screen.queryByText("Admin content")).not.toBeInTheDocument();
  });

  it("renders protected content when the user has the permission", async () => {
    vi.mocked(apiClient.me).mockResolvedValue({
      user_id: "u1",
      username: "admin",
      display_name: "Administrator",
      email: null,
      permissions: ["system:admin"],
    });

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/admin"
              element={
                <RequirePermission code="system:admin">
                  <div>Admin content</div>
                </RequirePermission>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Admin content")).toBeInTheDocument());
  });
});
