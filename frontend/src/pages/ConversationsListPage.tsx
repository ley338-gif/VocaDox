import { useQueries, useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Circle,
  Inbox,
  Mic,
  Plus,
  Upload,
} from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import type { Conversation, ConversationStatus } from "../api/conversations";
import { getConversation, getConversationStats, listConversations } from "../api/conversations";
import { search as searchContent, type SearchResult } from "../api/search";
import { OpenTasksCard } from "../components/OpenTasksCard";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { Select, TextInput } from "../design-system/FormControls";
import { IconAvatar } from "../design-system/IconAvatar";
import { PageHeader } from "../design-system/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";
import { Pagination } from "../design-system/Pagination";
import { Tabs, type TabItem } from "../design-system/Tabs";
import { CONVERSATION_TYPE_LABELS } from "../lib/conversationLabels";
import { formatDuration } from "../lib/formatDuration";
import { getRecentConversations } from "../lib/recentConversations";
import styles from "./ConversationsListPage.module.css";

// Same STATUS_MAP tones as StatusBadge (design-system/StatusBadge.tsx) —
// just paired with a glyph for the sidebar's round icon avatars instead
// of a text pill, so a given status still reads the same color everywhere.
const CONVERSATION_STATUS_ICON: Record<ConversationStatus, { icon: ReactNode; tone: "neutral" | "info" | "success" | "danger" }> = {
  created: { icon: <Circle size={16} aria-hidden="true" />, tone: "neutral" },
  recording: { icon: <Mic size={16} aria-hidden="true" />, tone: "info" },
  uploaded: { icon: <Upload size={16} aria-hidden="true" />, tone: "info" },
  normalizing: { icon: <Activity size={16} aria-hidden="true" />, tone: "info" },
  ready: { icon: <CheckCircle2 size={16} aria-hidden="true" />, tone: "success" },
  failed: { icon: <AlertCircle size={16} aria-hidden="true" />, tone: "danger" },
  deleted: { icon: <Circle size={16} aria-hidden="true" />, tone: "neutral" },
};

const SEARCH_SOURCE_LABELS: Record<SearchResult["source_type"], string> = {
  transcript_segment: "Transkript",
  extracted_fact: "Fakten",
  document: "Dokumentation",
};

function highlightedSnippet(snippet: string) {
  // ts_headline (see app.search.service, ADR-0030) wraps matches in ✦
  // pairs — the SQLite test/dev fallback never emits these, so plain
  // snippets render unchanged.
  const parts = snippet.split("✦");
  return parts.map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part));
}

function SearchResultsPanel({ query }: { query: string }) {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["content-search", query],
    queryFn: () => searchContent({ q: query }),
  });

  if (isLoading) return <Skeleton height="4rem" />;
  if (!data || data.items.length === 0) {
    return <EmptyState title="Keine Treffer" description="Keine Inhalte gefunden." />;
  }

  return (
    <div className={styles.searchResults}>
      {data.items.map((item) => (
        <a
          key={`${item.source_type}-${item.source_id}`}
          className={styles.searchResult}
          href={`/app/conversations/${item.conversation_id}`}
          onClick={(event) => {
            event.preventDefault();
            const tab =
              item.source_type === "transcript_segment"
                ? "transcript"
                : item.source_type === "extracted_fact"
                  ? "facts"
                  : "document";
            navigate(`/app/conversations/${item.conversation_id}`, {
              state: {
                tab,
                focusSegmentId: item.source_type === "transcript_segment" ? item.source_id : undefined,
              },
            });
          }}
        >
          <div className={styles.searchResultHeader}>
            <span className={styles.searchResultTitle}>{item.conversation_title}</span>
            <StatusBadge status={item.source_type} label={SEARCH_SOURCE_LABELS[item.source_type]} />
          </div>
          <p className={styles.searchResultSnippet}>{highlightedSnippet(item.snippet)}</p>
        </a>
      ))}
    </div>
  );
}

const PAGE_SIZE = 20;

