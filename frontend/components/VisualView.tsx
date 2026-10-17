"use client";

import { ChartLine } from "@phosphor-icons/react";

import type { AnswerEnvelope, VisualSpec } from "@/lib/contracts";
import { columnKeys, formatScalar, isRecord, isRowArray } from "@/lib/format";

import { DataValue } from "./DataValue";
import { EvidenceChips } from "./EvidenceChips";

/**
 * The backend chooses `visual.kind` (see backend/app/knowledge.py); the frontend
 * never picks one and never recomputes a series or a total.
 *
 * Every renderer below is a *drawing* of the rows the backend returned:
 *  - `table`   rows exactly as sent, columns in first-seen order;
 *  - `line`    one point per row, straight segments, no smoothing or interpolation;
 *  - `bar`     one bar per row, length proportional to the value in that row;
 *  - `map`     wells at their recorded lat/lon on a schematic field grid (no tiles);
 *  - `heatmap` the area × month grid with the counts the backend computed.
 *
 * Nothing here aggregates, fills gaps, sorts by an unstated rule, or invents a
 * unit. If a required field is missing the visual says which one, rather than
 * drawing something plausible.
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
  if (visual.kind === "table") return <TableView visual={visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />;
  if (visual.kind === "line") return <LineView visual={visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />;
  if (visual.kind === "bar") return <BarView visual={visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />;
  if (visual.kind === "map") return <MapView visual={visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />;
  if (visual.kind === "heatmap") return <HeatmapView visual={visual} envelope={envelope} onOpenEvidence={onOpenEvidence} />;
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

function MissingField({ visual, field }: { visual: VisualSpec; field: string }) {
  return (
    <div className="visual-unsupported">
      <p className="visual-unsupported__head">
        <ChartLine size={16} weight="regular" aria-hidden="true" />
        {visual.title}
      </p>
      <p>
        The backend returned {visual.data.length} row{visual.data.length === 1 ? "" : "s"} for a{" "}
        <span className="visual__kind">{visual.kind}</span> visual, but no <code>{field}</code> data to draw. Nothing is
        drawn approximately.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- text / card

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

// ---------------------------------------------------------------- table

/** Evidence ids are the one column shown as chips rather than text. */
function orderedColumns(rows: Record<string, unknown>[]): string[] {
  const keys = columnKeys(rows).filter((key) =>
    // A column that is empty in every row is not information; showing "not recorded"
    // eight times makes the real fields harder to find.
    rows.some((row) => row[key] !== null && row[key] !== undefined && row[key] !== ""),
  );
  const priority = ["well_id", "date", "protocol", "status", "detail", "due_at", "area", "month", "count"];
  const populated = (key: string) => rows.filter((row) => row[key] !== null && row[key] !== undefined && row[key] !== "").length;
  const rest = keys
    .filter((key) => key !== "evidence_ids" && !priority.includes(key))
    .sort((a, b) => populated(b) - populated(a) || a.localeCompare(b));
  return [
    ...priority.filter((key) => keys.includes(key)),
    ...rest,
    ...(keys.includes("evidence_ids") ? ["evidence_ids"] : []),
  ];
}

