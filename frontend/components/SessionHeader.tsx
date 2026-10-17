"use client";

import { CalendarBlank, ChatCircleDots, List } from "@phosphor-icons/react";

import type { DatasetUser } from "@/lib/contracts";

/**
 * Wordmark, analysis date control and the dataset user picker.
 *
 * The picker is a dataset user chooser, not an author field: there is no text
 * input for a name anywhere in this app, and the selected id is the only value
 * that goes into the `X-User-ID` header.
 */
export function SessionHeader({
  users,
  usersStatus,
  usersError,
  selectedUserId,
  onSelectUser,
  onRetryUsers,
  analysisDate,
  onAnalysisDateChange,
  dateLocked,
  sidebarOpen,
  onToggleSidebar,
}: {
  users: DatasetUser[];
  usersStatus: "idle" | "loading" | "ready" | "error";
  usersError: string | null;
  selectedUserId: string | null;
  onSelectUser: (userId: string) => void;
  onRetryUsers: () => void;
  analysisDate: string;
  onAnalysisDateChange: (next: string) => void;
  dateLocked: boolean;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}) {
  return (
    <header className="shell__header">
      <button
        type="button"
        className="sidebar-toggle"
        aria-expanded={sidebarOpen}
        onClick={onToggleSidebar}
      >
        <List size={16} weight="regular" aria-hidden="true" />
        Threads
      </button>

      <div className="brand">
        <span className="brand__mark">
          <ChatCircleDots size={17} weight="regular" aria-hidden="true" />
          Fieldnote
        </span>
        <span className="brand__divider" aria-hidden="true">
          /
        </span>
        <span className="brand__product">Asset Intelligence</span>
      </div>

      <div className="header__controls">
        <div className="field">
          <label className="field__label" htmlFor="analysis-date">
            <CalendarBlank size={12} weight="regular" aria-hidden="true" /> Analysis date
          </label>
          <input
            id="analysis-date"
            className="field__control field__control--date"
            type="date"
            value={analysisDate}
            disabled={dateLocked}
            onChange={(event) => onAnalysisDateChange(event.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="dataset-user">
            Dataset user
          </label>
          <select
            id="dataset-user"
            className="field__control"
            value={selectedUserId ?? ""}
            disabled={usersStatus !== "ready" && usersStatus !== "error"}
            onChange={(event) => onSelectUser(event.target.value)}
          >
            <option value="">
              {usersStatus === "loading" || usersStatus === "idle" ? "Loading users..." : "Select a user"}
            </option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name ? `${user.name} (${user.id})` : user.id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {usersStatus === "error" ? (
        <div className="error-state header-error">
          <p className="error-state__title">Could not load the dataset users</p>
          <p>{usersError}</p>
          <button type="button" className="button" onClick={onRetryUsers}>
            Retry
          </button>
        </div>
      ) : null}
    </header>
  );
}
