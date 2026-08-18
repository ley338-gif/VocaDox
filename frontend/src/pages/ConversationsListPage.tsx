import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import type { ConversationStatus } from "../api/conversations";
import { listConversations } from "../api/conversations";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Select, TextInput } from "../design-system/FormControls";
import styles from "./ConversationsListPage.module.css";

const STATUS_TONE: Record<ConversationStatus, "neutral" | "success" | "warning" | "danger" | "info"> = {
  created: "neutral",
  recording: "warning",
  uploaded: "info",
  normalizing: "info",
  ready: "success",
  failed: "danger",
  deleted: "neutral",
};

const PAGE_SIZE = 20;

export function ConversationsListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [offset, setOffset] = useState(0);

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

  return (
    <div>
      <div className={styles.header}>
        <h1 style={{ fontSize: "var(--font-h1-size)" }}>Conversations</h1>
        <Button variant="primary" type="button" onClick={() => navigate("/app/conversations/new")}>
          <Plus size={16} aria-hidden="true" /> New conversation
        </Button>
      </div>

      <div className={styles.filters}>
        <TextInput
          placeholder="Search by title…"
          aria-label="Search conversations"
          value={search}
          onChange={(event) => {
            setOffset(0);
            setSearch(event.target.value);
          }}
        />
        <Select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(event) => {
            setOffset(0);
            setStatusFilter(event.target.value);
          }}
        >
          <option value="">All statuses</option>
          <option value="created">Created</option>
          <option value="recording">Recording</option>
          <option value="uploaded">Uploaded</option>
          <option value="normalizing">Normalizing</option>
          <option value="ready">Ready</option>
          <option value="failed">Failed</option>
        </Select>
        <Select
          aria-label="Filter by type"
          value={typeFilter}
          onChange={(event) => {
            setOffset(0);
            setTypeFilter(event.target.value);
          }}
        >
          <option value="">All types</option>
          <option value="general">General</option>
          <option value="medical">Medical</option>
          <option value="therapy">Therapy</option>
          <option value="meeting">Meeting</option>
          <option value="interview">Interview</option>
          <option value="other">Other</option>
        </Select>
      </div>

      {isLoading && <p style={{ color: "var(--text-muted)" }}>Loading conversations…</p>}
      {isError && <p role="alert">Couldn&apos;t load conversations. Try reloading the page.</p>}

      {!isLoading && !isError && data && data.items.length === 0 && (
        <div className={styles.emptyState}>
          <p>No conversations yet.</p>
          <Button variant="primary" type="button" onClick={() => navigate("/app/conversations/new")}>
            Start your first conversation
          </Button>
        </div>
      )}

      {!isLoading && !isError && data && data.items.length > 0 && (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Status</th>
                <th>Privacy</th>
                <th>Duration</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((conversation) => (
                <tr
                  key={conversation.id}
                  className={styles.row}
                  tabIndex={0}
                  onClick={() => navigate(`/app/conversations/${conversation.id}`)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") navigate(`/app/conversations/${conversation.id}`);
                  }}
                >
                  <td>{conversation.title}</td>
                  <td>{conversation.conversation_type}</td>
                  <td>
                    <Badge tone={STATUS_TONE[conversation.status]}>{conversation.status}</Badge>
                  </td>
                  <td>{conversation.privacy_mode === "restricted" ? "Restricted" : "Standard"}</td>
                  <td>{conversation.duration_ms ? `${Math.round(conversation.duration_ms / 1000)}s` : "—"}</td>
                  <td>{new Date(conversation.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className={styles.pagination}>
            <Button
              variant="secondary"
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              type="button"
              disabled={offset + PAGE_SIZE >= data.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

