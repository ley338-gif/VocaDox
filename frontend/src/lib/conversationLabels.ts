import type { ConversationType } from "../api/conversations";

export const CONVERSATION_TYPE_LABELS: Record<ConversationType, string> = {
  general: "Allgemein",
  medical: "Medizinisch",
  therapy: "Therapie",
  meeting: "Meeting",
  interview: "Interview",
  other: "Sonstiges",
};
