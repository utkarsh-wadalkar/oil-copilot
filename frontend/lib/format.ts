/**
 * Faithful formatting of values that arrive from the backend.
 *
 * Rules: no rounding, no unit conversion, no key renaming, no plausible-looking
 * defaults. A value the backend did not send is shown as "not recorded", never
 * guessed. Keys stay exactly as the backend spells them (monospace in the UI) so
 * an engineer can match what they see against the contract.
 */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isRowArray(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.length > 0 && value.every(isRecord);
}

/** Render a leaf value. Booleans read as yes/no; null is never dressed up. */
export function formatScalar(value: unknown): string {
  if (value === null || value === undefined) return "not recorded";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : String(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(formatScalar).join(", ");
  return JSON.stringify(value);
}

/** Column order for a table: first-seen across every row, so no row's keys are hidden. */
export function columnKeys(rows: Record<string, unknown>[]): string[] {
  const keys: string[] = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!keys.includes(key)) keys.push(key);
    }
  }
  return keys;
}

/** Evidence ids attached to a row or finding, in the order the backend sent them. */
export function evidenceIdsOf(value: unknown): string[] {
  if (!isRecord(value)) return [];
  const raw = value.evidence_ids;
  if (!Array.isArray(raw)) return [];
  return raw.filter((entry): entry is string => typeof entry === "string");
}

/** Dates and windows are printed exactly as the backend formats them (ISO-8601). */
export function formatWindow(window: Record<string, string> | null): string | null {
  if (!window) return null;
  const start = window.start;
  const end = window.end;
  if (start && end) return `${start} to ${end}`;
  return start ?? end ?? null;
}

/** Pull the source-vs-value pairs out of a conflict record without hiding any key. */
export function conflictExtras(conflict: Record<string, unknown>): Array<[string, unknown]> {
  return Object.entries(conflict).filter(([key]) => key !== "message" && key !== "target_id" && key !== "evidence_ids");
}
