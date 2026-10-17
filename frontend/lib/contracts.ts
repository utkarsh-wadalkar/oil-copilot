/**
 * Client-side mirror of the backend REST contract.
 *
 * Source of truth: backend/app/schemas.py (AnswerEnvelope, VisualSpec, Finding,
 * EvidenceRef, VisualKind) and backend/app/routes.py (request/response bodies).
 * Nothing here may add a field, rename one, or invent an enum value: every shape
 * below is a direct transcription of those two files.
 *
 * This module must stay dependency-free apart from zod so the schema tests can
 * import it directly with node's type stripping.
 */
import { z } from "zod/v4";

/** backend/app/schemas.py: VisualKind */
export const VisualKindSchema = z.enum(["text", "card", "table", "line", "bar", "map", "heatmap"]);
export type VisualKind = z.infer<typeof VisualKindSchema>;

/** backend/app/schemas.py: EvidenceRef */
export const EvidenceRefSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  record_id: z.string().nullable().default(null),
  path: z.string(),
  title: z.string(),
  excerpt: z.string(),
  start_line: z.number().int().nullable().default(null),
  end_line: z.number().int().nullable().default(null),
});
export type EvidenceRef = z.infer<typeof EvidenceRefSchema>;

/** backend/app/schemas.py: Finding. `value` is `Any` on the server, so it stays unknown here. */
export const FindingSchema = z.object({
  label: z.string(),
  value: z.unknown(),
  unit: z.string().nullable().default(null),
  evidence_ids: z.array(z.string()).default([]),
});
export type Finding = z.infer<typeof FindingSchema>;

/** backend/app/schemas.py: VisualSpec */
export const VisualSpecSchema = z.object({
  kind: VisualKindSchema,
  title: z.string(),
  data: z.array(z.record(z.string(), z.unknown())).default([]),
  x: z.string().nullable().default(null),
  y: z.string().nullable().default(null),
  series: z.string().nullable().default(null),
});
export type VisualSpec = z.infer<typeof VisualSpecSchema>;

/**
 * backend/app/schemas.py: AnswerEnvelope.
 * `analysis_date` and the `date_window` values are `datetime.date` on the server,
 * which pydantic serialises to ISO-8601 date strings.
 */
export const AnswerEnvelopeSchema = z.object({
  result_id: z.string(),
  question: z.string(),
  analysis_date: z.string(),
  date_window: z.record(z.string(), z.string()).nullable().default(null),
  summary: z.string(),
  findings: z.array(FindingSchema).default([]),
  evidence: z.array(EvidenceRefSchema).default([]),
  conflicts: z.array(z.record(z.string(), z.unknown())).default([]),
  visual: VisualSpecSchema,
  selected_well_ids: z.array(z.string()).default([]),
  calculations: z.array(z.record(z.string(), z.unknown())).default([]),
  revisions: z.record(z.string(), z.string()).default({}),
  warnings: z.array(z.string()).default([]),
  previous_result_id: z.string().nullable().default(null),
  comparison: z.record(z.string(), z.unknown()).nullable().default(null),
});
export type AnswerEnvelope = z.infer<typeof AnswerEnvelopeSchema>;

/** routes.py GET /users -> {users: [{id, name, role, team}]} */
/**
 * POST /results/{id}/ui — a generative layout for an already validated answer.
 *
 * `program` is OpenUI Lang that references the answer by id; it carries no values.
 * `enabled: false` with a reason is the honest "render deterministically" answer.
 */
export const UiProgramSchema = z.object({
  result_id: z.string(),
  enabled: z.boolean(),
  model: z.string().nullable(),
  program: z.string().nullable(),
  reason: z.string().nullable(),
});
export type UiProgram = z.infer<typeof UiProgramSchema>;

export const DatasetUserSchema = z.object({
  id: z.string(),
  name: z.string().nullable().default(null),
  role: z.string().nullable().default(null),
  team: z.string().nullable().default(null),
});
export type DatasetUser = z.infer<typeof DatasetUserSchema>;
export const UserListSchema = z.object({ users: z.array(DatasetUserSchema) });

/** routes.py GET /conversations -> {conversations: [{id, title, created_at}]} */
export const ThreadSummarySchema = z.object({
  id: z.string(),
  title: z.string().nullable().default(null),
  created_at: z.string(),
});
export type ThreadSummary = z.infer<typeof ThreadSummarySchema>;
export const ThreadListSchema = z.object({ conversations: z.array(ThreadSummarySchema) });

/** routes.py GET /conversations/{id} -> {id, title, messages, results} */
export const ThreadMessageSchema = z.object({
  id: z.string(),
  role: z.string(),
  content: z.string(),
  created_at: z.string(),
});
export type ThreadMessage = z.infer<typeof ThreadMessageSchema>;

export const ThreadResultRefSchema = z.object({
  result_id: z.string(),
  question: z.string(),
  created_at: z.string(),
});
export type ThreadResultRef = z.infer<typeof ThreadResultRefSchema>;

export const ThreadDetailSchema = z.object({
  id: z.string(),
  title: z.string().nullable().default(null),
  messages: z.array(ThreadMessageSchema),
  results: z.array(ThreadResultRefSchema),
});
export type ThreadDetail = z.infer<typeof ThreadDetailSchema>;

/** routes.py GET /results/{id} -> {result_id, question, answer, validity, previous_result_id, analysis_date} */
export const SavedResultSchema = z.object({
  result_id: z.string(),
  question: z.string(),
  answer: AnswerEnvelopeSchema,
  validity: z.record(z.string(), z.unknown()).default({}),
  previous_result_id: z.string().nullable().default(null),
  analysis_date: z.string().nullable().default(null),
});
export type SavedResult = z.infer<typeof SavedResultSchema>;

/** routes.py POST /conversations/{id}/messages response. `answer` is null while the model is rate limited. */
export const DraftSummarySchema = z.record(z.string(), z.unknown());

export const TurnResponseSchema = z.object({
  status: z.string(),
  conversation_id: z.string(),
  message_id: z.string().nullable().optional(),
  result_id: z.string().nullable().optional(),
  answer: AnswerEnvelopeSchema.nullable().default(null),
  draft: DraftSummarySchema.nullable().default(null),
  warnings: z.array(z.string()).default([]),
  retry_after: z.number().nullable().optional(),
});
export type TurnResponse = z.infer<typeof TurnResponseSchema>;

/** routes.py POST /conversations -> {id, title, created_at} */
export const CreatedThreadSchema = z.object({
  id: z.string(),
  title: z.string().nullable().default(null),
  created_at: z.string(),
});

/** routes.py GET /evidence/{id:path} returns an EvidenceRef. */
export const SourceExcerptSchema = EvidenceRefSchema;

export const ERROR_STATUS_LABELS: Record<number, string> = {
  401: "No dataset user was sent with the request",
  403: "That dataset user is not in this dataset",
  404: "Not found",
  409: "The request conflicted with an earlier one",
  422: "The backend rejected the request",
  500: "The backend could not produce an answer",
  502: "The backend is unreachable",
  503: "The backend is not ready",
};
