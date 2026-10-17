"use client";

import { Quotes } from "@phosphor-icons/react";

import type { AnswerEnvelope } from "@/lib/contracts";

/**
 * Evidence citations, rendered as compact chips.
 *
 * A chip resolves its id against the envelope the citation came from. When it
 * resolves, the chip shows that reference's position in the envelope's own
 * evidence list (`E1`, `E2`, ...) and carries the real title and path in its
 * label attribute, so nothing about the citation is invented. An id the envelope
 * does not list is still shown, verbatim in monospace, and still clickable: the
 * backend resolves any `source:start:end` id through GET /evidence.
 */
export function EvidenceChips({
  ids,
  envelope,
  onOpen,
}: {
  ids: string[];
  envelope: AnswerEnvelope;
  onOpen: ((evidenceId: string) => void) | null;
}) {
  if (ids.length === 0) return null;

  return (
    <span className="chips">
      {ids.map((id) => {
        const index = envelope.evidence.findIndex((ref) => ref.id === id);
        const ref = index >= 0 ? envelope.evidence[index] : null;
        const label = ref ? `E${index + 1}` : id;
        const describe = ref
          ? `${ref.title} — ${ref.path}${ref.start_line ? ` (lines ${ref.start_line}-${ref.end_line ?? ref.start_line})` : ""}`
          : `Evidence ${id}`;
        return (
          <button
            key={id}
            type="button"
            className="chip"
            title={describe}
            aria-label={`Open evidence ${describe}`}
            disabled={!onOpen}
            onClick={() => onOpen?.(id)}
          >
            <Quotes size={11} weight="regular" aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </span>
  );
}
