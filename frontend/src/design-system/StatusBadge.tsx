/**
 * Central status-vocabulary → {label, tone} mapping used across the app
 * (Conversation/Transcript/Document/ProcessingJob/FollowUpTask status
 * strings all funnel through here) so the same status always renders with
 * the same color/label everywhere, instead of each page mapping tones ad hoc.
 */
import { Badge } from "./Badge";

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "purple" | "teal";

const STATUS_MAP: Record<string, { label: string; tone: Tone }> = {
  // Conversation
  created: { label: "Erstellt", tone: "neutral" },
  recording: { label: "Aufnahme läuft", tone: "info" },
  uploaded: { label: "Hochgeladen", tone: "info" },
  normalizing: { label: "Verarbeitung", tone: "info" },
  ready: { label: "Bereit", tone: "success" },
  failed: { label: "Fehler", tone: "danger" },
  deleted: { label: "Gelöscht", tone: "neutral" },
  // Transcript
  pending: { label: "Ausstehend", tone: "neutral" },
  processing: { label: "Verarbeitung", tone: "info" },
  // Document / review
  draft: { label: "Entwurf", tone: "neutral" },
  review_required: { label: "Review nötig", tone: "warning" },
  ready_for_approval: { label: "Freigabe ausstehend", tone: "info" },
  approved: { label: "Freigegeben", tone: "success" },
  published: { label: "Veröffentlicht", tone: "success" },
  retired: { label: "Zurückgezogen", tone: "neutral" },
  // ProcessingJob
  queued: { label: "Wartend", tone: "neutral" },
  running: { label: "Läuft", tone: "info" },
  succeeded: { label: "Erfolgreich", tone: "success" },
  cancelled: { label: "Abgebrochen", tone: "neutral" },
  // FollowUpTask
  open: { label: "Offen", tone: "warning" },
  done: { label: "Erledigt", tone: "success" },
  dismissed: { label: "Verworfen", tone: "neutral" },
  // Review issue severity
  low: { label: "Niedrig", tone: "neutral" },
  medium: { label: "Mittel", tone: "warning" },
  high: { label: "Hoch", tone: "danger" },
  critical: { label: "Kritisch", tone: "danger" },
  // ModelProfile lifecycle (AVAILABLE -> TESTING -> PILOT -> PRODUCTION -> RETIRED)
  available: { label: "Verfügbar", tone: "neutral" },
  testing: { label: "Testphase", tone: "info" },
  pilot: { label: "Pilot", tone: "warning" },
  production: { label: "Produktion", tone: "success" },
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const entry = STATUS_MAP[status];
  return <Badge tone={entry?.tone ?? "neutral"}>{label ?? entry?.label ?? status}</Badge>;
}