// The "in progress" bucket used for both the KPI-style status tabs below
// and the app dashboard (AppHomePage) — kept identical so the two pages
// never disagree about what counts as "in Bearbeitung".
const IN_PROGRESS_STATUSES = ["recording", "uploaded", "normalizing"];

type StatusTab = "all" | "active" | "ready" | "failed";

// One real backend status value per tab, comma-joined for "active" (see
// app.conversations.service.list_conversations's multi-value support) —
// never a fabricated aggregate status.
const STATUS_TAB_FILTER: Record<StatusTab, string> = {
  all: "",
  active: IN_PROGRESS_STATUSES.join(","),
  ready: "ready",
  failed: "failed",
};

function formatRelativeDateTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const time = date.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  if (date.toDateString() === now.toDateString()) return `heute, ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return `gestern, ${time}`;
  return `${date.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}, ${time}`;
}

const COLUMNS: DataTableColumn<Conversation>[] = [
  {
    key: "title",
    header: "Gespräch",
    render: (row) => (
      <div>
        <div className={styles.rowTitle}>{row.title}</div>
        <div className={styles.rowSubtitle}>
          {row.description || CONVERSATION_TYPE_LABELS[row.conversation_type]}
        </div>
      </div>
    ),
    sortable: true,
    sortValue: (row) => row.title,
  },
  {
    key: "context",
    header: "Kontext",
    render: (row) => row.external_reference || "—",
  },
  {
    key: "created",
    header: "Datum",
    render: (row) =>
      new Date(row.created_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }),
    sortable: true,
    sortValue: (row) => row.created_at,
  },
  {
    key: "duration",
    header: "Dauer",
    render: (row) => (row.duration_ms ? formatDuration(row.duration_ms) : "—"),
  },
  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
];

export function ConversationsListPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get("q") ?? "");
  const [statusTab, setStatusTab] = useState<StatusTab>("all");
  const [typeFilter, setTypeFilter] = useState("");
  const [offset, setOffset] = useState(0);
  // Full-text/cross-conversation content search (post-GA P0-1) — distinct
  // from `search` above, which only ever filters the title column.
  const [contentQuery, setContentQuery] = useState("");

  const statusFilter = STATUS_TAB_FILTER[statusTab];

  const { data, isLoading, isError } = useQuery({
    queryKey: ["conversations", { search, statusFilter, typeFilter, offset }],
    queryFn: () =>
      listConversations({
        search: search || undefined,
        status: statusFilter || undefined,
        type: typeFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
  });

  const statsQuery = useQuery({ queryKey: ["conversation-stats"], queryFn: getConversationStats });
  const counts = statsQuery.data?.counts ?? {};
  const allCount = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const activeCount = IN_PROGRESS_STATUSES.reduce((sum, key) => sum + (counts[key] ?? 0), 0);
  const readyCount = counts.ready ?? 0;
  const failedCount = counts.failed ?? 0;

  const tabItems: TabItem[] = [
    { id: "all", label: `Alle (${allCount})` },
    { id: "active", label: `In Bearbeitung (${activeCount})` },
    { id: "ready", label: `Bereit (${readyCount})` },
    { id: "failed", label: `Fehler (${failedCount})` },
  ];

  const recentEntries = getRecentConversations().slice(0, 4);
  const recentQueries = useQueries({
    queries: recentEntries.map((entry) => ({
      queryKey: ["conversation", entry.id],
      queryFn: () => getConversation(entry.id),
      staleTime: 30_000,
      retry: false,
    })),
  });
  const recentConversations = recentQueries
    .map((q, index) => (q.data ? { conversation: q.data, openedAt: recentEntries[index].openedAt } : null))
    .filter((entry): entry is { conversation: Conversation; openedAt: string } => entry !== null);

  return (
    <div>
      <PageHeader
        title="Gespräche"
        meta="Alle aufgenommenen und transkribierten Gespräche im Überblick."
        actions={
          <Button variant="primary" type="button" onClick={() => navigate("/app/conversations/new")}>
            <Plus size={16} aria-hidden="true" /> Neues Gespräch
          </Button>
        }
      />

      <div className={styles.searchSection}>
        <TextInput
          placeholder="Inhalte durchsuchen (Transkript, Fakten, Dokumentation)…"
          aria-label="Inhalte durchsuchen"
          value={contentQuery}
          onChange={(event) => setContentQuery(event.target.value)}
        />
        {contentQuery.trim() && <SearchResultsPanel query={contentQuery.trim()} />}
      </div>

      <div className={styles.columns}>
        <div>
          <Tabs
            items={tabItems}
            activeId={statusTab}
            onChange={(id) => {
              setOffset(0);
              setStatusTab(id as StatusTab);
            }}
            idPrefix="conversations-status"
          />

          <div className={styles.filters}>
            <TextInput
              placeholder="Nach Titel suchen…"
              aria-label="Gespräche durchsuchen"
              value={search}
              onChange={(event) => {
                setOffset(0);
                setSearch(event.target.value);
              }}
            />
            <Select
              aria-label="Nach Typ filtern"
              value={typeFilter}
              onChange={(event) => {
                setOffset(0);
                setTypeFilter(event.target.value);
              }}
            >
              <option value="">Alle Typen</option>
              <option value="general">Allgemein</option>
              <option value="medical">Medizinisch</option>
              <option value="therapy">Therapie</option>
              <option value="meeting">Meeting</option>
              <option value="interview">Interview</option>
              <option value="other">Sonstiges</option>
            </Select>
          </div>

          <DataTable
            columns={COLUMNS}
            rows={data?.items ?? []}
            keyExtractor={(row) => row.id}
            loading={isLoading}
            error={isError ? <ErrorState message="Gespräche konnten nicht geladen werden." /> : undefined}
            onRowClick={(row) => navigate(`/app/conversations/${row.id}`)}
            empty={
              <EmptyState
                icon={<Inbox size={20} aria-hidden="true" />}
                title="Noch keine Gespräche"
                description="Starten Sie ein neues Gespräch, um loszulegen."
                action={
                  <Button variant="primary" type="button" onClick={() => navigate("/app/conversations/new")}>
                    Gespräch starten
                  </Button>
                }
              />
            }
          />

          {data && data.total > 0 && (
            <Pagination offset={offset} limit={PAGE_SIZE} total={data.total} onOffsetChange={setOffset} />
          )}
        </div>

        <aside className={styles.sidebar}>
          <Card title="Schnellaktionen">
            <div className={styles.quickActions}>
              <button
                type="button"
                className={styles.quickAction}
                onClick={() => navigate("/app/conversations/new?mode=record")}
              >
                <Mic size={16} aria-hidden="true" /> Audio aufnehmen
              </button>
              <button
                type="button"
                className={styles.quickAction}
                onClick={() => navigate("/app/conversations/new?mode=upload")}
              >
                <Upload size={16} aria-hidden="true" /> Datei hochladen
              </button>
            </div>
          </Card>

          <Card title="Zuletzt geöffnet">
            {recentConversations.length === 0 ? (
              <EmptyState title="Noch nichts geöffnet" description="Geöffnete Gespräche erscheinen hier." />
            ) : (
              <ul className={styles.recentList}>
                {recentConversations.map(({ conversation, openedAt }) => (
                  <li key={conversation.id}>
                    <button
                      type="button"
                      className={styles.recentItem}
                      onClick={() => navigate(`/app/conversations/${conversation.id}`)}
                    >
                      <IconAvatar {...CONVERSATION_STATUS_ICON[conversation.status]} />
                      <span className={styles.recentBody}>
                        <span className={styles.recentTitle}>{conversation.title}</span>
                        <span className={styles.recentMeta}>
                          {conversation.description || CONVERSATION_TYPE_LABELS[conversation.conversation_type]}
                          {" · "}
                          {formatRelativeDateTime(openedAt)}
                        </span>
                      </span>
                      <ChevronRight size={16} aria-hidden="true" className={styles.recentChevron} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <OpenTasksCard limit={4} />
        </aside>
      </div>
    </div>
  );
}
