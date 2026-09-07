import { useState } from "react";

import type { Participant } from "../api/conversations";
import type { KnownSpeaker } from "../api/people";
import type { DetectedSpeaker } from "../api/transcription";
import { Button } from "../design-system/Button";
import { Select, TextInput } from "../design-system/FormControls";
import { speakerColor } from "../lib/speakerColor";
import styles from "./SpeakerAssignRow.module.css";

const CUSTOM_VALUE = "__custom__";
const NONE_VALUE = "";

interface SpeakerAssignRowProps {
  speaker: DetectedSpeaker;
  participants: Participant[];
  knownSpeakers: KnownSpeaker[];
  onAssign: (input: { participantId: string | null; label: string | null }) => void;
  onAcceptSuggestion: () => void;
  onEnroll: (knownSpeakerId: string) => void;
}

export function SpeakerAssignRow({
  speaker,
  participants,
  knownSpeakers,
  onAssign,
  onAcceptSuggestion,
  onEnroll,
}: SpeakerAssignRowProps) {
  const [customMode, setCustomMode] = useState(Boolean(speaker.display_label) && !speaker.participant_id);
  const [customLabel, setCustomLabel] = useState(speaker.display_label ?? "");
  const [enrollTarget, setEnrollTarget] = useState("");

  const suggestedKnownSpeaker = knownSpeakers.find((k) => k.id === speaker.suggested_known_speaker_id);

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

        {suggestedKnownSpeaker && (
          <div className={styles.suggestionRow}>
            <span className={styles.suggestionText}>
              Vorschlag: {suggestedKnownSpeaker.display_name}
              {typeof speaker.suggested_confidence === "number"
                ? ` (${Math.round(speaker.suggested_confidence * 100)}% Übereinstimmung)`
                : ""}
            </span>
            <Button variant="tertiary" type="button" onClick={onAcceptSuggestion}>
              Übernehmen
            </Button>
          </div>
        )}

        {speaker.has_voiceprint && knownSpeakers.length > 0 && (
          <div className={styles.enrollRow}>
            <Select
              aria-label={`${speaker.internal_label} — Stimmprofil zuordnen`}
              value={enrollTarget}
              onChange={(event) => setEnrollTarget(event.target.value)}
            >
              <option value="">Stimmprofil speichern als…</option>
              {knownSpeakers.map((known) => (
                <option key={known.id} value={known.id}>
                  {known.display_name}
                </option>
              ))}
            </Select>
            <Button
              variant="tertiary"
              type="button"
              disabled={!enrollTarget}
              onClick={() => {
                onEnroll(enrollTarget);
                setEnrollTarget("");
              }}
            >
              Speichern
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
