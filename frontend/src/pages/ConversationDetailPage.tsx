import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CheckSquare,
  Clock,
  FileText,
  History,
  Info,
  Link2,
  Sparkles,
  StickyNote,
  Trash2,
  Users,
} from "lucide-react";
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
import { getDocument } from "../api/documents";
import { getExternalReferenceTimeline, listConversationTasks } from "../api/longitudinal";
import { listFacts } from "../api/intelligence";
import { getProcessingStatus, listSpeakers } from "../api/transcription";
import { useAuth } from "../auth/useAuth";
import { AudioPlayer, type AudioPlayerHandle } from "../components/AudioPlayer";
import { DocumentPanel } from "../components/DocumentPanel";
import { FactsPanel } from "../components/FactsPanel";
import { LongitudinalPanel } from "../components/LongitudinalPanel";
import { RecordingWorkspace } from "../components/RecordingWorkspace";
import { ReviewWizard } from "../components/ReviewWizard";
import { SpeakerBadge } from "../components/SpeakerBadge";
import { TasksPanel } from "../components/TasksPanel";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { Select, TextInput } from "../design-system/FormControls";
import { NavCard } from "../design-system/NavCard";
import { PageHeader } from "../design-system/PageHeader";
import { SidePanelCard } from "../design-system/SidePanelCard";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { Tabs, type TabItem } from "../design-system/Tabs";
import { CONVERSATION_TYPE_LABELS } from "../lib/conversationLabels";
import styles from "./ConversationDetailPage.module.css";

const TAB_LABELS: Record<Tab, string> = {
  overview: "Übersicht",
  document: "Dokumentation",
  review: "Review",
  audio: "Audio",
  transcript: "Transkript",
  facts: "Fakten",
  timeline: "Verlauf",
  related: "Verwandt",
  tasks: "Aufgaben",
  details: "Details",
  notes: "Notizen",
  activity: "Aktivität",
};

const PRIMARY_TAB_IDS: Tab[] = ["overview", "transcript", "document", "review", "audio"];

