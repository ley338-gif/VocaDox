import { useQuery } from "@tanstack/react-query";
import { Mic, Upload } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../api/client";
import type { ConversationType, PrivacyMode } from "../api/conversations";
import { createConversation, uploadMedia } from "../api/conversations";
import { listMyOrganizations } from "../api/organizations";
import { listProcessingProfiles } from "../api/profiles";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { Checkbox, Select, TextInput } from "../design-system/FormControls";
import styles from "./NewConversationPage.module.css";

type Mode = "record" | "upload";

export function NewConversationPage() {
  const navigate = useNavigate();
  const { csrfToken } = useAuth();
  const [mode, setMode] = useState<Mode | null>(null);
  const [title, setTitle] = useState("");
  const [conversationType, setConversationType] = useState<ConversationType>("general");
  const [organizationId, setOrganizationId] = useState("");
  const [processingProfileId, setProcessingProfileId] = useState("");
  const [externalReference, setExternalReference] = useState("");
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>("standard");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError(submitError instanceof ApiError ? submitError.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", marginBottom: "var(--space-6)" }}>
        New conversation
      </h1>

      <div className={styles.choiceRow}>
        <button
          type="button"
          className={`${styles.choiceCard} ${mode === "record" ? styles.selected : ""}`}
          onClick={() => setMode("record")}
        >
          <Mic size={24} aria-hidden="true" />
          <h3>Start recording</h3>
          <p style={{ color: "var(--text-muted)" }}>
            Record directly in the browser using your microphone.
          </p>
        </button>
        <button
          type="button"
          className={`${styles.choiceCard} ${mode === "upload" ? styles.selected : ""}`}
          onClick={() => setMode("upload")}
        >
          <Upload size={24} aria-hidden="true" />
          <h3>Upload audio</h3>
          <p style={{ color: "var(--text-muted)" }}>
            Upload an existing audio file (WebM, WAV, MP3, or M4A).
          </p>
        </button>
      </div>

      {mode && (
        <div className={styles.form}>
          <div className={styles.field}>
            <label htmlFor="title">Title</label>
            <TextInput
              id="title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="org">Organization</label>
            <Select
              id="org"
              value={organizationId}
              onChange={(event) => setOrganizationId(event.target.value)}
              required
            >
              <option value="">Select an organization…</option>
              {organizations?.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </Select>
          </div>

          <div className={styles.field}>
            <label htmlFor="type">Conversation type</label>
            <Select
              id="type"
              value={conversationType}
              onChange={(event) => setConversationType(event.target.value as ConversationType)}
            >
              <option value="general">General</option>
              <option value="medical">Medical</option>
              <option value="therapy">Therapy</option>
              <option value="meeting">Meeting</option>
              <option value="interview">Interview</option>
              <option value="other">Other</option>
            </Select>
          </div>

          <div className={styles.field}>
            <label htmlFor="profile">Processing profile</label>
            <Select
              id="profile"
              value={processingProfileId}
              onChange={(event) => setProcessingProfileId(event.target.value)}
            >
              <option value="">General (default)</option>
              {selectableProfiles
                .filter((p) => !p.is_system_default)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </Select>
          </div>

          <div className={styles.field}>
            <label htmlFor="externalRef">External reference (optional)</label>
            <TextInput
              id="externalRef"
              value={externalReference}
              onChange={(event) => setExternalReference(event.target.value)}
            />
          </div>

          <div className={styles.field}>
            <label>
              <Checkbox
                checked={privacyMode === "restricted"}
                onChange={(event) => setPrivacyMode(event.target.checked ? "restricted" : "standard")}
              />{" "}
              Mark as restricted privacy
            </label>
          </div>

          {mode === "upload" && (
            <div className={styles.field}>
              <label htmlFor="file">Audio file</label>
              <input
                id="file"
                type="file"
                accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,.webm,.wav,.mp3,.m4a"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </div>
          )}

          {error && <p role="alert">{error}</p>}

          <Button
            variant="primary"
            type="button"
            disabled={submitting || !title.trim() || !organizationId || (mode === "upload" && !file)}
            onClick={() => void handleCreate()}
          >
            {mode === "record" ? "Continue to recording" : "Create and upload"}
          </Button>
        </div>
      )}
    </div>
  );
}
