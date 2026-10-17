# Page 1 — System design

**Asset Intelligence Copilot.** The governing idea: a language model may decide *what to ask*,
never *what is true*. Every number, well id, date and citation is produced by deterministic
code over versioned records; the model's only jobs are tool selection and prose framing.

## Architecture and storage

FastAPI + PostgreSQL (authoritative) + Next.js workspace, with Neo4j/Mem0 as optional
projections. Data is ingested as **immutable source versions** (`SourceVersion`: file bytes,
sha256, path) and **record versions** (`RecordVersion`: one parsed object per line, with
source id and line number). An `ActiveRecord` pointer chooses the current version, so a
re-import never rewrites history and an A→B→A content change still produces a new version.
Typed **query projections** (`WellFact`, `InspectionFact`, `MaintenanceFact`, `RegulatorFact`)
serve analytics; **`Rule`** rows hold every threshold with its manual/SOP source span. Imports
validate duplicate ids, dangling/cross-well references, enum and range types, path escapes and
symlink escape, then commit inside a savepoint: a failed import retains only its diagnostic batch.

**Indexing.** SQL indexes on well/area/date/type; section-aware `DocumentChunk` rows with exact
line spans plus 384-d MiniLM vectors in pgvector; a unique effective-value table for corrections.
Vector search is only ever a *discovery* aid for prose — no numeric total is computed from top-k.

## Tools

1. `asset_query` — one typed `QuerySpec` (operation, wells/area, window, equipment, limit,
   visual) over eleven operations: status, temperatures, spills, downtime, maintenance, rca,
   containment, compliance, notes, documents, guidance. Returns rows + calculations + evidence.
2. `recall_results` — resolves “the wells we discussed” against **this user's** saved results only.
3. `propose_feedback` — prepares a correction, rule, note or claim. It never publishes.

The model loop is capped (6 rounds, 8 calls). A bad tool argument returns a tool error the
model can correct, not a failed turn. Without credentials the deterministic planner runs and a
visible warning says so.

## Numbers, documents and notes

Numbers come from SQL: production state is `wellhead − ambient ≥ threshold` where the threshold
is read from the well-type manual row; downtime is `7 days × non-producing weekly inspections`
(never repair hours); spill totals, costs and heatmap cells are SQL aggregates over *effective*
(corrected) facts. Documents are parsed at ingest: manuals and SOPs yield rules; repair reports
yield facts that exist only in prose (containment time, the SR/RC compliance table), each tied
to a source line. Notes are stored as records: formal `correction` notes are promoted to
corrections at import; operator notes are used only as *attributed explanations* (with author)
and never as facts.

One answer envelope merges multiple tool results: evidence de-duplicates by exact source span,
conflicts accumulate, and every row keeps the ids back to the raw line.

## Two memory levels

- **Shared**: corrections and claims are rows with an explicit scope — inspection, well, or
  well type. Effective values are recomputed on every query, so a correction reaches every
  user immediately; a well-type rule change applies only to that type (T350 in, T200 out).
- **Private**: saved results and messages are user-scoped. Recall re-validates ownership
  against PostgreSQL on every read; the graph query itself requires an `OWNS` path from the
  asking user. An unresolvable reference produces an explicit “no earlier conversation of
  yours” — never a fleet-wide fallback.

## Conflicts and new data

Prepare/confirm is mandatory for writes: clarification of well/inspection/field/value/unit,
plausibility, before/after preview, conflict detection (prior corrections, competing drafts),
then confirmation with a stale-record recheck. Originals are never deleted. Incompatible formal
corrections become `disputed` with the last accepted value retained and shown; informal notes
that disagree are surfaced while the detection stands; a user claim contradicting an inspection
is kept as *unconfirmed* and the answer says so; `recorded_status` is labelled stale when the
inspection disagrees; a team rule is labelled “team override”, never “official manual”.
New data of the same format loads additively (versions + pointers + re-extracted rules), the
analysis date is configuration, and affected saved results are marked outdated rather than
silently changed.

## Models and cost

`gemma4:31b` (Ollama Cloud) for the tool loop — measured 4–6 s per turn, one to six calls,
roughly 3–6 k input and <500 output tokens: fractions of a cent per turn. Local MiniLM
embeddings cost nothing. OUI-1 (or OpenUI Gateway) is optional and may only compose layout.
No silent paid-provider fallback.

## Next

Run every final question through the model path, not just the planner, and diff tool traces;
replace heuristic routing with a schema-constrained decoder plus retry; automate the multi-turn
scenarios in the harness; table-aware/LLM-assisted document extraction that still carries line
provenance and human review; per-team tenancy; streamed envelopes and cached rule lookups.
