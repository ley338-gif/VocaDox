import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { LoginPage } from "./LoginPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof apiClient>();
  return { ...actual, me: vi.fn(), login: vi.fn() };
});

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/app" element={<div>App home</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.mocked(apiClient.me).mockRejectedValue(new apiClient.ApiError(401, "not authenticated"));
    vi.mocked(apiClient.login).mockReset();
  });

  it("shows a generic error on invalid credentials, without leaking a reason", async () => {
    vi.mocked(apiClient.login).mockRejectedValue(new apiClient.ApiError(401, "invalid credentials"));

    renderLoginPage();
    await waitFor(() => expect(screen.getByLabelText("Username")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText("Invalid username or password.")).toBeInTheDocument()
    );
  });

  it("navigates to /app after a successful login", async () => {
    vi.mocked(apiClient.login).mockResolvedValue({
      user_id: "u1",
      username: "alice",
      display_name: "Alice",
      csrf_token: "token123",
    });
    // First call is the AuthProvider's on-mount "do I already have a
    // session?" probe — must fail so the login form actually renders;
    // subsequent calls (triggered by a successful login) resolve.
    vi.mocked(apiClient.me)
      .mockRejectedValueOnce(new apiClient.ApiError(401, "not authenticated"))
      .mockResolvedValue({
        user_id: "u1",
        username: "alice",
        display_name: "Alice",
        email: null,
        permissions: [],
      });

    renderLoginPage();
    await waitFor(() => expect(screen.getByLabelText("Username")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText("App home")).toBeInTheDocument());
  });
});