function TableView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  const rows = isRowArray(visual.data) ? visual.data : [];
  const columns = orderedColumns(rows);
  return (
    <div>
      <VisualHeading visual={visual} />
      {rows.length === 0 ? (
        <p className="empty-state">The backend returned no rows for this table.</p>
      ) : (
        <div className="table-visual__scroll">
          <table className="table-visual">
            <thead>
              <tr>
                {columns.map((key) => (
                  <th key={key} scope="col">
                    {key}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((key) => (
                    <td key={key}>
                      <Cell value={row[key]} envelope={envelope} onOpenEvidence={onOpenEvidence} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="visual__note">
        {rows.length} row{rows.length === 1 ? "" : "s"} exactly as returned by the analytics operation.
      </p>
    </div>
  );
}

function Cell({
  value,
  envelope,
  onOpenEvidence,
}: {
  value: unknown;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  if (Array.isArray(value) && value.every((entry) => typeof entry === "string")) {
    // Evidence ids and plain string lists both arrive as string arrays. Chips are only
    // useful when the ids resolve inside this envelope.
    const known = value.filter((id) => (envelope.evidence ?? []).some((ref) => ref.id === id));
    if (known.length === value.length && known.length > 0) {
      return <EvidenceChips ids={known} envelope={envelope} onOpen={onOpenEvidence} />;
    }
    return <span className="cell-list">{value.map(formatScalar).join(", ")}</span>;
  }
  if (isRecord(value)) {
    return <span className="cell-json">{JSON.stringify(value)}</span>;
  }
  if (value === null || value === undefined || value === "") {
    return <span className="cell-empty" title="not recorded">—</span>;
  }
  if (typeof value === "number") {
    return <span className="cell-number">{formatScalar(value)}</span>;
  }
  return <span>{formatScalar(value)}</span>;
}

// ---------------------------------------------------------------- chart helpers

const NUMBER = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const LABEL = (value: unknown): string =>
  value === null || value === undefined || value === "" ? "not recorded" : formatScalar(value);

function numericKeys(rows: Record<string, unknown>[]): string[] {
  const keys: string[] = [];
  for (const row of rows) {
    for (const [key, value] of Object.entries(row)) {
      if (key === "evidence_ids") continue;
      if (NUMBER(value) !== null && !keys.includes(key)) keys.push(key);
    }
  }
  return keys;
}

function labelKey(rows: Record<string, unknown>[], preferred: string[], exclude: string[]): string | null {
  for (const key of preferred) {
    if (rows.some((row) => row[key] !== undefined && row[key] !== null)) return key;
  }
  for (const key of columnKeys(rows)) {
    if (exclude.includes(key)) continue;
    if (!rows.some((row) => typeof row[key] === "string")) continue;
    return key;
  }
  return null;
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    // One distinct value still needs a readable axis: bracket it.
    return [min - 1, min, min + 1];
  }
  const span = max - min;
  const step = Math.pow(10, Math.floor(Math.log10(span / count)));
  const scaled = span / count / step;
  const factor = scaled >= 7.5 ? 10 : scaled >= 3.5 ? 5 : scaled >= 1.5 ? 2 : 1;
  const size = factor * step;
  const start = Math.floor(min / size) * size;
  const ticks: number[] = [];
  for (let value = start; value <= max + size * 0.001; value += size) ticks.push(Number(value.toFixed(6)));
  return ticks;
}

const W = 720;
const H = 260;
const PAD = { top: 16, right: 16, bottom: 34, left: 46 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

function AxisFrame({ ticks, format }: { ticks: number[]; format?: (value: number) => string }) {
  const min = Math.min(...ticks);
  const max = Math.max(...ticks);
  const y = (value: number) => PAD.top + PLOT_H - ((value - min) / (max - min || 1)) * PLOT_H;
  return (
    <>
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} className="chart__grid" />
          <text x={PAD.left - 8} y={y(tick) + 4} className="chart__tick chart__tick--y" textAnchor="end">
            {format ? format(tick) : String(tick)}
          </text>
        </g>
      ))}
    </>
  );
}

// ---------------------------------------------------------------- line

function LineView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  const rows = (isRowArray(visual.data) ? visual.data : []).filter((row) => row);
  if (rows.length === 0) return <MissingField visual={visual} field="series" />;

  const xKey = visual.x ?? labelKey(rows, ["date", "month", "day"], ["evidence_ids"]);
  const allNumeric = numericKeys(rows);
  const preferred = [visual.y, "wellhead_temp_c", "ambient_temp_c"].filter(
    (key): key is string => Boolean(key) && allNumeric.includes(key as string),
  );
  const series = Array.from(new Set(preferred.length > 0 ? preferred : allNumeric.slice(0, 2)));
  if (!xKey || series.length === 0) return <MissingField visual={visual} field={xKey ? "y" : "x"} />;

  const values = rows.flatMap((row) => series.map((key) => NUMBER(row[key])).filter((v): v is number => v !== null));
  if (values.length === 0) return <MissingField visual={visual} field="numeric y" />;
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const low = Math.min(...ticks);
  const high = Math.max(...ticks);
  const px = (index: number) =>
    PAD.left + (rows.length === 1 ? PLOT_W / 2 : (index / (rows.length - 1)) * PLOT_W);
  const py = (value: number) => PAD.top + PLOT_H - ((value - low) / (high - low || 1)) * PLOT_H;

  // A row the backend marked as not producing is marked on the chart; nothing is inferred.
  const marked = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => row.producing === false || row.not_producing === true);

  const labelStep = Math.max(1, Math.ceil(rows.length / 8));

  return (
    <div>
      <VisualHeading visual={visual} />
      <div className="chart">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${visual.title}, ${rows.length} readings`}>
          <AxisFrame ticks={ticks} />
          {series.map((key, seriesIndex) => {
            const points = rows
              .map((row, index) => {
                const value = NUMBER(row[key]);
                return value === null ? null : `${px(index)},${py(value)}`;
              })
              .filter((point): point is string => point !== null);
            return (
              <polyline
                key={key}
                points={points.join(" ")}
                className={`chart__line chart__line--${seriesIndex % 4}`}
                fill="none"
              />
            );
          })}
          {marked.map(({ row, index }) => {
            const value = NUMBER(row[series[0]]);
            if (value === null) return null;
            return (
              <g key={`mark-${index}`}>
                <line x1={px(index)} x2={px(index)} y1={PAD.top} y2={PAD.top + PLOT_H} className="chart__mark" />
                <circle cx={px(index)} cy={py(value)} r={4} className="chart__dot--mark" />
              </g>
            );
          })}
          {rows.map((row, index) =>
            index % labelStep === 0 || index === rows.length - 1 ? (
              <text key={`x-${index}`} x={px(index)} y={H - 12} className="chart__tick" textAnchor="middle">
                {LABEL(row[xKey])}
              </text>
            ) : null,
          )}
        </svg>
        <Legend items={series} />
      </div>
      {marked.length > 0 ? (
        <p className="visual__note">
          Marked {marked.length} reading{marked.length === 1 ? "" : "s"} where the backend reported the well was not
          producing oil: {marked.map(({ row }) => LABEL(row[xKey])).join(", ")}.
        </p>
      ) : null}
      <RowEvidence rows={rows} envelope={envelope} onOpenEvidence={onOpenEvidence} />
    </div>
  );
}

function Legend({ items }: { items: string[] }) {
  return (
    <ul className="chart__legend">
      {items.map((item, index) => (
        <li key={item}>
          <span className={`chart__swatch chart__swatch--${index % 4}`} aria-hidden="true" />
          {item}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- bar

function BarView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  const rows = isRowArray(visual.data) ? visual.data : [];
  if (rows.length === 0) return <MissingField visual={visual} field="bar" />;
  const numeric = numericKeys(rows);
  const valueKey = visual.y && numeric.includes(visual.y) ? visual.y : numeric[0];
  const nameKey = labelKey(rows, [visual.x ?? "well_id", "well", "name", "area"], ["evidence_ids", valueKey ?? ""]);
  if (!valueKey || !nameKey) return <MissingField visual={visual} field={valueKey ? "a label" : "a value"} />;

  // A series column turns the bar into a stacked bar: one bar per label, one segment per
  // series value, lengths still exactly the numbers the backend sent.
  const seriesKey =
    visual.series && rows.some((row) => typeof row[visual.series as string] === "string") ? visual.series : null;

  if (seriesKey) {
    const names = Array.from(new Set(rows.map((row) => LABEL(row[nameKey]))));
    const seriesValues = Array.from(new Set(rows.map((row) => LABEL(row[seriesKey])))).sort();
    const byKey = new Map<string, number>();
    for (const row of rows) byKey.set(`${LABEL(row[nameKey])}|${LABEL(row[seriesKey])}`, NUMBER(row[valueKey]) ?? 0);
    const totals = names.map((name) => seriesValues.reduce((sum, s) => sum + (byKey.get(`${name}|${s}`) ?? 0), 0));
    const ticks = niceTicks(0, Math.max(...totals, 1));
    const high = Math.max(...ticks);
    const barH = Math.max(12, Math.min(30, PLOT_H / Math.max(names.length, 1) - 10));
    const gap = names.length > 1 ? (PLOT_H - barH * names.length) / (names.length - 1) : 0;
    const chartH = Math.max(H, names.length * (barH + gap) + PAD.top + PAD.bottom);
    return (
      <div>
        <VisualHeading visual={visual} />
        <div className="chart">
          <svg viewBox={`0 0 ${W} ${chartH}`} role="img" aria-label={`${visual.title}, stacked by ${seriesKey}`}>
            {ticks.map((tick) => {
              const x = PAD.left + (tick / (high || 1)) * PLOT_W;
              return (
                <g key={tick}>
                  <line x1={x} x2={x} y1={PAD.top} y2={PAD.top + names.length * (barH + (gap || 0))} className="chart__grid" />
                  <text x={x} y={PAD.top + names.length * (barH + (gap || 0)) + 16} className="chart__tick" textAnchor="middle">
                    {tick}
                  </text>
                </g>
              );
            })}
            {names.map((name, index) => {
              const y = PAD.top + index * (barH + gap);
              let offset = 0;
              return (
                <g key={name}>
                  {seriesValues.map((series, seriesIndex) => {
                    const value = byKey.get(`${name}|${series}`) ?? 0;
                    if (value <= 0) return null;
                    const width = (value / (high || 1)) * PLOT_W;
                    const x = PAD.left + offset;
                    offset += width;
                    return (
                      <rect
                        key={series}
                        x={x}
                        y={y}
                        width={Math.max(width, 1)}
                        height={barH}
                        className={`chart__stack chart__stack--${seriesIndex % 5}`}
                      >
                        <title>{`${name} · ${series} · ${value}`}</title>
                      </rect>
                    );
                  })}
                  <text x={PAD.left - 8} y={y + barH / 2 + 4} className="chart__tick chart__tick--y" textAnchor="end">
                    {name}
                  </text>
                  <text x={PAD.left + offset + 6} y={y + barH / 2 + 4} className="chart__value">
                    {formatScalar(totals[index])}
                  </text>
                </g>
              );
            })}
          </svg>
          <ul className="chart__legend">
            {seriesValues.map((series, index) => (
              <li key={series}>
                <span className={`chart__swatch chart__swatch--${index % 5}`} aria-hidden="true" />
                {series}
              </li>
            ))}
          </ul>
          <p className="visual__note">
            Stacked by <code>{seriesKey}</code>; segment and total lengths are the returned <code>{valueKey}</code> values.
          </p>
        </div>
        <RowEvidence rows={rows} envelope={envelope} onOpenEvidence={onOpenEvidence} />
      </div>
    );
  }

  const values = rows.map((row) => NUMBER(row[valueKey]) ?? 0);
  const max = Math.max(...values);
  const ticks = niceTicks(0, max === 0 ? 1 : max);
  const high = Math.max(...ticks);
  const barH = Math.max(10, Math.min(26, PLOT_H / Math.max(rows.length, 1) - 8));
  const gap = rows.length > 1 ? (PLOT_H - barH * rows.length) / (rows.length - 1) : 0;

  return (
    <div>
      <VisualHeading visual={visual} />
      <div className="chart">
        <svg
          viewBox={`0 0 ${W} ${Math.max(H, rows.length * (barH + 10) + PAD.top + PAD.bottom)}`}
          role="img"
          aria-label={`${visual.title}, ${rows.length} bars`}
        >
          {ticks.map((tick) => {
            const x = PAD.left + (tick / (high || 1)) * PLOT_W;
            return (
              <g key={tick}>
                <line x1={x} x2={x} y1={PAD.top} y2={PAD.top + rows.length * (barH + (gap || 0))} className="chart__grid" />
                <text x={x} y={PAD.top + rows.length * (barH + (gap || 0)) + 16} className="chart__tick" textAnchor="middle">
                  {tick}
                </text>
              </g>
            );
          })}
          {rows.map((row, index) => {
            const value = NUMBER(row[valueKey]) ?? 0;
            const y = PAD.top + index * (barH + gap);
            const width = (value / (high || 1)) * PLOT_W;
            return (
              <g key={index}>
                <rect x={PAD.left} y={y} width={Math.max(width, 1)} height={barH} className="chart__bar" />
                <text x={PAD.left - 8} y={y + barH / 2 + 4} className="chart__tick chart__tick--y" textAnchor="end">
                  {LABEL(row[nameKey])}
                </text>
                <text x={PAD.left + width + 6} y={y + barH / 2 + 4} className="chart__value">
                  {formatScalar(value)}
                </text>
              </g>
            );
          })}
        </svg>
        <p className="visual__note">
          Bar length is <code>{valueKey}</code> exactly as returned. Ranked by the backend, not re-sorted here.
        </p>
      </div>
      <RowEvidence rows={rows} envelope={envelope} onOpenEvidence={onOpenEvidence} />
    </div>
  );
}

// ---------------------------------------------------------------- map

function MapView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  const rows = (isRowArray(visual.data) ? visual.data : []).filter(
    (row) => NUMBER(row.lat) !== null && NUMBER(row.lon) !== null,
  );
  if (rows.length === 0) return <MissingField visual={visual} field="lat/lon" />;

  const lats = rows.map((row) => NUMBER(row.lat) as number);
  const lons = rows.map((row) => NUMBER(row.lon) as number);
  // A tiny minimum span keeps a single pin from sitting on an edge.
  const latPad = Math.max(0.004, (Math.max(...lats) - Math.min(...lats)) * 0.12);
  const lonPad = Math.max(0.004, (Math.max(...lons) - Math.min(...lons)) * 0.12);
  const latMin = Math.min(...lats) - latPad;
  const latMax = Math.max(...lats) + latPad;
  const lonMin = Math.min(...lons) - lonPad;
  const lonMax = Math.max(...lons) + lonPad;
  const MAP_W = 720;
  const MAP_H = 360;
  const mx = (lon: number) => ((lon - lonMin) / (lonMax - lonMin || 1)) * (MAP_W - 80) + 40;
  const my = (lat: number) => (1 - (lat - latMin) / (latMax - latMin || 1)) * (MAP_H - 70) + 30;

  return (
    <div>
      <VisualHeading visual={visual} />
      <div className="map-visual">
        <svg viewBox={`0 0 ${MAP_W} ${MAP_H}`} role="img" aria-label={`${visual.title}, ${rows.length} wells`}>
          <rect x={12} y={12} width={MAP_W - 24} height={MAP_H - 24} className="map__frame" />
          {[0.25, 0.5, 0.75].map((fraction) => (
            <g key={fraction}>
              <line
                x1={40}
                x2={MAP_W - 40}
                y1={30 + fraction * (MAP_H - 70)}
                y2={30 + fraction * (MAP_H - 70)}
                className="map__grid"
              />
              <line
                x1={40 + fraction * (MAP_W - 80)}
                x2={40 + fraction * (MAP_W - 80)}
                y1={30}
                y2={MAP_H - 40}
                className="map__grid"
              />
            </g>
          ))}
          {rows.map((row, index) => {
            const lat = NUMBER(row.lat) as number;
            const lon = NUMBER(row.lon) as number;
            const volume = NUMBER(row.volume_bbl);
            const where = `${LABEL(row.well_id ?? row.name)} at ${lat}, ${lon}`;
            return (
              <g key={index} className="map__pin">
                <title>
                  {where}
                  {volume !== null ? ` · ${volume} bbl` : ""}
                  {row.date ? ` · ${LABEL(row.date)}` : ""}
                </title>
                <circle cx={mx(lon)} cy={my(lat)} r={7} className="map__pin-dot" />
                <text x={mx(lon) + 11} y={my(lat) + 4} className="map__label">
                  {LABEL(row.well_id ?? row.name)}
                  {volume !== null ? ` · ${volume} bbl` : ""}
                </text>
              </g>
            );
          })}
          <text x={16} y={MAP_H - 12} className="map__scale">
            schematic field grid · lat {latMin.toFixed(3)}–{latMax.toFixed(3)} · lon {lonMin.toFixed(3)}–
            {lonMax.toFixed(3)}
          </text>
        </svg>
        <p className="visual__note">
          Positions are the wells&apos; recorded coordinates. The grid is a reference frame, not a basemap; no road,
          boundary or distance is implied.
        </p>
      </div>
      <RowEvidence rows={rows} envelope={envelope} onOpenEvidence={onOpenEvidence} />
    </div>
  );
}

// ---------------------------------------------------------------- heatmap

function HeatmapView({
  visual,
  envelope,
  onOpenEvidence,
}: {
  visual: VisualSpec;
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  const rows = isRowArray(visual.data) ? visual.data : [];
  const areaKey = rows.length > 0 && "area" in rows[0] ? "area" : null;
  const monthKey = rows.length > 0 && "month" in rows[0] ? "month" : null;
  const valueKey = rows.length > 0 ? ["count", "value", "spills"].find((key) => NUMBER(rows[0][key]) !== null) : undefined;
  if (!areaKey || !monthKey || !valueKey) return <MissingField visual={visual} field="area/month/count" />;

  const areas = Array.from(new Set(rows.map((row) => LABEL(row[areaKey]))));
  const months = Array.from(new Set(rows.map((row) => LABEL(row[monthKey])))).sort();
  const lookup = new Map<string, number>();
  for (const row of rows) lookup.set(`${LABEL(row[areaKey])}|${LABEL(row[monthKey])}`, NUMBER(row[valueKey]) ?? 0);
  const values = Array.from(lookup.values());
  const max = Math.max(...values, 1);
  const totals = areas.map((area) => months.reduce((sum, month) => sum + (lookup.get(`${area}|${month}`) ?? 0), 0));

  return (
    <div>
      <VisualHeading visual={visual} />
      <div className="table-visual__scroll">
        <table className="heatmap">
          <thead>
            <tr>
              <th scope="col">area</th>
              {months.map((month) => (
                <th key={month} scope="col">
                  {month}
                </th>
              ))}
              <th scope="col" className="heatmap__total">
                total
              </th>
            </tr>
          </thead>
          <tbody>
            {areas.map((area, rowIndex) => (
              <tr key={area}>
                <th scope="row">{area}</th>
                {months.map((month) => {
                  const count = lookup.get(`${area}|${month}`) ?? 0;
                  const intensity = max === 0 ? 0 : count / max;
                  return (
                    <td
                      key={month}
                      className="heatmap__cell"
                      style={{ background: count === 0 ? undefined : `rgba(168, 87, 59, ${0.08 + intensity * 0.62})` }}
                      title={`${area} · ${month} · ${count}`}
                    >
                      {count}
                    </td>
                  );
                })}
                <td className="heatmap__total">{totals[rowIndex]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="visual__note">
        Counts are the backend&apos;s aggregate per area and month after corrections. Shading scales with the largest cell
        ({max}).
      </p>
      <RowEvidence rows={rows} envelope={envelope} onOpenEvidence={onOpenEvidence} />
    </div>
  );
}

// ---------------------------------------------------------------- shared

/** The distinct evidence behind a chart, so a chart is as auditable as a table row. */
function RowEvidence({
  rows,
  envelope,
  onOpenEvidence,
}: {
  rows: Record<string, unknown>[];
  envelope: AnswerEnvelope;
  onOpenEvidence: ((evidenceId: string) => void) | null;
}) {
  const known = new Set((envelope.evidence ?? []).map((ref) => ref.id));
  const ids: string[] = [];
  for (const row of rows) {
    const raw = row.evidence_ids;
    if (!Array.isArray(raw)) continue;
    for (const entry of raw) {
      if (typeof entry === "string" && known.has(entry) && !ids.includes(entry)) ids.push(entry);
    }
  }
  if (ids.length === 0) return null;
  return (
    <div className="chart__evidence">
      <span className="text-visual__key">evidence</span>
      <EvidenceChips ids={ids} envelope={envelope} onOpen={onOpenEvidence} />
    </div>
  );
}

function UnsupportedView({ visual }: { visual: VisualSpec }) {
  return (
    <div className="visual-unsupported">
      <p className="visual-unsupported__head">
        <ChartLine size={16} weight="regular" aria-hidden="true" />
        {visual.title}
      </p>
      <p>
        The backend returned {visual.data.length} row{visual.data.length === 1 ? "" : "s"} for a visual this workspace
        does not know how to draw, so nothing is shown rather than drawn approximately.
      </p>
    </div>
  );
}
