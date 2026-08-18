import { useNavigate } from "react-router";

import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";

/**
 * Placeholder home for the future `/app` user workspace (Dashboard,
 * Conversations, ... land in later phases — see
 * docs/architecture/domain-model.md). Phase 1 only needs a logged-in
 * shell state and a working logout action.
 */
export function AppHomePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Welcome, {user?.displayName}
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        You are signed in as <strong>{user?.username}</strong>. The full
        conversation workspace (recording, review, documents, ...) ships in
        later phases.
      </p>
      <div style={{ marginTop: "var(--space-6)" }}>
        <Button variant="secondary" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </div>
  );
}
