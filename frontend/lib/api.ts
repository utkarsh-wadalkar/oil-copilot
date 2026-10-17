/**
 * REST client for the FastAPI backend.
 *
 * Read backend/app/routes.py alongside this file: every path, body field and
 * header below exists there. Nothing is invented, and every request carries the
 * selected dataset user's id in `X-User-ID`, which is the only identity the
 * frontend has (there is no author or user name input anywhere in the UI).
 *
 * `NEXT_PUBLIC_API_BASE_URL` is a public origin, not a secret. The backend's
 * secrets (OLLAMA_API_KEY, NEO4J_PASSWORD, DATABASE_URL...) are never read by
 * this app and never become a browser-exposed variable.
 */
import { z } from "zod/v4";

import {
  AnswerEnvelopeSchema,
  CreatedThreadSchema,
  SavedResultSchema,
  SourceExcerptSchema,
  ThreadDetailSchema,
  ThreadListSchema,
  TurnResponseSchema,
  UiProgramSchema,
  UserListSchema,
  type AnswerEnvelope,
  type DatasetUser,
  type EvidenceRef,
  type ThreadDetail,
  type ThreadSummary,
  type TurnResponse,
} from "./contracts";
import type { RequestScope } from "./session";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function describeDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return "";
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function send(
  path: string,
  init: { method: string; userId?: string | null; body?: unknown; scope: RequestScope },
): Promise<unknown> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.userId) headers["X-User-ID"] = init.userId;
  if (init.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method,
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.scope.signal,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(502, `Could not reach the backend at ${API_BASE_URL}`, error);
  }

  const payload = await readBody(response);
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : payload;
    const described = describeDetail(detail);
    throw new ApiError(
      response.status,
      described ? `Backend ${response.status}: ${described}` : `Backend ${response.status}`,
      payload,
    );
  }
  return payload;
}

/**
 * Validate the transport payload with the same schema the renderer trusts.
 * A backend contract change surfaces as a visible error, never as a half-rendered
 * answer built from unknown fields.
 */
function validate<T>(schema: z.ZodType<T>, payload: unknown, what: string): T {
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(0, `${what} did not match the expected contract`, parsed.error.issues);
  }
  return parsed.data;
}

/** GET /users (no identity required: the picker runs before a user is chosen). */
export async function listUsers(scope: RequestScope): Promise<DatasetUser[]> {
  const payload = await send("/users", { method: "GET", scope });
  return validate(UserListSchema, payload, "The dataset user list").users;
}

/** GET /conversations */
export async function listThreads(userId: string, scope: RequestScope): Promise<ThreadSummary[]> {
  const payload = await send("/conversations", { method: "GET", userId, scope });
  return validate(ThreadListSchema, payload, "The thread list").conversations;
}

/** POST /conversations */
export async function createThread(userId: string, scope: RequestScope, title?: string): Promise<ThreadSummary> {
  const payload = await send("/conversations", { method: "POST", userId, body: { title: title ?? null }, scope });
  return validate(CreatedThreadSchema, payload, "The new thread");
}

/** GET /conversations/{id} */
export async function getThread(userId: string, threadId: string, scope: RequestScope): Promise<ThreadDetail> {
  const payload = await send(`/conversations/${encodeURIComponent(threadId)}`, { method: "GET", userId, scope });
  return validate(ThreadDetailSchema, payload, "The thread");
}

/** GET /results/{id} */
export async function getResult(userId: string, resultId: string, scope: RequestScope): Promise<AnswerEnvelope> {
  const payload = await send(`/results/${encodeURIComponent(resultId)}`, { method: "GET", userId, scope });
  return validate(SavedResultSchema, payload, "The saved result").answer;
}

/**
 * POST /results/{id}/ui
 *
 * Asks the server to compose a generative layout for an already validated answer. The
 * model chooses which parts to show; it never supplies a value. `enabled: false` (or a
 * missing program) is a normal answer meaning "render it deterministically", not an error.
 */
export async function getUiProgram(
  userId: string,
  resultId: string,
  scope: RequestScope,
): Promise<{ enabled: boolean; model: string | null; program: string | null; reason: string | null }> {
  const payload = await send(`/results/${encodeURIComponent(resultId)}/ui`, {
    method: "POST",
    userId,
    scope,
  });
  return UiProgramSchema.parse(payload);
}

/**
 * POST /conversations/{id}/messages
 *
 * The body matches routes.py `MessageIn`. Reusing the same `client_message_id`
 * with the same content and analysis date is what makes a retry idempotent; the
 * backend answers a replayed id with the stored envelope.
 */
export async function postMessage(
  userId: string,
  threadId: string,
  body: { content: string; client_message_id: string; analysis_date: string },
  scope: RequestScope,
): Promise<TurnResponse> {
  const payload = await send(`/conversations/${encodeURIComponent(threadId)}/messages`, {
    method: "POST",
    userId,
    body,
    scope,
  });
  return validate(TurnResponseSchema, payload, "The answer");
}

/**
 * GET /evidence/{evidence_id:path}
 *
 * The evidence id is `source_id:start_line:end_line` (see routes.py
 * `get_evidence`), so each colon-separated part is escaped on its own and the
 * colons are preserved: encoding the whole id would turn them into `%3A`.
 */
export async function getEvidenceSource(
  userId: string,
  evidenceId: string,
  scope: RequestScope,
): Promise<EvidenceRef> {
  const encoded = evidenceId.split(":").map(encodeURIComponent).join(":");
  const payload = await send(`/evidence/${encoded}`, { method: "GET", userId, scope });
  return validate(SourceExcerptSchema, payload, "The evidence source");
}

export { AnswerEnvelopeSchema };
