/**
 * Session state and the privacy guard.
 *
 * This module is deliberately free of React and of every browser API so the
 * privacy rules can be asserted in `npm test` with node alone. It imports types
 * only (`import type`), which node's type stripping removes, so the runtime
 * module has no imports at all.
 *
 * Two rules from the brief live here:
 *
 *  1. Switching dataset user clears the thread, messages, results and evidence
 *     *synchronously*: `sessionForUser()` returns a whole new state object and
 *     the reducer applies it in a single transition, so no intermediate paint
 *     can show the previous user's data.
 *  2. In-flight responses are cancelled or discarded: `PrivacyGuard.reset()`
 *     aborts every registered request and bumps the epoch, and `ifCurrent()`
 *     refuses to run a reducer action whose request belongs to an old epoch.
 */
import type { AnswerEnvelope, DatasetUser, EvidenceRef, ThreadMessage, ThreadSummary } from "./contracts";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

/** A question that has been sent and whose answer has not settled yet. */
export interface PendingTurn {
  clientMessageId: string;
  content: string;
  analysisDate: string;
  sentAt: number;
}

export interface TurnError {
  message: string;
  /** True when the same message can be sent again with the same client_message_id. */
  retryable: boolean;
}

/** The evidence drawer, scoped to one answer so it can never outlive its result. */
export interface EvidenceState {
  answerQuestion: string;
  analysisDate: string;
  refs: EvidenceRef[];
  selectedId: string;
  source: EvidenceRef | null;
  status: LoadStatus;
  error: string | null;
}

/** Everything the selected dataset user owns. All of it is cleared on a user switch. */
export interface SessionState {
  userId: string | null;
  threadId: string | null;
  threads: ThreadSummary[];
  threadsStatus: LoadStatus;
  messages: ThreadMessage[];
  threadStatus: LoadStatus;
  envelopes: AnswerEnvelope[];
  pending: PendingTurn | null;
  evidence: EvidenceState | null;
  error: TurnError | null;
  /** Informational banner (for example a prepared correction draft). Never an error. */
  notice: string | null;
}

export interface WorkspaceState {
  session: SessionState;
  /** The dataset user picker is not user-scoped data, so it survives a switch. */
  users: DatasetUser[];
  usersStatus: LoadStatus;
  usersError: string | null;
}

export const emptySession = (): SessionState => ({
  userId: null,
  threadId: null,
  threads: [],
  threadsStatus: "idle",
  messages: [],
  threadStatus: "idle",
  envelopes: [],
  pending: null,
  evidence: null,
  error: null,
  notice: null,
});

/** The one and only place a user switch is expressed: a brand new, empty session. */
export const sessionForUser = (userId: string | null): SessionState => ({ ...emptySession(), userId });

export const initialWorkspaceState = (): WorkspaceState => ({
  session: emptySession(),
  users: [],
  usersStatus: "idle",
  usersError: null,
});

export type WorkspaceAction =
  | { type: "users-loading" }
  | { type: "users-ready"; users: DatasetUser[] }
  | { type: "users-error"; message: string }
  | { type: "switch-user"; userId: string | null }
  | { type: "threads-loading" }
  | { type: "threads-ready"; threads: ThreadSummary[] }
  | { type: "threads-error"; message: string }
  | { type: "thread-open"; threadId: string | null }
  | { type: "thread-detail"; threadId: string; messages: ThreadMessage[]; envelopes: AnswerEnvelope[] }
  | { type: "thread-error"; message: string }
  | { type: "turn-start"; pending: PendingTurn }
  | { type: "turn-complete"; messages: ThreadMessage[]; envelope: AnswerEnvelope | null }
  | { type: "turn-failed"; message: string; retryable: boolean }
  | { type: "turn-pending"; message: string }
  | { type: "turn-notice"; message: string | null }
  | { type: "evidence-open"; state: EvidenceState }
  | { type: "evidence-loading"; evidenceId: string }
  | { type: "evidence-source"; source: EvidenceRef }
  | { type: "evidence-error"; message: string }
  | { type: "evidence-close" };

