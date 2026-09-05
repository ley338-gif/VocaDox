import { useNavigate } from "react-router";

import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";

/**
 * `/app` landing page. Was a Phase-1 placeholder ("the full conversation
 * workspace ships in later phases") that never got updated once those
 * phases actually shipped — found stale during a post-GA manual
 * walkthrough. Real quick links only; no dashboard content duplicated
 * from `/admin` (that's the admin's own Dashboard page).
 */
export function AppHomePage() {
  const { user, hasPermission, logout } = useAuth();
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
        Signed in as <strong>{user?.username}</strong>.
      </p>
      <div
        style={{
          marginTop: "var(--space-6)",
          display: "flex",
          gap: "var(--space-3)",
          flexWrap: "wrap",
        }}
      >
        <Button onClick={() => navigate("/app/conversations/new")}>New conversation</Button>
        <Button variant="secondary" onClick={() => navigate("/app/conversations")}>
          View conversations
        </Button>
        {hasPermission("system:admin") && (
          <Button variant="secondary" onClick={() => navigate("/admin")}>
            Admin portal
          </Button>
        )}
        <Button variant="tertiary" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </div>
  );
}
