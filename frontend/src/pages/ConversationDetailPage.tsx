import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";

import {
  addMarker,
  addNote,
  addParticipant,
  deleteConversation,
  deleteMarker,
  deleteNote,
  deleteParticipant,
  getConversation,
  listMarkers,
  listMedia,
  listNotes,
  listParticipants,
  mediaContentUrl,
  uploadMedia,
} from "../api/conversations";
import { useAuth } from "../auth/useAuth";
import { AudioPlayer, type AudioPlayerHandle } from "../components/AudioPlayer";
import { FactsPanel } from "../components/FactsPanel";
import { RecordingWorkspace } from "../components/RecordingWorkspace";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Select, TextInput } from "../design-system/FormControls";
import styles from "./ConversationDetailPage.module.css";

type Tab = "overview" | "audio" | "transcript" | "facts" | "participants" | "notes" | "activity";

export function ConversationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation() as { state?: { startRecording?: boolean } };
  const navigate = useNavigate();
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>(location.state?.startRecording ? "audio" : "overview");
  const [showRecorder, setShowRecorder] = useState(Boolean(location.state?.startRecording));
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const [activeMs, setActiveMs] = useState(0);

  const conversationId = id ?? "";

  const conversationQuery = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => getConversation(conversationId),
    enabled: Boolean(conversationId),
  });
  const mediaQuery = useQuery({
    queryKey: ["conversation-media", conversationId],
    queryFn: () => listMedia(conversationId),
    enabled: Boolean(conversationId),
  });
  const participantsQuery = useQuery({
    queryKey: ["conversation-participants", conversationId],
    queryFn: () => listParticipants(conversationId),
    enabled: Boolean(conversationId),
  });
  const markersQuery = useQuery({
    queryKey: ["conversation-markers", conversationId],
    queryFn: () => listMarkers(conversationId),
    enabled: Boolean(conversationId),
  });
  const notesQuery = useQuery({
    queryKey: ["conversation-notes", conversationId],
    queryFn: () => listNotes(conversationId),
    enabled: Boolean(conversationId),
  });

  const [participantName, setParticipantName] = useState("");
  const [participantType, setParticipantType] = useState("unknown");
  const [noteContent, setNoteContent] = useState("");
  const [markerLabel, setMarkerLabel] = useState("");

  const addParticipantMutation = useMutation({
    mutationFn: () =>
      addParticipant(
        conversationId,
        { display_name: participantName, participant_type: participantType as never },
        csrfToken ?? ""
      ),
    onSuccess: () => {
      setParticipantName("");
      void queryClient.invalidateQueries({ queryKey: ["conversation-participants", conversationId] });
    },
  });

  const removeParticipantMutation = useMutation({
    mutationFn: (participantId: string) => deleteParticipant(conversationId, participantId, csrfToken ?? ""),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["conversation-participants", conversationId] }),
  });

  const addNoteMutation = useMutation({
    mutationFn: () => addNote(conversationId, { content: noteContent }, csrfToken ?? ""),
    onSuccess: () => {
      setNoteContent("");
      void queryClient.invalidateQueries({ queryKey: ["conversation-notes", conversationId] });
    },
  });

  const removeNoteMutation = useMutation({
    mutationFn: (noteId: string) => deleteNote(conversationId, noteId, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["conversation-notes", conversationId] }),
  });

  const addMarkerMutation = useMutation({
    mutationFn: () =>
      addMarker(conversationId, { timestamp_ms: 0, label: markerLabel || undefined }, csrfToken ?? ""),
    onSuccess: () => {
      setMarkerLabel("");
      void queryClient.invalidateQueries({ queryKey: ["conversation-markers", conversationId] });
    },
  });

  const removeMarkerMutation = useMutation({
    mutationFn: (markerId: string) => deleteMarker(conversationId, markerId, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["conversation-markers", conversationId] }),
  });

  const deleteConversationMutation = useMutation({
    mutationFn: () => deleteConversation(conversationId, csrfToken ?? ""),
    onSuccess: () => navigate("/app/conversations"),
  });

  if (conversationQuery.isLoading) return <p>Loading conversation…</p>;
  if (conversationQuery.isError || !conversationQuery.data) {
    return <p role="alert">Conversation not found, or you don&apos;t have access to it.</p>;
  }
  const conversation = conversationQuery.data;
  const sourceMedia = mediaQuery.data?.find((m) => m.kind === "source_audio");

  return (
    <div>
      <div className={styles.header}>
        <div>
          <h1 style={{ fontSize: "var(--font-h1-size)" }}>{conversation.title}</h1>
          <div className={styles.meta}>
            <Badge tone="info">{conversation.status}</Badge>
            <span>{conversation.conversation_type}</span>
            <span>{new Date(conversation.created_at).toLocaleString()}</span>
            {conversation.privacy_mode === "restricted" && <Badge tone="warning">Restricted</Badge>}
          </div>
        </div>
        {hasPermission("conversation:delete") && (
          <Button
            variant="destructive"
            type="button"
            onClick={() => {
              if (confirm("Delete this conversation and its media? This cannot be undone.")) {
                deleteConversationMutation.mutate();
              }
            }}
          >
            <Trash2 size={16} aria-hidden="true" /> Delete
          </Button>
        )}
      </div>

      <div className={styles.tabs} role="tablist">
        {(["overview", "audio", "transcript", "facts", "participants", "notes", "activity"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`${styles.tab} ${tab === t ? styles.tabActive : ""}`}
            onClick={() => setTab(t)}
            type="button"
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className={styles.layout}>
        <div>
          {tab === "overview" && (
            <div className={styles.sideCard}>
              <p>{conversation.description || "No description."}</p>
              <p style={{ marginTop: "var(--space-3)", color: "var(--text-muted)" }}>
                External reference: {conversation.external_reference || "—"}
              </p>
              <p style={{ color: "var(--text-muted)" }}>
                Duration: {conversation.duration_ms ? `${Math.round(conversation.duration_ms / 1000)}s` : "—"}
              </p>
            </div>
          )}

          {tab === "audio" && (
            <div>
              {sourceMedia ? (
                <AudioPlayer
                  ref={audioPlayerRef}
                  src={mediaContentUrl(conversationId, sourceMedia.id)}
                  sourceLabel={`${sourceMedia.source_type.replace("_", " ")} · ${sourceMedia.container ?? sourceMedia.content_type} · ${(sourceMedia.size_bytes / 1024 / 1024).toFixed(1)} MB`}
                  markers={markersQuery.data ?? []}
                  onTimeUpdateMs={setActiveMs}
                />
              ) : showRecorder ? (
                csrfToken && (
                  <RecordingWorkspace
                    conversationId={conversationId}
                    csrfToken={csrfToken}
                    onFinalized={() => {
                      setShowRecorder(false);
                      void queryClient.invalidateQueries({ queryKey: ["conversation-media", conversationId] });
                      void queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
                    }}
                  />
                )
              ) : (
                <div className={styles.emptyState}>
                  <p>No audio yet.</p>
                  <div style={{ display: "flex", gap: "var(--space-3)", justifyContent: "center" }}>
                    <Button variant="primary" type="button" onClick={() => setShowRecorder(true)}>
                      Start recording
                    </Button>
                    <Button
                      variant="secondary"
                      type="button"
                      onClick={() => document.getElementById("audio-upload-fallback-input")?.click()}
                    >
                      Upload audio file
                    </Button>
                    <input
                      id="audio-upload-fallback-input"
                      type="file"
                      accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,.webm,.wav,.mp3,.m4a"
                      style={{ display: "none" }}
                      onChange={(event) => {
                        const selected = event.target.files?.[0];
                        if (!selected || !csrfToken) return;
                        void uploadMedia(conversationId, selected, csrfToken).then(() => {
                          void queryClient.invalidateQueries({ queryKey: ["conversation-media", conversationId] });
                          void queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
                        });
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === "transcript" && (
            <div>
              {sourceMedia && (
                <div style={{ marginBottom: "var(--space-4)" }}>
                  <AudioPlayer
                    ref={audioPlayerRef}
                    src={mediaContentUrl(conversationId, sourceMedia.id)}
                    sourceLabel="Conversation audio"
                    onTimeUpdateMs={setActiveMs}
                  />
                </div>
              )}
              <TranscriptPanel
                conversationId={conversationId}
                audioPlayerRef={audioPlayerRef}
                activeMs={activeMs}
              />
            </div>
          )}

          {tab === "facts" && (
            <div>
              {sourceMedia && (
                <div style={{ marginBottom: "var(--space-4)" }}>
                  <AudioPlayer
                    ref={audioPlayerRef}
                    src={mediaContentUrl(conversationId, sourceMedia.id)}
                    sourceLabel="Conversation audio"
                    onTimeUpdateMs={setActiveMs}
                  />
                </div>
              )}
              <FactsPanel conversationId={conversationId} audioPlayerRef={audioPlayerRef} />
            </div>
          )}

          {tab === "participants" && (
            <div className={styles.sideCard}>
              {participantsQuery.data && participantsQuery.data.length === 0 && (
                <p>No participants yet.</p>
              )}
              <ul className={styles.list}>
                {participantsQuery.data?.map((participant) => (
                  <li key={participant.id} className={styles.listItem}>
                    <span>
                      {participant.display_name} ({participant.participant_type})
                    </span>
                    {hasPermission("conversation:manage-participants") && (
                      <button
                        type="button"
                        aria-label={`Remove ${participant.display_name}`}
                        onClick={() => removeParticipantMutation.mutate(participant.id)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {hasPermission("conversation:manage-participants") && (
                <div className={styles.addRow}>
                  <TextInput
                    placeholder="Person A"
                    aria-label="Participant name"
                    value={participantName}
                    onChange={(event) => setParticipantName(event.target.value)}
                  />
                  <Select
                    aria-label="Participant type"
                    value={participantType}
                    onChange={(event) => setParticipantType(event.target.value)}
                  >
                    <option value="unknown">Unknown</option>
                    <option value="staff">Staff</option>
                    <option value="patient">Patient</option>
                    <option value="client">Client</option>
                    <option value="guest">Guest</option>
                    <option value="other">Other</option>
                  </Select>
                  <Button
                    variant="secondary"
                    type="button"
                    disabled={!participantName.trim()}
                    onClick={() => addParticipantMutation.mutate()}
                  >
                    Add
                  </Button>
                </div>
              )}
            </div>
          )}

          {tab === "notes" && (
            <div className={styles.sideCard}>
              {notesQuery.data && notesQuery.data.length === 0 && <p>No notes yet.</p>}
              <ul className={styles.list} style={{ marginBottom: "var(--space-3)" }}>
                {notesQuery.data?.map((note) => (
                  <li key={note.id} className={styles.listItem}>
                    <span>{note.content}</span>
                    {hasPermission("conversation:manage-notes") && (
                      <button
                        type="button"
                        aria-label="Remove note"
                        onClick={() => removeNoteMutation.mutate(note.id)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {hasPermission("conversation:manage-notes") && (
                <div className={styles.addRow}>
                  <TextInput
                    placeholder="Add a note…"
                    aria-label="Note content"
                    value={noteContent}
                    onChange={(event) => setNoteContent(event.target.value)}
                  />
                  <Button
                    variant="secondary"
                    type="button"
                    disabled={!noteContent.trim()}
                    onClick={() => addNoteMutation.mutate()}
                  >
                    Add
                  </Button>
                </div>
              )}
            </div>
          )}

          {tab === "activity" && (
            <div className={styles.sideCard}>
              <ul className={styles.list}>
                <li className={styles.listItem}>
                  <span>Created</span>
                  <span>{new Date(conversation.created_at).toLocaleString()}</span>
                </li>
                {conversation.started_at && (
                  <li className={styles.listItem}>
                    <span>Recording started</span>
                    <span>{new Date(conversation.started_at).toLocaleString()}</span>
                  </li>
                )}
                {conversation.ended_at && (
                  <li className={styles.listItem}>
                    <span>Recording/upload ended</span>
                    <span>{new Date(conversation.ended_at).toLocaleString()}</span>
                  </li>
                )}
                <li className={styles.listItem}>
                  <span>Last updated</span>
                  <span>{new Date(conversation.updated_at).toLocaleString()}</span>
                </li>
              </ul>
              <p style={{ marginTop: "var(--space-3)", color: "var(--text-muted)" }}>
                Full event-level audit history is available to Auditor/System Admin roles via the
                admin area in a later phase.
              </p>
            </div>
          )}
        </div>

        <aside className={styles.sidebar}>
          <div className={styles.sideCard}>
            <h4>Markers</h4>
            {markersQuery.data && markersQuery.data.length === 0 && <p>No markers yet.</p>}
            <ul className={styles.list}>
              {markersQuery.data?.map((marker) => (
                <li key={marker.id} className={styles.listItem}>
                  <span>
                    {Math.round(marker.timestamp_ms / 1000)}s {marker.label ? `— ${marker.label}` : ""}
                  </span>
                  {hasPermission("conversation:manage-markers") && (
                    <button
                      type="button"
                      aria-label="Remove marker"
                      onClick={() => removeMarkerMutation.mutate(marker.id)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {hasPermission("conversation:manage-markers") && (
              <div className={styles.addRow}>
                <TextInput
                  placeholder="Marker label"
                  aria-label="Marker label"
                  value={markerLabel}
                  onChange={(event) => setMarkerLabel(event.target.value)}
                />
                <Button variant="secondary" type="button" onClick={() => addMarkerMutation.mutate()}>
                  Add
                </Button>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
