import { FileText, Inbox, Mic, Users } from "lucide-react";
import { useState } from "react";

import { Badge, StatusDot } from "./Badge";
import { Button } from "./Button";
import { Card, StatCard } from "./Card";
import { DataTable, type DataTableColumn } from "./Table";
import styles from "./DesignSystemPage.module.css";
import { Drawer } from "./Drawer";
import { FormField } from "./FormField";
import { Checkbox, Radio, Select, Switch, Textarea, TextInput } from "./FormControls";
import { Modal } from "./Modal";
import { Pagination } from "./Pagination";
import { EmptyState, ErrorState, Skeleton } from "./States";
import { StatusBadge } from "./StatusBadge";
import { TabPanel, Tabs } from "./Tabs";
import { useToast } from "./useToast";

interface DemoRow {
  id: string;
  name: string;
  status: string;
}

const DEMO_ROWS: DemoRow[] = [
  { id: "1", name: "Kardiologische Kontrolle", status: "ready" },
  { id: "2", name: "Aufklärung OP", status: "review_required" },
  { id: "3", name: "Diabetes Verlauf", status: "failed" },
];

const DEMO_COLUMNS: DataTableColumn<DemoRow>[] = [
  { key: "name", header: "Gespräch", render: (row) => row.name, sortable: true, sortValue: (row) => row.name },
  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
];

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
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [switchOn, setSwitchOn] = useState(true);
  const [offset, setOffset] = useState(0);
  const { showToast } = useToast();

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
          <Switch checked={switchOn} onChange={setSwitchOn} aria-label="Beispiel-Switch" />
        </div>
        <div className={styles.row} style={{ marginTop: "var(--space-2)" }}>
          <Textarea placeholder="Textarea" rows={3} />
        </div>
        <div className={styles.row} style={{ maxWidth: 320 }}>
          <FormField label="Titel" hint="Kurzer, beschreibender Titel." required>
            <TextInput placeholder="z. B. Kardiologische Kontrolle" />
          </FormField>
          <FormField label="Externe Referenz" error="Dieses Feld ist erforderlich.">
            <TextInput placeholder="Fallnummer" />
          </FormField>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Cards &amp; Stat Cards</h2>
        <div className={styles.row}>
          <StatCard label="Aktive Gespräche" value={3} icon={<Mic size={18} aria-hidden="true" />} />
          <StatCard
            label="Offene Reviews"
            value={8}
            icon={<Inbox size={18} aria-hidden="true" />}
            hint="warten auf Freigabe"
          />
          <Card title="Beispiel-Karte" actions={<Button variant="tertiary">Alle anzeigen</Button>}>
            <p style={{ color: "var(--text-secondary)", fontSize: "var(--font-body-sm-size)" }}>
              Card-Inhalt mit Titel und Aktion im Header.
            </p>
          </Card>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Tabs</h2>
        <Tabs
          idPrefix="ds-tabs"
          activeId={activeTab}
          onChange={setActiveTab}
          items={[
            { id: "overview", label: "Übersicht" },
            { id: "details", label: "Details" },
          ]}
        />
        <TabPanel id="overview" activeId={activeTab} idPrefix="ds-tabs">
          <p style={{ color: "var(--text-secondary)" }}>Inhalt des Übersicht-Tabs.</p>
        </TabPanel>
        <TabPanel id="details" activeId={activeTab} idPrefix="ds-tabs">
          <p style={{ color: "var(--text-secondary)" }}>Inhalt des Details-Tabs.</p>
        </TabPanel>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Data Table</h2>
        <DataTable columns={DEMO_COLUMNS} rows={DEMO_ROWS} keyExtractor={(row) => row.id} />
        <Pagination offset={offset} limit={3} total={9} onOffsetChange={setOffset} />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Empty / Loading / Error States</h2>
        <div className={styles.row}>
          <div className={styles.card}>
            <EmptyState
              icon={<Inbox size={20} aria-hidden="true" />}
              title="Noch keine Gespräche"
              description="Starten Sie ein neues Gespräch, um loszulegen."
              action={<Button variant="primary">Gespräch starten</Button>}
            />
          </div>
          <div className={styles.card} style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            <Skeleton height="1rem" />
            <Skeleton height="1rem" width="80%" />
            <Skeleton height="1rem" width="60%" />
          </div>
          <div className={styles.card}>
            <ErrorState message="Transkription fehlgeschlagen." onRetry={() => undefined} />
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Modal, Drawer &amp; Toast</h2>
        <div className={styles.row}>
          <Button variant="secondary" onClick={() => setModalOpen(true)}>
            Modal öffnen
          </Button>
          <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
            Drawer öffnen
          </Button>
          <Button variant="secondary" onClick={() => showToast("success", "Erfolgreich gespeichert.")}>
            Erfolgs-Toast
          </Button>
          <Button variant="secondary" onClick={() => showToast("error", "Etwas ist schiefgelaufen.")}>
            Fehler-Toast
          </Button>
        </div>
        <Modal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Beispiel-Dialog"
          footer={
            <>
              <Button variant="tertiary" onClick={() => setModalOpen(false)}>
                Abbrechen
              </Button>
              <Button variant="primary" onClick={() => setModalOpen(false)}>
                Bestätigen
              </Button>
            </>
          }
        >
          <p>Kurzer Bestätigungsdialog-Inhalt.</p>
        </Modal>
        <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Beispiel-Drawer">
          <p style={{ color: "var(--text-secondary)" }}>Seitliches Panel für Detailinformationen.</p>
        </Drawer>
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
        <p style={{ color: "var(--text-muted)", marginTop: "var(--space-2)" }}>StatusBadge (app status vocabulary)</p>
        <div className={styles.row} style={{ alignItems: "center" }}>
          <StatusBadge status="recording" />
          <StatusBadge status="normalizing" />
          <StatusBadge status="ready" />
          <StatusBadge status="review_required" />
          <StatusBadge status="approved" />
          <StatusBadge status="failed" />
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
