# Asset Knowledge data dictionary (effective, corrected)

This dictionary is generated to match the **exact effective views and tool schemas** exposed
by the Copilot's Asset Knowledge MCP server. It deliberately excludes raw, uncorrected sensor
facts: every value below is the *effective* value after formal corrections are applied at
their explicit scope.

## Canonical units

| Family        | Canonical unit | Notes                                             |
| ------------- | -------------- | ------------------------------------------------- |
| Temperature   | `C` (Celsius)  | `wellhead_temp_c`, `ambient_temp_c`               |
| Spill volume  | `bbl`          | barrels                                           |
| Spill area    | `%`            | percent of the inspection footprint               |
| Duration      | hours          | `containment_hours`, `hours_to_report`            |
| Money         | `USD`          | `cost_usd`, `fine_usd`                            |
| Time          | UTC            | inspection/date bounds are ISO-8601 (UTC)         |

## Operations of `asset_query`

`operation` chooses the projection; all accept `well_ids` or `area`, and most accept
`start`/`end`, `limit`, `visual`.

| operation       | Returns                                                        |
| --------------- | -------------------------------------------------------------- |
| `status`        | Current well status + recorded status                          |
| `temperatures`  | Wellhead/ambient temperature readings over the window          |
| `spills`        | Spill detections with estimated volume/area                    |
| `downtime`      | Maintenance-derived downtime hours and cost over the window     |
| `maintenance`   | Maintenance events by equipment kind                           |
| `compliance`    | Regulatory events, protocols, reporting latency, fines         |
| `containment`   | Containment hours                                              |
| `rca`           | Root-cause threshold rule + contributing maintenance           |
| `notes`         | Context notes/claims attached to wells                         |
| `documents`     | Document search (needs `query`)                                |
| `guidance`      | SOP/manual-directed next steps with cited sections             |

## Effective-fact fields (never raw)

- `spill_detected` (bool), `spill_est_volume_bbl` (float|bbl), `spill_area_pct` (float|%)
- `wellhead_temp_c` / `ambient_temp_c` (float|C)
- `cost_usd` (float), `containment_hours` (float), `fine_usd` (float), `hours_to_report` (float)
- `rca_threshold` (int, per well type) — resolves against the well's type and the equipment kind

A correction is scoped and attributed: `before` -> `after`, `author`, `reason`, validity
interval. A corrected value is the effective truth; the raw original is retained for audit but
is **never** the current value. `well_history` returns the accepted corrections/notes for a well.

## Tool result envelope (compact)

```
{
  "summary": str,
  "selected_well_ids": [str],
  "rows": [ { ... } ],            # capped preview
  "calculations": [ { ... } ],    # every figure, with its inputs
  "conflicts": [ { ... } ],
  "warnings": [str],
  "evidence_count": int,
  "visual": "text|card|table|line|bar|map|heatmap"
}
```

`store_envelope` persists this envelope under the signed actor + request and returns a
`result_id` the Copilot renders. The model's own prose is never treated as the answer.
