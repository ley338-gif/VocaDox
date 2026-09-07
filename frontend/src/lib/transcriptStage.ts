/**
 * Real progress stages derived from actual ProcessingJob rows — a stage
 * indicator, not a fabricated percentage. Shared between TranscriptPanel
 * (Transkript tab) and ConversationDetailPage (Übersicht tab) so both
 * agree on what "still processing" means.
 */
import type { ProcessingJob } from "../api/transcription";

export type Stage = "idle" | "preparing" | "transcribing" | "diarizing" | "aligning" | "ready" | "failed";

export function stageFromJobs(jobs: ProcessingJob[], transcriptStatus: string | undefined): Stage {
  if (transcriptStatus === "ready") return "ready";
  if (transcriptStatus === "failed") return "failed";
  if (jobs.length === 0) return "idle";
  // A real failure is a job that actually reports status "failed" -- NOT
  // merely "no job is queued/running right now". The pipeline enqueues
  // normalize -> transcribe -> diarize -> align one at a time, so there is
  // a real, brief gap between one job succeeding and the next one being
  // created where NONE is active yet everything is fine; misreading that
  // gap as "failed" was a real bug (a spurious "Transkription
  // fehlgeschlagen" flash that self-corrected on the next poll/reload).
  if (jobs.some((j) => j.status === "failed")) return "failed";
  // `jobs` is ordered by queued_at DESC (see GET .../process/status), so
  // jobs[0] is the most recently queued/created job -- during the gap
  // above, that's still the best signal for "how far did we get".
  const active = jobs.find((j) => j.status === "queued" || j.status === "running") ?? jobs[0];
  switch (active.job_type) {
    case "normalize":
      return "preparing";
    case "transcribe":
      return "transcribing";
    case "diarize":
      return "diarizing";
    case "align":
      return "aligning";
    default:
      return "preparing";
  }
}

export const STAGE_LABELS: Record<Stage, string> = {
  idle: "Nicht gestartet",
  preparing: "Audio wird vorbereitet…",
  transcribing: "Transkription läuft…",
  diarizing: "Sprechererkennung läuft…",
  aligning: "Transkript wird ausgerichtet…",
  ready: "Bereit",
  failed: "Fehlgeschlagen",
};
