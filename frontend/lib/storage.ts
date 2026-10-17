/**
 * Browser storage for the selected dataset user and thread, and nothing else.
 *
 * Deliberately stores two ids. Message bodies, answers, evidence and any
 * correction draft stay in memory for the life of the tab, so a shared machine
 * cannot leak one operator's results to the next.
 */
export interface StoredIdentity {
  userId: string | null;
  threadId: string | null;
}

const KEY = "copilot.identity";

const EMPTY: StoredIdentity = { userId: null, threadId: null };

export function readStoredIdentity(): StoredIdentity {
  if (typeof window === "undefined") return EMPTY;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return EMPTY;
    const record = parsed as Record<string, unknown>;
    return {
      userId: typeof record.userId === "string" ? record.userId : null,
      threadId: typeof record.threadId === "string" ? record.threadId : null,
    };
  } catch {
    return EMPTY;
  }
}

export function writeStoredIdentity(identity: StoredIdentity): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ userId: identity.userId, threadId: identity.threadId }),
    );
  } catch {
    // Storage can be unavailable (private mode, quota). Losing the remembered
    // ids is harmless; losing a security boundary would not be.
  }
}

export function clearStoredIdentity(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // See above.
  }
}
