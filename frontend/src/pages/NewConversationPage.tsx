import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Mic, Upload } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { ApiError } from "../api/client";
import type { ConversationType, PrivacyMode } from "../api/conversations";
import { createConversation, uploadMedia } from "../api/conversations";
import { listMyOrganizations } from "../api/organizations";
import { listProcessingProfiles } from "../api/profiles";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { FormField } from "../design-system/FormField";
import { Checkbox, Select, TextInput } from "../design-system/FormControls";
import { ErrorState } from "../design-system/States";
import { type CalendarEvent, parseIcs, upcomingEvents } from "../lib/icsParser";
import styles from "./NewConversationPage.module.css";

type Mode = "record" | "upload";

function formatEventTime(date: Date): string {
  return date.toLocaleString("de-DE", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function NewConversationPage() {
  const navigate = useNavigate();
  const { csrfToken, user } = useAuth();
  const [searchParams] = useSearchParams();
  const initialMode = searchParams.get("mode");
  const [mode, setMode] = useState<Mode | null>(
    initialMode === "record" || initialMode === "upload" ? initialMode : null
  );
  const [title, setTitle] = useState("");
  const [conversationType, setConversationType] = useState<ConversationType>("general");
  const [organizationId, setOrganizationId] = useState("");
  const [processingProfileId, setProcessingProfileId] = useState("");
  const [externalReference, setExternalReference] = useState("");
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>("standard");
  // Post-GA team-scoped visibility: pre-select if the user has exactly one
  // team, otherwise leave unselected (-> org-wide/no-team, today's
  // behavior) rather than forcing a choice on someone with no team yet.
  const myGroups = user?.groups ?? [];
  const [groupId, setGroupId] = useState(() => (myGroups.length === 1 ? myGroups[0].id : ""));
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Post-GA P2-2 "Kalender-Automatik": parsed entirely client-side from a
  // locally-picked .ics file — no calendar data ever reaches the backend
  // until the user explicitly creates a conversation, and no runtime
  // network call or account/secret is involved at all (see
  // docs/architecture/adr/0037-calendar-ics-import.md).
  const [showCalendarImport, setShowCalendarImport] = useState(false);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [selectedEventUid, setSelectedEventUid] = useState<string | null>(null);

  function handleIcsFile(icsFile: File | undefined) {
    setCalendarError(null);
    setCalendarEvents([]);
    setSelectedEventUid(null);
    if (!icsFile) return;
    icsFile
      .text()
      .then((text) => {
        const events = upcomingEvents(parseIcs(text));
        if (events.length === 0) {
          setCalendarError(
            "Keine bevorstehenden Termine in dieser Datei gefunden (nur Termine der " +
              "nächsten 30 Tage werden angezeigt)."
          );
          return;
        }
        setCalendarEvents(events);
      })
      .catch(() => setCalendarError("Datei konnte nicht als Kalenderdatei (.ics) gelesen werden."));
  }

  function handleSelectEvent(event: CalendarEvent) {
    setSelectedEventUid(event.uid);
    setTitle(event.summary);
    setConversationType("meeting");
    setMode("record");
  }

  const { data: organizations } = useQuery({
    queryKey: ["organizations"],
    queryFn: listMyOrganizations,
  });
  // Phase 6 (spec §19): "User sieht verständliche Namen" — a plain list of
  // published, enabled Processing Profiles the user can pick by friendly
  // name. Never shown the underlying template/model/prompt composition.
  const { data: processingProfiles } = useQuery({
    queryKey: ["processing-profiles"],
    queryFn: listProcessingProfiles,
  });
  const selectableProfiles = (processingProfiles ?? []).filter(
    (p) => p.enabled && p.current_published_version_id !== null
  );

  async function handleCreate() {
    if (!csrfToken || !organizationId || !title.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const conversation = await createConversation(
        {
          title: title.trim(),
          organization_id: organizationId,
          conversation_type: conversationType,
          external_reference: externalReference || undefined,
          privacy_mode: privacyMode,
          processing_profile_id: processingProfileId || undefined,
          group_id: groupId || undefined,
        },
        csrfToken
      );

      if (mode === "upload" && file) {
        try {
          await uploadMedia(conversation.id, file, csrfToken);
        } catch {
          // The conversation itself was created successfully; surface the
          // upload failure but still route to the detail page so the user
          // can retry the upload from there instead of losing the
          // conversation they just created.
          navigate(`/app/conversations/${conversation.id}`);
          return;
        }
      }
      navigate(`/app/conversations/${conversation.id}`, {
        state: { startRecording: mode === "record" },
      });
    } catch (submitError) {
      setError(submitError instanceof ApiError ? submitError.message : "Etwas ist schiefgelaufen.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", marginBottom: "var(--space-6)" }}>Neues Gespräch</h1>

      <div className={styles.choiceRow}>
        <button
          type="button"
          className={`${styles.choiceCard} ${mode === "record" ? styles.selected : ""}`}
          onClick={() => setMode("record")}
        >
          <Mic size={24} aria-hidden="true" />
          <h3>Aufnahme starten</h3>
          <p style={{ color: "var(--text-muted)" }}>Direkt im Browser über das Mikrofon aufnehmen.</p>
        </button>
        <button
          type="button"
          className={`${styles.choiceCard} ${mode === "upload" ? styles.selected : ""}`}
          onClick={() => setMode("upload")}
        >
          <Upload size={24} aria-hidden="true" />
          <h3>Audio hochladen</h3>
          <p style={{ color: "var(--text-muted)" }}>Eine vorhandene Audiodatei hochladen (WebM, WAV, MP3, M4A).</p>
        </button>
        <button
          type="button"
          className={`${styles.choiceCard} ${showCalendarImport ? styles.selected : ""}`}
          onClick={() => setShowCalendarImport(true)}
        >
          <CalendarDays size={24} aria-hidden="true" />
          <h3>Aus Kalender übernehmen</h3>
          <p style={{ color: "var(--text-muted)" }}>
            Titel aus einer Kalenderdatei (.ics) für einen bevorstehenden Termin übernehmen.
          </p>
        </button>
      </div>

      {showCalendarImport && (
        <div className={styles.form} style={{ marginBottom: "var(--space-6)" }}>
          <FormField label="Kalenderdatei (.ics)">
            <input
              type="file"
              accept=".ics,text/calendar"
              onChange={(event) => handleIcsFile(event.target.files?.[0])}
            />
          </FormField>
          <p style={{ color: "var(--text-muted)", fontSize: "var(--font-body-sm-size)" }}>
            Wird ausschließlich lokal in Ihrem Browser gelesen — nichts aus der Kalenderdatei wird
            übertragen, bevor Sie unten ein Gespräch erstellen.
          </p>
          {calendarError && <ErrorState message={calendarError} />}
          {calendarEvents.length > 0 && (
            <ul className={styles.calendarEventList}>
              {calendarEvents.map((event) => (
                <li key={event.uid}>
                  <button
                    type="button"
                    className={`${styles.calendarEventItem} ${
                      selectedEventUid === event.uid ? styles.selected : ""
                    }`}
                    onClick={() => handleSelectEvent(event)}
                  >
                    <strong>{event.summary}</strong>
                    <span>{formatEventTime(event.start)}</span>
                    {event.location && <span>{event.location}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {mode && (
        <div className={styles.form}>
          <FormField label="Titel" required>
            <TextInput value={title} onChange={(event) => setTitle(event.target.value)} required />
          </FormField>

          <FormField label="Organisation" required>
            <Select value={organizationId} onChange={(event) => setOrganizationId(event.target.value)} required>
              <option value="">Organisation wählen…</option>
              {organizations?.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </Select>
          </FormField>

          {myGroups.length > 0 && (
            <FormField label="Team (optional)">
              <Select value={groupId} onChange={(event) => setGroupId(event.target.value)}>
                <option value="">Kein Team — für die ganze Organisation sichtbar</option>
                {myGroups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </Select>
            </FormField>
          )}

          <FormField label="Gesprächstyp">
            <Select
              value={conversationType}
              onChange={(event) => setConversationType(event.target.value as ConversationType)}
            >
              <option value="general">Allgemein</option>
              <option value="medical">Medizinisch</option>
              <option value="therapy">Therapie</option>
              <option value="meeting">Meeting</option>
              <option value="interview">Interview</option>
              <option value="other">Sonstiges</option>
            </Select>
          </FormField>

          <FormField label="Verarbeitungsprofil">
            <Select value={processingProfileId} onChange={(event) => setProcessingProfileId(event.target.value)}>
              <option value="">Allgemein (Standard)</option>
              {selectableProfiles
                .filter((p) => !p.is_system_default)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </Select>
          </FormField>

          <FormField label="Externe Referenz (optional)">
            <TextInput value={externalReference} onChange={(event) => setExternalReference(event.target.value)} />
          </FormField>

          <div className={styles.field}>
            <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <Checkbox
                checked={privacyMode === "restricted"}
                onChange={(event) => setPrivacyMode(event.target.checked ? "restricted" : "standard")}
              />
              Als eingeschränkt (restricted) markieren
            </label>
          </div>

          {mode === "upload" && (
            <FormField label="Audiodatei">
              <input
                type="file"
                accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,.webm,.wav,.mp3,.m4a"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </FormField>
          )}

          {error && <ErrorState message={error} />}

          <Button
            variant="primary"
            type="button"
            disabled={submitting || !title.trim() || !organizationId || (mode === "upload" && !file)}
            onClick={() => void handleCreate()}
          >
            {mode === "record" ? "Weiter zur Aufnahme" : "Erstellen und hochladen"}
          </Button>
        </div>
      )}
    </div>
  );
}
