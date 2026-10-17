"use client";

import { ArrowClockwise, Plus } from "@phosphor-icons/react";

import type { ThreadSummary } from "@/lib/contracts";
import type { LoadStatus } from "@/lib/session";

/** The selected user's threads, plus a way to start a new one. */
export function ThreadSidebar({
  threads,
  status,
  activeThreadId,
  busy,
  onSelectThread,
  onNewThread,
  onRetryThreads,
}: {
  threads: ThreadSummary[];
  status: LoadStatus;
  activeThreadId: string | null;
  busy: boolean;
  onSelectThread: (threadId: string) => void;
  onNewThread: () => void;
  onRetryThreads: () => void;
}) {
  return (
    <nav className="sidebar" aria-label="Conversations">
      <button type="button" className="button" onClick={onNewThread} disabled={busy}>
        <Plus size={15} weight="regular" aria-hidden="true" />
        New conversation
      </button>

      <p className="sidebar__section-label">Threads</p>

      {status === "loading" ? (
        <div className="stack" aria-hidden="true">
          <div className="skeleton skeleton--line" />
          <div className="skeleton skeleton--line" />
          <div className="skeleton skeleton--line" />
        </div>
      ) : null}

      {status === "error" ? (
        <div className="error-state">
          <p className="error-state__title">Could not load threads</p>
          <button type="button" className="button" onClick={onRetryThreads}>
            <ArrowClockwise size={15} weight="regular" aria-hidden="true" />
            Retry
          </button>
        </div>
      ) : null}

      {status === "ready" && threads.length === 0 ? (
        <p className="empty-state">No threads yet. Start one to ask your first question.</p>
      ) : null}

      <ul className="thread-list">
        {threads.map((thread) => (
          <li key={thread.id}>
            <button
              type="button"
              className="thread-item"
              aria-current={thread.id === activeThreadId}
              onClick={() => onSelectThread(thread.id)}
            >
              <span className="thread-item__title">{thread.title ?? "Untitled thread"}</span>
              <span className="thread-item__meta">{thread.created_at.slice(0, 16).replace("T", " ")}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
