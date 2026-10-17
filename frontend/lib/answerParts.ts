/**
 * Selective rendering of one validated `AnswerEnvelope`.
 *
 * A generative UI program may choose *which parts* of an answer to show and in what
 * order, and may add its own prose annotation. It may never supply a value: every part
 * is resolved from the server-validated envelope held by the workspace, so a model
 * cannot invent a number, a well or a citation.
 */
import type { AnswerEnvelope } from "@/lib/contracts";

export const ANSWER_PARTS = [
  "meta",
  "summary",
  "findings",
  "warnings",
  "conflicts",
  "visual",
  "evidence",
  "calculations",
] as const;

export type AnswerPart = (typeof ANSWER_PARTS)[number];

export const ALL_PARTS: readonly AnswerPart[] = ANSWER_PARTS;

/** Blank out every field a part does not own, so the existing view hides it. */
export function envelopeForParts(envelope: AnswerEnvelope, parts: readonly AnswerPart[]): AnswerEnvelope {
  const has = (part: AnswerPart) => parts.includes(part);
  return {
    ...envelope,
    summary: has("summary") ? envelope.summary : "",
    findings: has("findings") ? envelope.findings : [],
    warnings: has("warnings") ? envelope.warnings : [],
    conflicts: has("conflicts") ? envelope.conflicts : [],
    evidence: has("evidence") ? envelope.evidence : [],
    calculations: has("calculations") ? envelope.calculations : [],
    visual: has("visual") ? envelope.visual : { ...envelope.visual, data: [], title: "" },
  };
}