type Tab =
  | "overview"
  | "document"
  | "review"
  | "audio"
  | "transcript"
  | "facts"
  | "timeline"
  | "related"
  | "tasks"
  | "details"
  | "notes"
  | "activity";

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
  const processingQuery = useQuery({
    queryKey: ["conversation-processing", conversationId],
    queryFn: () => getProcessingStatus(conversationId),
    enabled: Boolean(conversationId),
  });

  // Sidebar summaries — deliberately read the SAME query keys the owning
  // tabs/panels already use (document/speakers/tasks), so React Query
  // dedupes the request instead of firing a second network call, and the
  // sidebar and its tab always agree with each other.
  const documentQuery = useQuery({
    queryKey: ["document", conversationId],
    queryFn: () => getDocument(conversationId),
    retry: false,
    enabled: Boolean(conversationId),
  });
  const speakersQuery = useQuery({
    queryKey: ["speakers", conversationId],
    queryFn: () => listSpeakers(conversationId),
    enabled: Boolean(conversationId),
  });
  const tasksQuery = useQuery({
    queryKey: ["conversation-tasks", conversationId],
    queryFn: () => listConversationTasks(conversationId),
    enabled: Boolean(conversationId) && hasPermission("task:read"),
  });
  const factsQuery = useQuery({
    queryKey: ["facts", conversationId],
    queryFn: () => listFacts(conversationId),
    enabled: Boolean(conversationId),
  });
  const externalReference = conversationQuery.data?.external_reference;
  const organizationId = conversationQuery.data?.organization_id;
  const timelineQuery = useQuery({
    queryKey: ["longitudinal-timeline", organizationId, externalReference],
    queryFn: () => getExternalReferenceTimeline(externalReference ?? "", organizationId ?? ""),
    enabled: Boolean(externalReference && organizationId),
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

  if (conversationQuery.isLoading) {
    return <Skeleton height="8rem" />;
  }
  if (conversationQuery.isError || !conversationQuery.data) {
    return <ErrorState title="Gespräch nicht gefunden" message="Kein Zugriff oder das Gespräch existiert nicht." />;
  }
  const conversation = conversationQuery.data;
  const sourceMedia = mediaQuery.data?.find((m) => m.kind === "source_audio");

  const tabItems: TabItem[] = PRIMARY_TAB_IDS.map((t) => ({ id: t, label: TAB_LABELS[t] }));

  const openTasks = (tasksQuery.data ?? []).filter((t) => t.status === "open");
  const documentPreview = documentQuery.data?.current_revision?.rendered_text ?? null;

  return (
    <div>
      <PageHeader
        breadcrumb={[{ label: "Gespräche", to: "/app/conversations" }, { label: conversation.title }]}
        title={conversation.title}
        meta={
          <>
            <StatusBadge status={conversation.status} />
            <span className={styles.metaItem}>{CONVERSATION_TYPE_LABELS[conversation.conversation_type]}</span>
            <span className={styles.metaItem}>
              <Clock size={13} aria-hidden="true" /> {new Date(conversation.created_at).toLocaleString()}
            </span>
            {conversation.duration_ms !== null && (
              <span className={styles.metaItem}>{Math.round(conversation.duration_ms / 1000)}s</span>
            )}
            {participantsQuery.data && (
              <span className={styles.metaItem}>
                <Users size={13} aria-hidden="true" /> {participantsQuery.data.length} Teilnehmer
              </span>
            )}
            {conversation.privacy_mode === "restricted" && <Badge tone="warning">Eingeschränkt</Badge>}
          </>
        }
        actions={
          hasPermission("document:approve") && (
            <Button variant="primary" type="button" onClick={() => setTab("document")}>
              Freigeben
            </Button>
          )
        }
        overflowActions={
          hasPermission("conversation:delete")
            ? [
                {
                  label: "Gespräch löschen",
                  danger: true,
                  icon: <Trash2 size={14} aria-hidden="true" />,
                  onClick: () => {
                    if (
                      confirm("Dieses Gespräch inkl. Medien löschen? Dies kann nicht rückgängig gemacht werden.")
                    ) {
                      deleteConversationMutation.mutate();
                    }
                  },
                },
              ]
            : undefined
        }
      />

      <Tabs idPrefix="conv" items={tabItems} activeId={tab} onChange={(id) => setTab(id as Tab)} />

      <div className={styles.layout}>
        <div>
          {tab === "overview" && (
            <div>
              {conversation.description && (
                <p style={{ marginBottom: "var(--space-4)", color: "var(--text-secondary)" }}>
                  {conversation.description}
                </p>
              )}
              <div className={styles.dashboardGrid}>
                <NavCard
                  icon={<Sparkles size={18} aria-hidden="true" />}
                  title="Fakten"
                  description={`${factsQuery.data?.length ?? 0} extrahierte Fakten`}
                  onClick={() => setTab("facts")}
                />
                <NavCard
                  icon={<History size={18} aria-hidden="true" />}
                  title="Verlauf"
                  description={`${processingQuery.data?.jobs.length ?? 0} Verarbeitungsschritte`}
                  onClick={() => setTab("timeline")}
                />
                {conversation.external_reference && (
                  <NavCard
                    icon={<Link2 size={18} aria-hidden="true" />}
                    title="Verwandt"
                    description={`${timelineQuery.data?.conversations.length ?? 0} verknüpfte Gespräche`}
                    onClick={() => setTab("related")}
                  />
                )}
                <NavCard
                  icon={<Info size={18} aria-hidden="true" />}
                  title="Details"
                  description="Verarbeitungs-Provenienz"
                  onClick={() => setTab("details")}
                />
                <NavCard
                  icon={<StickyNote size={18} aria-hidden="true" />}
                  title="Notizen"
                  description={`${notesQuery.data?.length ?? 0} Notizen`}
                  onClick={() => setTab("notes")}
                />
                <NavCard
                  icon={<Activity size={18} aria-hidden="true" />}
                  title="Aktivität"
                  description="Zeitpunkte & Status"
                  onClick={() => setTab("activity")}
                />
              </div>
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

          {tab === "document" && (
            <div>
              <DocumentPanel conversationId={conversationId} />
            </div>
          )}

          {tab === "review" && (
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
              <ReviewWizard conversationId={conversationId} audioPlayerRef={audioPlayerRef} />
            </div>
          )}

          {tab === "timeline" && (
            <div className={styles.sideCard}>
              <p style={{ color: "var(--text-muted)" }}>
                Chronological processing/event timeline for this conversation only — cross-
                conversation longitudinal comparison is a later phase.
              </p>
              <ul className={styles.list}>
                {[
                  { at: conversation.created_at, label: "Conversation created" },
                  ...(markersQuery.data ?? []).map((m) => ({
                    at: m.created_at,
                    label: `Marker at ${Math.round(m.timestamp_ms / 1000)}s${m.label ? ` — ${m.label}` : ""}`,
                  })),
                  ...(notesQuery.data ?? []).map((n) => ({ at: n.created_at, label: `Note: ${n.content}` })),
                  ...(processingQuery.data?.jobs ?? []).map((j) => ({
                    at: j.completed_at ?? j.started_at ?? j.queued_at,
                    label: `${j.job_type} — ${j.status}${j.failure_class ? ` (${j.failure_class})` : ""}`,
                  })),
                ]
                  .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime())
                  .map((event, idx) => (
                    <li key={idx} className={styles.listItem}>
                      <span>{event.label}</span>
                      <span style={{ color: "var(--text-muted)" }}>
                        {new Date(event.at).toLocaleString()}
                      </span>
                    </li>
                  ))}
              </ul>
            </div>
          )}

          {tab === "related" && (
            <div className={styles.sideCard}>
              <LongitudinalPanel
                conversationId={conversationId}
                organizationId={conversation.organization_id}
                externalReference={conversation.external_reference}
              />
            </div>
          )}

          {tab === "tasks" && (
            <div className={styles.sideCard}>
              <TasksPanel conversationId={conversationId} />
            </div>
          )}

          {tab === "details" && (
            <div className={styles.sideCard}>
              <p style={{ color: "var(--text-muted)" }}>
                Processing provenance for this conversation — see the Facts/Document tabs for what
                each processing run actually produced.
              </p>
              {processingQuery.isLoading && <p>Loading processing history…</p>}
              <ul className={styles.list}>
                {processingQuery.data?.jobs.map((job) => (
                  <li key={job.id} className={styles.listItem}>
                    <span>
                      {job.job_type} — {job.status} (attempt {job.attempt}/{job.max_attempts})
                    </span>
                    <span style={{ color: "var(--text-muted)" }}>
                      {job.completed_at
                        ? new Date(job.completed_at).toLocaleString()
                        : job.started_at
                          ? `started ${new Date(job.started_at).toLocaleString()}`
                          : `queued ${new Date(job.queued_at).toLocaleString()}`}
                    </span>
                  </li>
                ))}
              </ul>
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
          <SidePanelCard
            icon={<Sparkles size={14} aria-hidden="true" />}
            title="Kurzfassung"
            action={
              documentPreview && (
                <Button variant="tertiary" type="button" onClick={() => setTab("document")}>
                  Vollständig
                </Button>
              )
            }
          >
            {documentQuery.isLoading && <Skeleton height="3rem" />}
            {!documentQuery.isLoading && !documentPreview && (
              <EmptyState
                icon={<FileText size={18} aria-hidden="true" />}
                title="Noch keine Dokumentation"
                description="Automatisch erstellt, sobald ein Dokument zusammengestellt wurde."
              />
            )}
            {documentPreview && (
              <p className={styles.summaryPreview}>
                {documentPreview.length > 320 ? `${documentPreview.slice(0, 320)}…` : documentPreview}
              </p>
            )}
          </SidePanelCard>

          <Card title="Marker">
            {markersQuery.data && markersQuery.data.length === 0 && (
              <EmptyState title="Noch keine Marker" />
            )}
            <ul className={styles.list}>
              {markersQuery.data?.map((marker) => (
                <li key={marker.id} className={styles.listItem}>
                  <span>
                    {Math.round(marker.timestamp_ms / 1000)}s {marker.label ? `— ${marker.label}` : ""}
                  </span>
                  {hasPermission("conversation:manage-markers") && (
                    <button
                      type="button"
                      aria-label="Marker entfernen"
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
                  placeholder="Marker-Beschriftung"
                  aria-label="Marker-Beschriftung"
                  value={markerLabel}
                  onChange={(event) => setMarkerLabel(event.target.value)}
                />
                <Button variant="secondary" type="button" onClick={() => addMarkerMutation.mutate()}>
                  Hinzufügen
                </Button>
              </div>
            )}
          </Card>

          <SidePanelCard icon={<Users size={14} aria-hidden="true" />} title="Teilnehmer">
            {participantsQuery.data && participantsQuery.data.length === 0 && (
              <EmptyState title="Noch keine Teilnehmer" />
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
                      aria-label={`${participant.display_name} entfernen`}
                      onClick={() => removeParticipantMutation.mutate(participant.id)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {hasPermission("conversation:manage-participants") && (
              <div className={styles.addRowStacked}>
                <TextInput
                  placeholder="Person A"
                  aria-label="Teilnehmername"
                  value={participantName}
                  onChange={(event) => setParticipantName(event.target.value)}
                />
                <div className={styles.addRow}>
                  <Select
                    aria-label="Teilnehmertyp"
                    value={participantType}
                    onChange={(event) => setParticipantType(event.target.value)}
                  >
                    <option value="unknown">Unbekannt</option>
                    <option value="staff">Mitarbeiter</option>
                    <option value="patient">Patient</option>
                    <option value="client">Klient</option>
                    <option value="guest">Gast</option>
                    <option value="other">Sonstiges</option>
                  </Select>
                  <Button
                    variant="secondary"
                    type="button"
                    disabled={!participantName.trim()}
                    onClick={() => addParticipantMutation.mutate()}
                  >
                    Hinzufügen
                  </Button>
                </div>
              </div>
            )}
            {(speakersQuery.data ?? []).length > 0 && (
              <>
                <p className={styles.sidebarSubheading}>Sprecherzuordnung</p>
                <div className={styles.speakerBadgeRow}>
                  {speakersQuery.data?.map((speaker) => (
                    <SpeakerBadge
                      key={speaker.id}
                      colorKey={speaker.internal_label}
                      label={speaker.display_label ?? speaker.internal_label}
                    />
                  ))}
                </div>
                {hasPermission("speaker:assign") && (
                  <Button variant="tertiary" type="button" onClick={() => setTab("transcript")}>
                    Sprecherzuordnung bearbeiten
                  </Button>
                )}
              </>
            )}
          </SidePanelCard>

          {hasPermission("task:read") && (
            <SidePanelCard
              icon={<CheckSquare size={14} aria-hidden="true" />}
              title="Nächste Schritte"
              action={
                <Button variant="tertiary" type="button" onClick={() => setTab("tasks")}>
                  Alle
                </Button>
              }
            >
              {tasksQuery.isLoading && <Skeleton height="2rem" />}
              {!tasksQuery.isLoading && openTasks.length === 0 && (
                <EmptyState title="Keine offenen Aufgaben" />
              )}
              <ul className={styles.taskPreviewList}>
                {openTasks.slice(0, 5).map((task) => (
                  <li key={task.id} className={styles.taskPreviewItem}>
                    <input type="checkbox" disabled aria-hidden="true" tabIndex={-1} />
                    <span>{task.description}</span>
                  </li>
                ))}
              </ul>
            </SidePanelCard>
          )}
        </aside>
      </div>
    </div>
  );
}
