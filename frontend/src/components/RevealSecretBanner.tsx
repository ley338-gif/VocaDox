import { Button } from "../design-system/Button";

/**
 * The "show a secret exactly once, right after creation/rotation" banner
 * — used by AdminServiceAccountsPage (API key) and AdminWebhooksPage
 * (signing secret), previously two copy-pasted implementations of the
 * exact same markup/inline styles with only the label/field name
 * differing. Never persisted/re-shown after this render — callers own
 * clearing their `revealed` state via `onClose`.
 */
export function RevealSecretBanner({
  label,
  value,
  onClose,
}: {
  label: string;
  value: string;
  onClose: () => void;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--color-warning)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4)",
        marginBottom: "var(--space-4)",
        background: "color-mix(in srgb, var(--color-warning) 10%, var(--surface-raised))",
      }}
    >
      <strong>{label} — jetzt kopieren, er wird nicht erneut angezeigt:</strong>
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
        <code
          style={{
            flex: 1,
            padding: "var(--space-2)",
            background: "var(--surface-sunken)",
            borderRadius: "var(--radius-sm)",
            overflowWrap: "anywhere",
          }}
        >
          {value}
        </code>
        <Button variant="secondary" onClick={() => navigator.clipboard.writeText(value)}>
          Kopieren
        </Button>
        <Button variant="secondary" onClick={onClose}>
          Schließen
        </Button>
      </div>
    </div>
  );
}
