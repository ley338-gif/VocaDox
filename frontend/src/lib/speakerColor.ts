/**
 * Stable speaker → color assignment (brief §5/§19: Blau/Violett/Grün/
 * Orange/Türkis, no neon). A simple string hash over a stable key
 * (DetectedSpeaker.internal_label, e.g. "SPEAKER_00") picks one of 5
 * fixed token colors, so the same speaker always renders the same color
 * everywhere (transcript turns, chips, future waveform segments) without
 * needing a lookup table kept in sync across components.
 */
const SPEAKER_PALETTE = [
  "var(--color-primary-600)", // Blau
  "var(--color-purple)", // Violett
  "var(--color-success)", // Grün
  "var(--color-warning)", // Orange
  "var(--color-teal)", // Türkis
] as const;

export function speakerColor(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  const index = Math.abs(hash) % SPEAKER_PALETTE.length;
  return SPEAKER_PALETTE[index];
}
