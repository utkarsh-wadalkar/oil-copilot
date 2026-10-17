"use client";

import { ArrowClockwise, Info } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { ApiError, createThread, getEvidenceSource, getResult, getThread, listThreads, listUsers, postMessage } from "@/lib/api";
import type { DatasetUser } from "@/lib/contracts";
import {
  buildTurns,
  initialWorkspaceState,
  newClientMessageId,
  PrivacyGuard,
  reduceWorkspace,
  type RequestScope,
} from "@/lib/session";
import { clearStoredIdentity, readStoredIdentity, writeStoredIdentity } from "@/lib/storage";

import { AnswerActionsContext, AnswerBlock, AnswerRegistryContext } from "./answerLibrary";
import { GenerativeAnswer } from "./GenerativeAnswer";
import type { AnswerActions } from "./AnswerEnvelopeView";
import { Composer } from "./Composer";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { PendingRow } from "./PendingRow";
import { SessionHeader } from "./SessionHeader";
import { ThreadSidebar } from "./ThreadSidebar";

/** The brief's default analysis date; the control can move it, but it starts here. */
const DEFAULT_ANALYSIS_DATE = "2026-10-17";

/**
 * Domain starter questions. These are prompts the operator may edit or discard,
 * not answers: choosing one only fills the composer, and the backend is still the
 * only thing that produces a result.
 */
const STARTERS = [
  "Which wells are not producing right now?",
  "Compare downtime across the inspected wells.",
  "Show any spills or leaks that were recorded.",
  "List inspections with a temperature reading above the threshold.",
];

/** A transport failure described for an operator, never dressed up as an answer. */
function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "The request failed before it reached the backend.";
}

/**
 * The workspace.
 *
 * This is the only stateful client component in the shell; the sidebar, drawer,
 * composer and answer renderer are leaves that take their state as props. Every
 * request is issued through a `PrivacyGuard` scope so a response that belongs to
 * a previous dataset user can neither paint nor dispatch.
 */
