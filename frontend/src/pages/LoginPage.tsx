import { useState } from "react";
import type { FormEvent } from "react";
import type { Location } from "react-router";
import { Navigate, useLocation } from "react-router";

import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { TextInput } from "../design-system/FormControls";
import styles from "./LoginPage.module.css";

export function LoginPage() {
  const { user, login } = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fromLocation = (location.state as { from?: Location } | null)?.from;
  const redirectTo = fromLocation ? fromLocation.pathname + fromLocation.search : "/app";

  if (user) {
    return <Navigate to={redirectTo} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
    } catch {
      // Deliberately generic — the backend returns the same message for
      // "unknown user" and "wrong password" to avoid username enumeration.
      setError("Invalid username or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <h1 className={styles.title}>Sign in to VocaDox</h1>

        <label className={styles.field}>
          <span className={styles.label}>Username</span>
          <TextInput
            autoFocus
            autoComplete="username"
            style={{ width: "100%" }}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Password</span>
          <TextInput
            type="password"
            autoComplete="current-password"
            style={{ width: "100%" }}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <p className={styles.error}>{error}</p>}

        <Button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
