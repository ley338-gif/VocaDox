/**
 * Client-side "recently opened" MRU list for the Gespräche list page's
 * sidebar. Deliberately just conversation ids in localStorage (per
 * browser, never synced) -- the list page re-fetches each id via the
 * real API to render fresh title/status, so this never risks showing a
 * stale/fabricated snapshot, only a stale *order*.
 */
const STORAGE_KEY = "vocadox.recentConversations";
const MAX_ENTRIES = 6;

export function recordRecentConversation(id: string): void {
  try {
    const next = [id, ...getRecentConversationIds().filter((existing) => existing !== id)].slice(
      0,
      MAX_ENTRIES
    );
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // localStorage unavailable (private browsing, storage disabled) — skip silently.
  }
}

export function getRecentConversationIds(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((entry): entry is string => typeof entry === "string") : [];
  } catch {
    return [];
  }
}
