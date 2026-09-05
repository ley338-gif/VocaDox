/**
 * Phase 9 "Tasks" tab: Follow-ups/Tasks for this conversation. Two
 * sources — AI_EXTRACTED (derived from Phase 4's existing "task" fact
 * category, always shown with a link back to its evidence) and
 * USER_CREATED (added directly here). No notifications/reminders exist —
 * this is a real, listable/actionable list only.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createConversationTask,
  listConversationTasks,
  updateTaskStatus,
  type FollowUpStatus,
  type FollowUpTask,
} from "../api/longitudinal";
import { useAuth } from "../auth/useAuth";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { TextInput } from "../design-system/FormControls";
import { EmptyState, Skeleton } from "../design-system/States";
import { StatusBadge } from "../design-system/StatusBadge";
import styles from "./FactsPanel.module.css";

function TaskRow({
  task,
  onUpdateStatus,
  canUpdate,
}: {
  task: FollowUpTask;
  onUpdateStatus: (status: FollowUpStatus) => void;
  canUpdate: boolean;
}) {
  return (
    <li className={styles.item}>
      <div className={styles.header}>
        <Badge tone={task.source === "ai_extracted" ? "info" : "neutral"}>
          {task.source === "ai_extracted" ? "Automatisch erstellt" : "Manuell erstellt"}
        </Badge>
        <StatusBadge status={task.status} />
        <span>{task.description}</span>
      </div>
      <div style={{ color: "var(--text-muted)", marginTop: "var(--space-1)" }}>
        {task.assignee && <span>Verantwortlich: {task.assignee} · </span>}
        {task.due_date && <span>Fällig: {task.due_date}</span>}
      </div>
      {canUpdate && task.status === "open" && (
        <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
          <Button variant="secondary" type="button" onClick={() => onUpdateStatus("done")}>
            Erledigt
          </Button>
          <Button variant="tertiary" type="button" onClick={() => onUpdateStatus("dismissed")}>
            Verwerfen
          </Button>
        </div>
      )}
    </li>
  );
}

export function TasksPanel({ conversationId }: { conversationId: string }) {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");

  const tasksQuery = useQuery({
    queryKey: ["conversation-tasks", conversationId],
    queryFn: () => listConversationTasks(conversationId),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createConversationTask(
        conversationId,
        { description, assignee: assignee || undefined, due_date: dueDate || undefined },
        csrfToken ?? ""
      ),
    onSuccess: () => {
      setDescription("");
      setAssignee("");
      setDueDate("");
      void queryClient.invalidateQueries({ queryKey: ["conversation-tasks", conversationId] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: FollowUpStatus }) =>
      updateTaskStatus(taskId, status, csrfToken ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["conversation-tasks", conversationId] }),
  });

  const canCreate = hasPermission("task:create");
  const canUpdate = hasPermission("task:update");

  return (
    <div>
      {tasksQuery.isLoading && <Skeleton height="4rem" />}
      {tasksQuery.data && tasksQuery.data.length === 0 && <EmptyState title="Noch keine Aufgaben" />}
      <ul className={styles.list}>
        {tasksQuery.data?.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            canUpdate={canUpdate}
            onUpdateStatus={(status) => updateMutation.mutate({ taskId: task.id, status })}
          />
        ))}
      </ul>
      {canCreate && (
        <div style={{ marginTop: "var(--space-4)", display: "grid", gap: "var(--space-2)" }}>
          <TextInput
            placeholder="Beschreibung der Aufgabe"
            aria-label="Aufgabenbeschreibung"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <TextInput
              placeholder="Verantwortlich (optional)"
              aria-label="Verantwortliche Person"
              value={assignee}
              onChange={(event) => setAssignee(event.target.value)}
            />
            <TextInput
              placeholder="Fällig am (optional)"
              aria-label="Fälligkeitsdatum"
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
            />
            <Button
              variant="secondary"
              type="button"
              disabled={!description.trim()}
              onClick={() => createMutation.mutate()}
            >
              Hinzufügen
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
