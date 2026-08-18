import { FileText, Mic, Users } from "lucide-react";

import { Badge, StatusDot } from "./Badge";
import { Button } from "./Button";
import styles from "./DesignSystemPage.module.css";
import { Checkbox, Radio, Select, TextInput } from "./FormControls";

const COLOR_GROUPS: Array<{ name: string; colors: Array<[string, string]> }> = [
  {
    name: "Primary",
    colors: [
      ["600", "var(--color-primary-600)"],
      ["500", "var(--color-primary-500)"],
      ["400", "var(--color-primary-400)"],
      ["300", "var(--color-primary-300)"],
      ["100", "var(--color-primary-100)"],
    ],
  },
  {
    name: "Gray",
    colors: [
      ["900", "var(--color-gray-900)"],
      ["800", "var(--color-gray-800)"],
      ["700", "var(--color-gray-700)"],
      ["500", "var(--color-gray-500)"],
      ["300", "var(--color-gray-300)"],
      ["200", "var(--color-gray-200)"],
      ["100", "var(--color-gray-100)"],
      ["White", "var(--color-white)"],
    ],
  },
  {
    name: "Semantic",
    colors: [
      ["Success", "var(--color-success)"],
      ["Warning", "var(--color-warning)"],
      ["Danger", "var(--color-danger)"],
      ["Info", "var(--color-info)"],
      ["Purple", "var(--color-purple)"],
      ["Teal", "var(--color-teal)"],
    ],
  },
];

const TYPE_SCALE: Array<[string, string, string]> = [
  ["H1", "var(--font-h1-size)", "var(--font-h1-line)"],
  ["H2", "var(--font-h2-size)", "var(--font-h2-line)"],
  ["H3", "var(--font-h3-size)", "var(--font-h3-line)"],
  ["H4", "var(--font-h4-size)", "var(--font-h4-line)"],
  ["H5", "var(--font-h5-size)", "var(--font-h5-line)"],
  ["H6", "var(--font-h6-size)", "var(--font-h6-line)"],
  ["Body Large", "var(--font-body-lg-size)", "var(--font-body-lg-line)"],
  ["Body Base", "var(--font-body-base-size)", "var(--font-body-base-line)"],
  ["Body Small", "var(--font-body-sm-size)", "var(--font-body-sm-line)"],
  ["Caption", "var(--font-caption-size)", "var(--font-caption-line)"],
];

const SPACING = [4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96];
const RADII: Array<[string, string]> = [
  ["sm (4px)", "var(--radius-sm)"],
  ["md (8px)", "var(--radius-md)"],
  ["lg (12px)", "var(--radius-lg)"],
  ["xl (16px)", "var(--radius-xl)"],
  ["2xl (24px)", "var(--radius-2xl)"],
];
const SHADOWS: Array<[string, string]> = [
  ["sm", "var(--shadow-sm)"],
  ["md", "var(--shadow-md)"],
  ["lg", "var(--shadow-lg)"],
  ["xl", "var(--shadow-xl)"],
];

export function DesignSystemPage() {
  return (
    <div className={styles.page}>
      <div>
        <h1 className={styles.sectionTitle}>Design System</h1>
        <p style={{ color: "var(--text-secondary)" }}>
          Living style guide — tokens and components rendered from the same
          CSS variables the app uses. Source: "VocaDox - Stylesystem.png".
        </p>
      </div>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Colors</h2>
        {COLOR_GROUPS.map((group) => (
          <div key={group.name}>
            <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-2)" }}>
              {group.name}
            </p>
            <div className={styles.row}>
              {group.colors.map(([label, value]) => (
                <div className={styles.swatch} key={label}>
                  <div className={styles.swatchBlock} style={{ background: value }} />
                  <span className={styles.swatchLabel}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Typography</h2>
        {TYPE_SCALE.map(([label, size, line]) => (
          <div className={styles.typeSample} key={label}>
            <span className={styles.typeName}>{label}</span>
            <span style={{ fontSize: size, lineHeight: line }}>The quick brown fox — Ramipril 5mg</span>
          </div>
        ))}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Spacing (8pt scale)</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {SPACING.map((px) => (
            <div key={px} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
              <span style={{ width: 48, color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
                {px}px
              </span>
              <div className={styles.spaceBar} style={{ width: px }} />
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Border Radius</h2>
        <div className={styles.row}>
          {RADII.map(([label, value]) => (
            <div className={styles.swatch} key={label}>
              <div
                className={styles.swatchBlock}
                style={{ background: "var(--accent-subtle)", borderRadius: value }}
              />
              <span className={styles.swatchLabel}>{label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Shadows</h2>
        <div className={styles.row}>
          {SHADOWS.map(([label, value]) => (
            <div className={styles.swatch} key={label}>
              <div
                className={styles.swatchBlock}
                style={{ background: "var(--surface-raised)", boxShadow: value }}
              />
              <span className={styles.swatchLabel}>{label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Icons (Lucide)</h2>
        <div className={styles.row} style={{ color: "var(--text-secondary)" }}>
          <Mic size={24} />
          <Users size={24} />
          <FileText size={24} />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Buttons</h2>
        <div className={styles.row}>
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="tertiary">Tertiary</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Form Controls</h2>
        <div className={styles.row} style={{ alignItems: "center" }}>
          <TextInput placeholder="Text input" />
          <TextInput placeholder="Disabled" disabled />
          <Select defaultValue="">
            <option value="" disabled>
              Select…
            </option>
            <option value="a">Option A</option>
            <option value="b">Option B</option>
          </Select>
          <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <Checkbox defaultChecked /> Checkbox
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <Radio name="ds-radio" defaultChecked /> Radio
          </label>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Badges / Tags / Status</h2>
        <div className={styles.row} style={{ alignItems: "center" }}>
          <Badge tone="neutral">Neutral</Badge>
          <Badge tone="success">Success</Badge>
          <Badge tone="warning">Warning</Badge>
          <Badge tone="danger">Danger</Badge>
          <Badge tone="info">Info</Badge>
          <Badge tone="purple">Purple</Badge>
          <Badge tone="teal">Teal</Badge>
          <StatusDot tone="success" /> <StatusDot tone="warning" /> <StatusDot tone="danger" />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Cards &amp; List Items</h2>
        <div className={styles.row}>
          <div className={styles.card}>
            <p style={{ fontWeight: 600 }}>Example Card</p>
            <p style={{ color: "var(--text-secondary)", fontSize: "var(--font-body-sm-size)" }}>
              Card body content with elevation from --shadow-sm.
            </p>
          </div>
          <div className={styles.card}>
            <div className={styles.listItem} style={{ padding: 0, border: "none" }}>
              <StatusDot tone="success" />
              <span>Conversation processed</span>
            </div>
            <div className={styles.listItem} style={{ padding: 0, border: "none", marginTop: 8 }}>
              <StatusDot tone="warning" />
              <span>Review pending</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
