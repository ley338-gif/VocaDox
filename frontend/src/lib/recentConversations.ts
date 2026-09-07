/**
 * Client-side "recently opened" MRU list for the Gespräche list page's
 * sidebar. Deliberately just {id, openedAt} pairs in localStorage (per
 * browser, never synced) -- the list page re-fetches each id via the
 * real API to render fresh title/status, so this never risks showing a
 * stale/fabricated snapshot, only a stale *order*. `openedAt` is the
 * real client-side moment the conversation was opened (not the
 * conversation's own created/updated_at), so "Zuletzt geöffnet" shows
 * genuinely when *this browser* last visited it.
 */
const STORAGE_KEY = "vocadox.recentConversations";
const MAX_ENTRIES = 6;

interface RecentEntry {
  id: string;
  openedAt: string;
}

export function recordRecentConversation(id: string): void {
  try {
    const next = [
      { id, openedAt: new Date().toISOString() },
      ...getRecentConversations().filter((entry) => entry.id !== id),
    ].slice(0, MAX_ENTRIES);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // localStorage unavailable (private browsing, storage disabled) — skip silently.
  }
}

export function getRecentConversations(): RecentEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is RecentEntry =>
        typeof entry === "object" &&
        entry !== null &&
        typeof (entry as RecentEntry).id === "string" &&
        typeof (entry as RecentEntry).openedAt === "string"
    );
  } catch {
    return [];
  }
}

export function getRecentConversationIds(): string[] {
  return getRecentConversations().map((entry) => entry.id);
}
