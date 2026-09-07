/**
 * Shared "open tasks" preview widget, used by both the Dashboard
 * (AppHomePage) and the Gespräche list sidebar — previously two
 * independently hand-rolled implementations of the exact same
 * `listTasks("open")` query with different markup/styling. One real
 * source of truth now: same query, same icon/tone vocabulary as
 * StatusBadge, same "Alle anzeigen" link to the org-wide /app/tasks
 * table (the real place to filter/act beyond this short preview).
 */
import { useQuery } from "@tanstack/react-query";
import { Circle, Clock, ListChecks } from "lucide-react";
import { useNavigate } from "react-router";

import { listTasks, type FollowUpTask } from "../api/longitudinal";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { IconAvatar } from "../design-system/IconAvatar";
import { EmptyState, ErrorState, Skeleton } from "../design-system/States";
import styles from "./OpenTasksCard.module.css";

// Same tone StatusBadge would show for this task's real `status` (open =
// warning, matching STATUS_MAP) -- only the glyph varies by due_date, so
// this never disagrees in color with the task's own StatusBadge shown
// elsewhere (e.g. the conversation's Aufgaben tab).
const TASK_STATUS_TONE: Record<FollowUpTask["status"], "warning" | "success" | "neutral"> = {
  open: "warning",
  done: "success",
  dismissed: "neutral",
};

function taskIcon(task: FollowUpTask) {
  return {
    icon: task.due_date ? <Clock size={16} aria-hidden="true" /> : <Circle size={16} aria-hidden="true" />,
    tone: TASK_STATUS_TONE[task.status],
  };
}

export function OpenTasksCard({ limit = 5 }: { limit?: number }) {
  const navigate = useNavigate();
  const { hasPermission } = useAuth();

  const tasksQuery = useQuery({
    queryKey: ["tasks", { status: "open" }],
    queryFn: () => listTasks("open"),
    enabled: hasPermission("task:read"),
  });

  if (!hasPermission("task:read")) return null;

  return (
    <Card
      title="Offene Aufgaben"
      actions={
        <Button variant="tertiary" type="button" onClick={() => navigate("/app/tasks")}>
          Alle anzeigen
        </Button>
      }
    >
      {tasksQuery.isLoading ? (
        <Skeleton height="1rem" />
      ) : tasksQuery.isError ? (
        <ErrorState message="Aufgaben konnten nicht geladen werden." />
      ) : (tasksQuery.data ?? []).length === 0 ? (
        <EmptyState icon={<ListChecks size={20} aria-hidden="true" />} title="Keine offenen Aufgaben" />
      ) : (
        <ul className={styles.list}>
          {(tasksQuery.data ?? []).slice(0, limit).map((task) => (
            <li key={task.id} className={styles.item}>
              <button
                type="button"
                className={styles.link}
                onClick={() =>
                  navigate(`/app/conversations/${task.conversation_id}`, { state: { tab: "tasks" } })
                }
              >
                <IconAvatar {...taskIcon(task)} />
                <span className={styles.body}>
                  <span className={styles.description}>{task.description}</span>
                  <span className={styles.meta}>
                    {task.source === "ai_extracted" ? "Automatisch erstellt" : "Manuell erstellt"}
                    {task.due_date ? ` · Fällig: ${task.due_date}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
