import { useState } from "react";

import type { Participant } from "../api/conversations";
import type { DetectedSpeaker } from "../api/transcription";
import { Select, TextInput } from "../design-system/FormControls";
import { speakerColor } from "../lib/speakerColor";
import styles from "./SpeakerAssignRow.module.css";

const CUSTOM_VALUE = "__custom__";
const NONE_VALUE = "";

interface SpeakerAssignRowProps {
  speaker: DetectedSpeaker;
  participants: Participant[];
  onAssign: (input: { participantId: string | null; label: string | null }) => void;
}

export function SpeakerAssignRow({ speaker, participants, onAssign }: SpeakerAssignRowProps) {
  const [customMode, setCustomMode] = useState(Boolean(speaker.display_label) && !speaker.participant_id);
  const [customLabel, setCustomLabel] = useState(speaker.display_label ?? "");

  return (
    <div className={styles.row}>
      <span
        className={styles.dot}
        style={{ background: speakerColor(speaker.internal_label) }}
        aria-hidden="true"
      />
      <div className={styles.controls}>
        <Select
          aria-label={`${speaker.internal_label} — Teilnehmer zuordnen`}
          value={customMode ? CUSTOM_VALUE : (speaker.participant_id ?? NONE_VALUE)}
          onChange={(event) => {
            const value = event.target.value;
            if (value === CUSTOM_VALUE) {
              setCustomMode(true);
              return;
            }
            setCustomMode(false);
            const participant = participants.find((p) => p.id === value);
            onAssign({ participantId: value || null, label: participant?.display_name ?? null });
          }}
        >
          <option value={NONE_VALUE}>{speaker.internal_label}</option>
          {participants.map((participant) => (
            <option key={participant.id} value={participant.id}>
              {participant.display_name}
            </option>
          ))}
          <option value={CUSTOM_VALUE}>Manuell eingeben…</option>
        </Select>
        {customMode && (
          <TextInput
            aria-label={`${speaker.internal_label} — Name eingeben`}
            placeholder={speaker.internal_label}
            value={customLabel}
            onChange={(event) => setCustomLabel(event.target.value)}
            onBlur={() => onAssign({ participantId: null, label: customLabel || null })}
          />
        )}
      </div>
    </div>
  );
}