export function Workspace() {
  const [state, dispatch] = useReducer(reduceWorkspace, undefined, initialWorkspaceState);
  const [composerValue, setComposerValue] = useState("");
  const [analysisDate, setAnalysisDate] = useState(DEFAULT_ANALYSIS_DATE);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [focusToken, setFocusToken] = useState(0);

  const guardRef = useRef<PrivacyGuard | null>(null);
  if (guardRef.current === null) guardRef.current = new PrivacyGuard();
  const sessionRef = useRef(state.session);

  useEffect(() => {
    sessionRef.current = state.session;
  }, [state.session]);

  const session = state.session;
  const ready = session.userId !== null;
  const busy = session.pending !== null && session.error === null;

  const registry = useMemo(
    () => new Map(session.envelopes.map((envelope) => [envelope.result_id, envelope])),
    [session.envelopes],
  );
  const turns = useMemo(() => buildTurns(session.messages, session.envelopes), [session.messages, session.envelopes]);

  /* ------------------------------------------------------------------ users */

  const fetchUsers = useCallback(async (): Promise<DatasetUser[] | null> => {
    const guard = guardRef.current as PrivacyGuard;
    const scope = guard.begin();
    dispatch({ type: "users-loading" });
    try {
      const users = await listUsers(scope);
      if (!scope.isCurrent()) return null;
      dispatch({ type: "users-ready", users });
      return users;
    } catch (error) {
      if (!scope.isCurrent()) return null;
      dispatch({ type: "users-error", message: describeError(error) });
      return null;
    } finally {
      guard.release(scope);
    }
  }, []);

  const loadUsers = useCallback(() => {
    void fetchUsers();
  }, [fetchUsers]);

  /* --------------------------------------------------------------- threads */

  const loadThreads = useCallback(async (userId: string, scope?: RequestScope) => {
    const guard = guardRef.current as PrivacyGuard;
    const own = scope ?? guard.begin();
    if (!scope) dispatch({ type: "threads-loading" });
    try {
      const threads = await listThreads(userId, own);
      if (!own.isCurrent()) return;
      dispatch({ type: "threads-ready", threads });
    } catch (error) {
      if (!own.isCurrent()) return;
      dispatch({ type: "threads-error", message: describeError(error) });
    } finally {
      guard.release(own);
    }
  }, []);

  /** Re-read the thread titles after a turn, without flashing the loading state. */
  const refreshThreads = useCallback(async (userId: string) => {
    const guard = guardRef.current as PrivacyGuard;
    const scope = guard.begin();
    try {
      const threads = await listThreads(userId, scope);
      if (!scope.isCurrent()) return;
      dispatch({ type: "threads-ready", threads });
    } catch {
      // Keep the list already on screen rather than blanking it on a transient error.
    } finally {
      guard.release(scope);
    }
  }, []);

  const openThread = useCallback(async (threadId: string, userId: string) => {
    const guard = guardRef.current as PrivacyGuard;
    // Opening another thread abandons any turn still in flight for the old one.
    guard.reset();
    dispatch({ type: "thread-open", threadId });
    writeStoredIdentity({ userId, threadId });

    const scope = guard.begin();
    try {
      const detail = await getThread(userId, threadId, scope);
      if (!scope.isCurrent()) return;
      const envelopes = await Promise.all(detail.results.map((result) => getResult(userId, result.result_id, scope)));
      if (!scope.isCurrent()) return;
      dispatch({ type: "thread-detail", threadId, messages: detail.messages, envelopes });
    } catch (error) {
      if (!scope.isCurrent()) return;
      dispatch({ type: "thread-error", message: describeError(error) });
    } finally {
      guard.release(scope);
    }
  }, []);

  /* -------------------------------------------------------------- evidence */

  const fetchEvidence = useCallback(async (userId: string, evidenceId: string) => {
    const guard = guardRef.current as PrivacyGuard;
    const scope = guard.begin();
    dispatch({ type: "evidence-loading", evidenceId });
    try {
      const source = await getEvidenceSource(userId, evidenceId, scope);
      if (!scope.isCurrent()) return;
      dispatch({ type: "evidence-source", source });
    } catch (error) {
      if (!scope.isCurrent()) return;
      dispatch({ type: "evidence-error", message: describeError(error) });
    } finally {
      guard.release(scope);
    }
  }, []);

  const answerActions = useMemo<AnswerActions>(
    () => ({
      openEvidence: (envelope, evidenceId) => {
        const userId = sessionRef.current.userId;
        if (!userId) return;
        dispatch({
          type: "evidence-open",
          state: {
            answerQuestion: envelope.question,
            analysisDate: envelope.analysis_date,
            refs: envelope.evidence,
            selectedId: evidenceId,
            source: null,
            status: "loading",
            error: null,
          },
        });
        void fetchEvidence(userId, evidenceId);
      },
    }),
    [fetchEvidence],
  );

  /* ----------------------------------------------------------------- turns */

  const sendTurn = useCallback(
    async (content: string, date: string) => {
      const guard = guardRef.current as PrivacyGuard;
      const current = sessionRef.current;
      const userId = current.userId;
      if (!userId || !date) return;

      // Same question and date reuses the same client_message_id, which is what
      // makes a retry idempotent: the backend answers a replayed id from storage
      // instead of recording the question a second time.
      const clientMessageId =
        current.pending && current.pending.content === content && current.pending.analysisDate === date
          ? current.pending.clientMessageId
          : newClientMessageId();

      const messagesBefore = current.messages;
      dispatch({
        type: "turn-start",
        pending: { clientMessageId, content, analysisDate: date, sentAt: Date.now() },
      });

      const scope = guard.begin();
      try {
        let threadId = current.threadId;
        let createdThread = false;
        if (!threadId) {
          const thread = await createThread(userId, scope);
          if (!scope.isCurrent()) return;
          threadId = thread.id;
          createdThread = true;
          dispatch({ type: "thread-open", threadId });
          writeStoredIdentity({ userId, threadId });
          void refreshThreads(userId);
        }

        const turn = await postMessage(
          userId,
          threadId,
          { content, client_message_id: clientMessageId, analysis_date: date },
          scope,
        );
        if (!scope.isCurrent()) return;

        if (!turn.answer) {
          const wait =
            typeof turn.retry_after === "number" && turn.retry_after > 0
              ? ` Try again in about ${Math.ceil(turn.retry_after)} seconds.`
              : "";
          dispatch({ type: "turn-pending", message: `The backend is not ready to answer yet.${wait}` });
          return;
        }

        const base = createdThread ? [] : messagesBefore;
        setComposerValue("");
        dispatch({
          type: "turn-complete",
          messages: [
            ...base,
            { id: turn.message_id ?? `local-${clientMessageId}`, role: "user", content, created_at: "" },
          ],
          envelope: turn.answer,
        });
        if (turn.draft) {
          dispatch({
            type: "turn-notice",
            message:
              "The backend prepared a correction draft for this question. Reviewing and confirming corrections is not part of this workspace yet, so nothing has been published.",
          });
        }
        void refreshThreads(userId);
      } catch (error) {
        if (!scope.isCurrent()) return;
        dispatch({ type: "turn-failed", message: describeError(error), retryable: true });
      } finally {
        guard.release(scope);
      }
    },
    [refreshThreads],
  );

  /* ------------------------------------------------------------- handlers */

  const handleComposerSubmit = useCallback(() => {
    const content = composerValue.trim();
    if (!content) return;
    if (!sessionRef.current.userId) return;
    void sendTurn(content, analysisDate);
  }, [composerValue, analysisDate, sendTurn]);

  const handleRetry = useCallback(() => {
    const pending = sessionRef.current.pending;
    if (!pending) return;
    void sendTurn(pending.content, pending.analysisDate);
  }, [sendTurn]);

  const handleSelectUser = useCallback(
    (userId: string) => {
      const guard = guardRef.current as PrivacyGuard;
      const nextUserId = userId || null;
      // Abort everything in flight, then replace the whole session in one state
      // transition: the previous user's thread, messages, answers and evidence
      // are gone before any request for the new user is issued.
      guard.reset();
      dispatch({ type: "switch-user", userId: nextUserId });
      setComposerValue("");
      setSidebarOpen(false);
      if (nextUserId) {
        writeStoredIdentity({ userId: nextUserId, threadId: null });
        void loadThreads(nextUserId);
      } else {
        clearStoredIdentity();
      }
    },
    [loadThreads],
  );

  const handleNewThread = useCallback(async () => {
    const userId = sessionRef.current.userId;
    if (!userId) return;
    const guard = guardRef.current as PrivacyGuard;
    guard.reset();
    setComposerValue("");
    setSidebarOpen(false);
    const scope = guard.begin();
    try {
      const thread = await createThread(userId, scope);
      if (!scope.isCurrent()) return;
      dispatch({ type: "thread-detail", threadId: thread.id, messages: [], envelopes: [] });
      writeStoredIdentity({ userId, threadId: thread.id });
      void refreshThreads(userId);
    } catch (error) {
      if (!scope.isCurrent()) return;
      dispatch({ type: "thread-error", message: describeError(error) });
    } finally {
      guard.release(scope);
    }
  }, [refreshThreads]);

  const handleSelectThread = useCallback(
    (threadId: string) => {
      const userId = sessionRef.current.userId;
      if (!userId) return;
      setSidebarOpen(false);
      void openThread(threadId, userId);
    },
    [openThread],
  );

  const handleStarter = useCallback((question: string) => {
    setComposerValue(question);
    setFocusToken((token) => token + 1);
  }, []);

  const handleSelectEvidence = useCallback(
    (evidenceId: string) => {
      const userId = sessionRef.current.userId;
      if (!userId) return;
      void fetchEvidence(userId, evidenceId);
    },
    [fetchEvidence],
  );

  const handleRetryEvidence = useCallback(() => {
    const userId = sessionRef.current.userId;
    const evidence = sessionRef.current.evidence;
    if (!userId || !evidence) return;
    void fetchEvidence(userId, evidence.selectedId);
  }, [fetchEvidence]);

  const handleCloseEvidence = useCallback(() => {
    dispatch({ type: "evidence-close" });
  }, []);

  /** Retry a thread that failed to load, or restart the thread that failed to create. */
  const handleRetryConversation = useCallback(() => {
    const current = sessionRef.current;
    const userId = current.userId;
    if (!userId) return;
    if (current.threadId) void openThread(current.threadId, userId);
    else void handleNewThread();
  }, [openThread, handleNewThread]);

  /* -------------------------------------------------- one-shot boot effect */

  const bootedRef = useRef(false);
  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    void (async () => {
      const users = await fetchUsers();
      if (!users) return;
      const stored = readStoredIdentity();
      if (!stored.userId) return;
      if (!users.some((user) => user.id === stored.userId)) {
        clearStoredIdentity();
        return;
      }
      dispatch({ type: "switch-user", userId: stored.userId });
      // Open the remembered thread first: it resets the guard, so the thread
      // list load below starts in the new, live epoch.
      if (stored.threadId) void openThread(stored.threadId, stored.userId);
      void loadThreads(stored.userId);
    })();
  }, [fetchUsers, loadThreads, openThread]);

  /* ----------------------------------------------------------------- render */

  const evidence = session.evidence;
  const showWelcome =
    session.pending === null && turns.length === 0 && session.threadStatus !== "error";
  const conversationError = session.threadStatus === "error" && session.error ? session.error : null;

  return (
    <div
      className="shell"
      data-drawer={evidence ? "open" : "closed"}
      data-sidebar={sidebarOpen ? "open" : "closed"}
    >
      <SessionHeader
        users={state.users}
        usersStatus={state.usersStatus}
        usersError={state.usersError}
        selectedUserId={session.userId}
        onSelectUser={handleSelectUser}
        onRetryUsers={loadUsers}
        analysisDate={analysisDate}
        onAnalysisDateChange={(next) => {
          if (next) setAnalysisDate(next);
        }}
        dateLocked={session.pending !== null}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((open) => !open)}
      />

      <div className="shell__sidebar">
        <ThreadSidebar
          threads={session.threads}
          status={session.threadsStatus}
          activeThreadId={session.threadId}
          busy={!ready || busy}
          onSelectThread={handleSelectThread}
          onNewThread={() => void handleNewThread()}
          onRetryThreads={() => {
            const userId = sessionRef.current.userId;
            if (userId) void loadThreads(userId);
          }}
        />
      </div>

      <main className="shell__main">
        <div className="conversation">
          <div className="conversation__inner">
            {conversationError ? (
              <div className="error-state" role="alert">
                <p className="error-state__title">Could not open this conversation</p>
                <p>{conversationError.message}</p>
                <button type="button" className="button" onClick={handleRetryConversation}>
                  <ArrowClockwise size={15} weight="regular" aria-hidden="true" />
                  Retry
                </button>
              </div>
            ) : null}

            {showWelcome ? (
              <div className="welcome">
                <p className="welcome__eyebrow">Fieldnote</p>
                <h1 className="welcome__heading">Ask the dataset a question about well integrity.</h1>
                <p className="welcome__body">
                  Choose a dataset user in the header, then ask about well status, downtime, spills or compliance. Each
                  answer is composed by the backend from the inspected records and arrives with its sources attached.
                </p>
                <div className="starters">
                  {STARTERS.map((question) => (
                    <button
                      key={question}
                      type="button"
                      className="starter"
                      disabled={!ready}
                      onClick={() => handleStarter(question)}
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <AnswerRegistryContext.Provider value={registry}>
              <AnswerActionsContext.Provider value={answerActions}>
                {turns.map((turn) => {
                  if (turn.kind === "question") {
                    return (
                      <div className="turn" key={turn.key}>
                        <div className="bubble-user">
                          <span className="bubble-user__label">You asked</span>
                          {turn.content}
                        </div>
                      </div>
                    );
                  }
                  if (turn.kind === "answer") {
                    return (
                      <div className="turn" key={turn.key}>
                        {session.userId ? (
                          <GenerativeAnswer
                            resultId={turn.resultId}
                            userId={session.userId}
                            guard={guardRef.current as PrivacyGuard}
                          />
                        ) : (
                          <AnswerBlock resultId={turn.resultId} />
                        )}
                      </div>
                    );
                  }
                  return (
                    <div className="turn" key={turn.key}>
                      <article className="answer answer--plain">
                        <p className="answer__summary">{turn.content}</p>
                      </article>
                    </div>
                  );
                })}
              </AnswerActionsContext.Provider>
            </AnswerRegistryContext.Provider>

            {session.pending ? <PendingRow analysisDate={session.pending.analysisDate} /> : null}
          </div>
        </div>

        <div className="composer-dock">
          <div className="composer-dock__inner">
            {session.notice ? (
              <p className="notice notice--ok" role="status">
                <Info className="notice__icon" size={15} weight="regular" aria-hidden="true" />
                <span>{session.notice}</span>
              </p>
            ) : null}

            {session.pending && session.error ? (
              <div className="error-state" role="alert">
                <p className="error-state__title">The question could not be answered</p>
                <p>{session.error.message}</p>
                <button
                  type="button"
                  className="button"
                  onClick={handleRetry}
                  disabled={!session.error.retryable}
                >
                  <ArrowClockwise size={15} weight="regular" aria-hidden="true" />
                  Retry this question
                </button>
              </div>
            ) : null}

            <Composer
              value={composerValue}
              onChange={setComposerValue}
              onSubmit={handleComposerSubmit}
              busy={busy}
              ready={ready}
              analysisDate={analysisDate}
              focusToken={focusToken}
            />
          </div>
        </div>
      </main>

      {evidence ? (
        <div className="shell__drawer">
          <EvidenceDrawer
            state={evidence}
            onSelect={handleSelectEvidence}
            onRetry={handleRetryEvidence}
            onClose={handleCloseEvidence}
          />
        </div>
      ) : null}
    </div>
  );
}
