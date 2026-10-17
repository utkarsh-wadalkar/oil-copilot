"use client";

import { ChartLine } from "@phosphor-icons/react";

import type { AnswerEnvelope, VisualSpec } from "@/lib/contracts";
import { formatScalar } from "@/lib/format";

import { DataValue } from "./DataValue";
import { EvidenceChips } from "./EvidenceChips";

/**
 * The backend chooses `visual.kind` (see backend/app/knowledge.py); the frontend
 * never picks one and never recomputes a series.
 *
 * Phase 4a renders `text` (the rows printed as key/value lines) and `card` (the
 * same rows in a bordered card). Every other kind gets an explicit notice naming
 * the kind and the number of rows the backend actually returned, so the gap is
 * visible instead of a chart being faked from data that is not charted yet.
 */
export function VisualView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  if (visual.kind === "text") return <TextView visual={visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />;
  if (visual.kind === "card") return <CardView visual={visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />;
  return <UnsupportedView visual={visual} />;
}

function VisualHeading({ visual }: { visual: VisualSpec }) {
  return (
    <div className="finding__head">
      <span className="visual__title">{visual.title}</span>
      <span className="visual__kind">{visual.kind}</span>
    </div>
  );
}

function TextView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  return (
    <div>
      <VisualHeading visual={visual} />
      {visual.data.length === 0 ? (
        <p className="empty-state">The backend returned no rows for this visual.</p>
      ) : (
        <div className="text-visual">
          {visual.data.map((row, index) => (
            <p className="text-visual__row" key={index}>
              {Object.entries(row).map(([key, value]) => (
                <span key={key}>
                  <span className="text-visual__key">{key}</span>{" "}
                  {key === "evidence_ids" && Array.isArray(value) ? (
                    <EvidenceChips
                      ids={value.filter((entry): entry is string => typeof entry === "string")}
                      envelope={envelope}
                      onOpen={onOpenEvidence}
                    />
                  ) : (
                    formatScalar(value)
                  )}
                </span>
              ))}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function CardView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  return (
    <div>
      <VisualHeading visual={visual} />
      {visual.data.length === 0 ? (
        <p className="empty-state">The backend returned no rows for this visual.</p>
      ) : (
        <div className="stack">
          {visual.data.map((row, index) => (
            <div className="card-visual" key={index}>
              <DataValue value={row} envelope={envelope} onOpenEvidence={onOpenEvidence} depth={1} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function UnsupportedView({ visual }: { visual: VisualSpec }) {
  const axes = [visual.x ? `x ${visual.x}` : null, visual.y ? `y ${visual.y}` : null, visual.series ? `series ${visual.series}` : null].filter(
    (entry): entry is string => Boolean(entry),
  );

  return (
    <div className="visual-unsupported">
      <p className="visual-unsupported__head">
        <ChartLine size={16} weight="regular" aria-hidden="true" />
        {visual.title}
      </p>
      <p>
        A <span className="visual__kind">{visual.kind}</span> visual is not supported in this workspace yet. The backend
        returned {visual.data.length} row{visual.data.length === 1 ? "" : "s"} for it, which stay out of the page rather
        than being drawn approximately.
      </p>
      {axes.length > 0 ? <p className="visual__kind">{axes.join(" · ")}</p> : null}
    </div>
  );
}
