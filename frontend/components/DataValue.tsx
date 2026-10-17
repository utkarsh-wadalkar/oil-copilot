"use client";

import type { ReactNode } from "react";

import type { AnswerEnvelope } from "@/lib/contracts";
import { columnKeys, formatScalar, isRecord, isRowArray } from "@/lib/format";

import { EvidenceChips } from "./EvidenceChips";

/**
 * Renders a value that came out of a validated envelope.
 *
 * The backend gives `Finding.value` as `Any` and puts whole row dicts in it, so
 * this has to cope with scalars, records and lists of records. Nothing is
 * recomputed, rounded or renamed: an object is printed key by key with the
 * backend's own key names, and a list of objects becomes a table whose columns
 * are the union of every row's keys, in first-seen order.
 */

const MAX_DEPTH = 3;

interface DataValueProps {
  value: unknown;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
  depth?: number;
}

export function DataValue({ value, envelope, onOpenEvidence, depth = 0 }: DataValueProps): ReactNode {
  if (isRowArray(value)) return <RowTable rows={value} envelope={envelope} onOpenEvidence={onOpenEvidence} />;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="answer__meta-code">no values</span>;
    return <span>{value.map((entry) => formatScalar(entry)).join(", ")}</span>;
  }

  if (isRecord(value)) {
    if (depth >= MAX_DEPTH) return <span className="record__value--number">{formatScalar(value)}</span>;
    return <RecordGrid record={value} envelope={envelope} onOpenEvidence={onOpenEvidence} depth={depth} />;
  }

  return <ScalarValue value={value} />;
}

export function ScalarValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span>{formatScalar(value)}</span>;
  if (typeof value === "number") return <span className="record__value--number">{formatScalar(value)}</span>;
  return <span>{formatScalar(value)}</span>;
}

function RecordGrid({
  record,
  envelope,
  onOpenEvidence,
  depth,
}: {
  record: Record<string, unknown>;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
  depth: number;
}) {
  const entries = Object.entries(record);
  if (entries.length === 0) return <span>not recorded</span>;

  return (
    <dl className="record">
      {entries.map(([key, entryValue]) => (
        <div key={key} className="record__row">
          <dt className="record__key">{key}</dt>
          <dd className="record__value">
            {key === "evidence_ids" && Array.isArray(entryValue) ? (
              <EvidenceChips
                ids={entryValue.filter((entry): entry is string => typeof entry === "string")}
                envelope={envelope}
                onOpen={onOpenEvidence}
              />
            ) : (
              <DataValue value={entryValue} envelope={envelope} onOpenEvidence={onOpenEvidence} depth={depth + 1} />
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function RowTable({
  rows,
  envelope,
  onOpenEvidence,
}: {
  rows: Record<string, unknown>[];
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  const columns = columnKeys(rows);
  return (
    <div className="data-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => {
                const cell = row[column];
                if (column === "evidence_ids" && Array.isArray(cell)) {
                  return (
                    <td key={column}>
                      <EvidenceChips
                        ids={cell.filter((entry): entry is string => typeof entry === "string")}
                        envelope={envelope}
                        onOpen={onOpenEvidence}
                      />
                    </td>
                  );
                }
                return (
                  <td key={column} data-numeric={typeof cell === "number"}>
                    {formatScalar(cell)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
