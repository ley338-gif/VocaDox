export function HomePage() {
  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        VocaDox — Phase 0 scaffold
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        This is an architecture &amp; foundation scaffold. No domain features
        (conversations, transcription, ...) are implemented yet. See{" "}
        <a href="/design-system">/design-system</a> for the living style
        guide, or the project README for the full roadmap.
      </p>
    </div>
  );
}
