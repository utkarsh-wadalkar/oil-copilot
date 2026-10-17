"use client";

import { CaretRight, Info, WarningOctagon } from "@phosphor-icons/react";

import type { AnswerEnvelope } from "@/lib/contracts";
import { ALL_PARTS, envelopeForParts, type AnswerPart } from "@/lib/answerParts";
import { conflictExtras, isRowArray } from "@/lib/format";

import { DataValue } from "./DataValue";
import { EvidenceChips } from "./EvidenceChips";
import { VisualView } from "./VisualView";

/**
 * Everything the workspace shows for one server-validated `AnswerEnvelope`.
 *
 * Field by field this mirrors backend/app/schemas.py: summary, findings,
 * conflicts, warnings, visual, evidence, calculations. If a field is empty it is
 * not rendered at all, and no section invents a value to fill a gap.
 */
export interface AnswerActions {
  openEvidence(envelope: AnswerEnvelope, evidenceId: string): void;
}

export function AnswerEnvelopeView({
  envelope,
  actions,
  parts = ALL_PARTS,
}: {
  envelope: AnswerEnvelope;
  actions: AnswerActions | null;
  /** Which parts to show. A generative program selects from these; it never supplies values. */
  parts?: readonly AnswerPart[];
}) {
  const shown = envelopeForParts(envelope, parts);
  const has = (part: AnswerPart) => parts.includes(part);
  const onOpenEvidence = actions ? (evidenceId: string) => actions.openEvidence(envelope, evidenceId) : null;
  const window = envelope.date_window;

  return (
    <article className="answer">
      {has("meta") ? (
      <div className="answer__meta">
        <span>
          analysis date <span className="answer__meta-code">{envelope.analysis_date}</span>
        </span>
        {window ? (
          <span>
            window{" "}
            <span className="answer__meta-code">
              {window.start ?? "?"} to {window.end ?? "?"}
            </span>
          </span>
        ) : null}
        <span>
          result <span className="answer__meta-code">{envelope.result_id}</span>
        </span>
        {envelope.selected_well_ids.length > 0 ? (
          <span>
            wells <span className="answer__meta-code">{envelope.selected_well_ids.join(", ")}</span>
          </span>
        ) : null}
      </div>
      ) : null}

      {shown.summary ? <p className="answer__summary">{shown.summary}</p> : null}

      {shown.findings.length > 0 ? (
        <section className="section" aria-label="Findings">
          <h3 className="section__title">Findings</h3>
          {shown.findings.map((finding, index) => (
            <div className="finding" key={`${finding.label}-${index}`}>
              <div className="finding__head">
                <span className="finding__label">{finding.label}</span>
                {finding.unit ? <span className="finding__unit">{finding.unit}</span> : null}
                <EvidenceChips ids={finding.evidence_ids} envelope={envelope} onOpen={onOpenEvidence} />
              </div>
              {isRowArray(finding.value) ? (
                <details className="disclosure">
                  <summary className="disclosure__summary">
                    <CaretRight className="disclosure__caret" size={13} weight="regular" aria-hidden="true" />
                    {finding.value.length} row{finding.value.length === 1 ? "" : "s"} in this finding
                  </summary>
                  <div className="disclosure__body">
                    <DataValue value={finding.value} envelope={envelope} onOpenEvidence={onOpenEvidence} />
                  </div>
                </details>
              ) : (
                <DataValue value={finding.value} envelope={envelope} onOpenEvidence={onOpenEvidence} />
              )}
            </div>
          ))}
        </section>
      ) : null}

      {shown.warnings.length > 0 ? (
        <section className="section" aria-label="Warnings">
          <h3 className="section__title">Warnings</h3>
          <ul className="notices">
            {shown.warnings.map((warning) => (
              <li className="notice" key={warning}>
                <Info className="notice__icon" size={15} weight="regular" aria-hidden="true" />
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {shown.conflicts.length > 0 ? (
        <section className="section" aria-label="Conflicts">
          <h3 className="section__title">Conflicts</h3>
          <ul className="notices">
            {shown.conflicts.map((conflict, index) => (
              <li className="notice notice--warning" key={index}>
                <WarningOctagon className="notice__icon" size={15} weight="regular" aria-hidden="true" />
                <div className="notice__body">
                  <span className="notice__title">
                    {typeof conflict.message === "string" ? conflict.message : "Recorded conflict"}
                  </span>
                  {typeof conflict.target_id === "string" ? (
                    <span className="answer__meta-code">target {conflict.target_id}</span>
                  ) : null}
                  {conflictExtras(conflict).map(([key, value]) => (
                    <DataValue key={key} value={{ [key]: value }} envelope={envelope} onOpenEvidence={onOpenEvidence} depth={1} />
                  ))}
                  <EvidenceChips
                    ids={Array.isArray(conflict.evidence_ids) ? conflict.evidence_ids.filter((entry): entry is string => typeof entry === "string") : []}
                    envelope={envelope}
                    onOpen={onOpenEvidence}
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {has("visual") ? (
        <section className="section" aria-label="Visual">
          <VisualView visual={shown.visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />
        </section>
      ) : null}

      {shown.evidence.length > 0 ? (
        <section className="section" aria-label="Evidence">
          <div className="finding__head">
            <span className="section__title">
              {shown.evidence.length} source reference{shown.evidence.length === 1 ? "" : "s"}
            </span>
            <div className="chips">
              <EvidenceChips
                ids={shown.evidence.map((ref) => ref.id)}
                envelope={envelope}
                onOpen={onOpenEvidence}
              />
              <button
                type="button"
                className="chip"
                disabled={!onOpenEvidence}
                onClick={() => onOpenEvidence?.(shown.evidence[0].id)}
              >
                Open evidence
              </button>
            </div>
          </div>
        </section>
      ) : null}

      {shown.calculations.length > 0 ? (
        <details className="disclosure">
          <summary className="disclosure__summary">
            <CaretRight className="disclosure__caret" size={13} weight="regular" aria-hidden="true" />
            Calculations ({shown.calculations.length})
          </summary>
          <div className="disclosure__body stack">
            {shown.calculations.map((calculation, index) => (
              <DataValue
                key={index}
                value={calculation}
                envelope={envelope}
                onOpenEvidence={onOpenEvidence}
                depth={1}
              />
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}