export function reduceWorkspace(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  switch (action.type) {
    case "users-loading":
      return { ...state, usersStatus: "loading", usersError: null };
    case "users-ready":
      return { ...state, usersStatus: "ready", users: action.users, usersError: null };
    case "users-error":
      return { ...state, usersStatus: "error", usersError: action.message };
    case "switch-user":
      // Whole-session replacement. Threads, messages, results, evidence and any
      // pending turn belong to the previous user and are dropped in this one
      // synchronous state transition, before any fetch for the new user starts.
      return { ...state, session: sessionForUser(action.userId), usersError: null };
    case "threads-loading":
      return { ...state, session: { ...state.session, threadsStatus: "loading" } };
    case "threads-ready":
      return { ...state, session: { ...state.session, threadsStatus: "ready", threads: action.threads } };
    case "threads-error":
      return {
        ...state,
        session: { ...state.session, threadsStatus: "error", error: { message: action.message, retryable: true } },
      };
    case "thread-open":
      return {
        ...state,
        session: {
          ...state.session,
          threadId: action.threadId,
          messages: [],
          envelopes: [],
          pending: null,
          evidence: null,
          error: null,
          threadStatus: action.threadId ? "loading" : "idle",
        },
      };
    case "thread-detail":
      return {
        ...state,
        session: {
          ...state.session,
          threadId: action.threadId,
          messages: action.messages,
          envelopes: action.envelopes,
          threadStatus: "ready",
          error: null,
        },
      };
    case "thread-error":
      return {
        ...state,
        session: { ...state.session, threadStatus: "error", error: { message: action.message, retryable: true } },
      };
    case "turn-start":
      return { ...state, session: { ...state.session, pending: action.pending, error: null, notice: null } };
    case "turn-complete":
      return {
        ...state,
        session: {
          ...state.session,
          pending: null,
          messages: action.messages,
          envelopes: action.envelope ? [...state.session.envelopes, action.envelope] : state.session.envelopes,
          error: null,
        },
      };
    case "turn-failed":
      // `pending` stays set on purpose: a retry must reuse the same
      // client_message_id, which is what makes the backend treat it as the same
      // turn rather than a second question.
      return { ...state, session: { ...state.session, error: { message: action.message, retryable: action.retryable } } };
    case "turn-pending":
      // Rate limited: the turn is still outstanding, so `pending` stays set and
      // the retry reuses the same client_message_id.
      return { ...state, session: { ...state.session, error: { message: action.message, retryable: true } } };
    case "turn-notice":
      return { ...state, session: { ...state.session, notice: action.message } };
    case "evidence-open":
      return { ...state, session: { ...state.session, evidence: action.state } };
    case "evidence-loading":
      return state.session.evidence
        ? { ...state, session: { ...state.session, evidence: { ...state.session.evidence, selectedId: action.evidenceId, status: "loading", error: null, source: null } } }
        : state;
    case "evidence-source":
      return state.session.evidence
        ? { ...state, session: { ...state.session, evidence: { ...state.session.evidence, status: "ready", source: action.source, error: null } } }
        : state;
    case "evidence-error":
      return state.session.evidence
        ? { ...state, session: { ...state.session, evidence: { ...state.session.evidence, status: "error", error: action.message } } }
        : state;
    case "evidence-close":
      return { ...state, session: { ...state.session, evidence: null } };
    default:
      return state;
  }
}

/** One request's identity: the epoch it was issued in, and its abort signal. */
export interface RequestScope {
  readonly epoch: number;
  readonly signal: AbortSignal;
  /** False once the scope's epoch has been superseded. */
  isCurrent(): boolean;
}

/**
 * Monotonic epoch plus abort registry. `reset()` is what a user switch calls:
 * it aborts every in-flight request for the previous user and invalidates their
 * scopes, so a slow response can neither paint nor dispatch.
 */
export class PrivacyGuard {
  private epoch = 0;
  private controllers = new Set<AbortController>();

  begin(): RequestScope {
    const epoch = this.epoch;
    const controller = new AbortController();
    this.controllers.add(controller);
    const guard = this;
    return {
      epoch,
      signal: controller.signal,
      isCurrent: () => guard.isCurrent(epoch) && !controller.signal.aborted,
    };
  }

  isCurrent(epoch: number): boolean {
    return epoch === this.epoch;
  }

  /** Abort everything in flight and invalidate scopes issued before now. */
  reset(): void {
    this.epoch += 1;
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
  }

  /** Release a scope's controller once its request has settled. */
  release(scope: RequestScope): void {
    for (const controller of this.controllers) {
      if (controller.signal === scope.signal) this.controllers.delete(controller);
    }
  }
}

/** Run `fn` only if the scope still belongs to the live epoch. */
export function ifCurrent<T>(scope: RequestScope, fn: () => T): T | undefined {
  if (!scope.isCurrent()) return undefined;
  return fn();
}

/**
 * One renderable item in the conversation column.
 *
 * An `answer` item carries only a result id: the answer itself is the validated
 * envelope in the registry, so nothing about it is rebuilt here.
 */
export type ThreadTurn =
  | { kind: "question"; key: string; content: string }
  | { kind: "answer"; key: string; resultId: string }
  | { kind: "note"; key: string; content: string };

/**
 * Pair the thread's messages with its answer envelopes.
 *
 * Every completed turn stores exactly one assistant message and one result, so
 * the nth assistant message belongs to the nth envelope. That positional guess
 * is only accepted when the envelope's own `question` matches the question the
 * user actually asked; otherwise the server's assistant text is shown verbatim
 * instead of attaching the wrong answer to it. Envelopes with no assistant
 * message (a turn that finished locally before the thread was re-read) are
 * appended in order.
 */
export function buildTurns(messages: ThreadMessage[], envelopes: AnswerEnvelope[]): ThreadTurn[] {
  const turns: ThreadTurn[] = [];
  let envelopeIndex = 0;
  let lastQuestion = "";

  for (const message of messages) {
    if (message.role === "user") {
      lastQuestion = message.content;
      turns.push({ kind: "question", key: message.id, content: message.content });
      continue;
    }
    const candidate = envelopes[envelopeIndex];
    if (candidate && candidate.question.trim() === lastQuestion.trim()) {
      turns.push({ kind: "answer", key: candidate.result_id, resultId: candidate.result_id });
      envelopeIndex += 1;
    } else {
      turns.push({ kind: "note", key: message.id, content: message.content });
    }
  }

  for (; envelopeIndex < envelopes.length; envelopeIndex += 1) {
    const envelope = envelopes[envelopeIndex];
    turns.push({ kind: "answer", key: envelope.result_id, resultId: envelope.result_id });
  }

  return turns;
}

/** A stable-enough unique id for `client_message_id`. */
export function newClientMessageId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
