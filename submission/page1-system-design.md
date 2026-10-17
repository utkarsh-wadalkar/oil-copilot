# Page 1 — System design

**Thesis:** the model decides *what to ask*, never *what is true*. Every number, id, date and
citation comes from deterministic code over versioned records; the model only picks tools and
frames prose.

**Stack.** FastAPI + PostgreSQL (authoritative) + Next.js workspace; Neo4j and Mem0 are optional
projections, never the source of truth.

## Storage, indexing, retrieval

Ingest writes **immutable source versions** (file bytes, sha256, path) and one **record version**
per JSONL line with its source id and line number. An `ActiveRecord` pointer chooses the current
version, so re-import never rewrites history and an A→B→A content change still creates a new
version. Typed projections (`WellFact`, `InspectionFact`, `MaintenanceFact`, `RegulatorFact`) serve
analytics; `Rule` rows hold every threshold with its manual/SOP span; `DocumentChunk` holds
section-aware chunks with exact line spans plus 384-d MiniLM vectors. Import validates duplicate
ids, dangling and cross-well references, units, ranges, path/symlink escapes, then commits in a
savepoint — a failed import keeps only its diagnostic batch.

Retrieval is typed, not top-k: `AssetKnowledge.query(QuerySpec)` runs SQL over *effective*
(corrected) facts for eleven operations (status, temperatures, spills, downtime, maintenance, RCA,
containment, compliance, notes, documents, guidance). Vector similarity is a discovery aid for
prose only; no total is ever computed from neighbours.

## Tools

1. `asset_query` — typed spec in, rows + calculations + evidence out.
2. `recall_results` — resolves “the wells we discussed” against this user's saved results only.
3. `propose_feedback` — prepares a correction, rule, note or claim; never publishes.

Loop capped at 6 rounds / 8 calls. A malformed tool argument returns a tool error the model can
correct, not a failed turn. Without credentials the deterministic planner answers with a visible
warning.

## Numbers, documents, notes

Production state is `wellhead − ambient ≥ threshold`, threshold read from the well-type manual row
(T350 inherits T200 where its manual says so). Downtime is 7 days × non-producing weekly
inspections — never repair hours. Spill totals, costs and heatmap cells are SQL aggregates over
effective facts. Repair reports are mined at ingest for prose-only facts (containment time, the
SR/RC compliance table) with line provenance. Notes stay attributed: formal `correction` notes
become corrections, operator notes are used only as *attributed explanations*, never as facts.

## Two memory levels

- **Shared:** corrections and claims carry an explicit scope — inspection, well, or well type —
  and effective values are recomputed on every query, so a correction reaches every user at once
  while a type-wide rule moves only that type.
- **Private:** results and messages are user-scoped; every recall re-validates ownership in
  PostgreSQL and the graph query requires an `OWNS` path. An unresolvable reference returns “no
  earlier conversation of yours”, never a fleet-wide widening.

## Conflicts and new data

All writes are prepare → preview → confirm: clarify well/inspection/field/value/unit, check
plausibility, show before/after, detect prior corrections and competing drafts, then re-check the
record is unchanged at confirmation. Originals are never deleted. Incompatible formal corrections
become `disputed` with the last accepted value retained and shown; disagreeing informal notes are
surfaced while the detection stands; a claim contradicting an inspection is kept *unconfirmed*;
`recorded_status` is labelled stale; a team rule is labelled “team override”, never “official
manual”. New data of the same format loads additively (versions, pointers, re-extracted rules),
the analysis date is configuration, and affected saved results are marked outdated rather than
silently rewritten.

## Models and cost

`gemma4:31b` (Ollama Cloud) drives the tool loop: 4–6 s per turn, 1–6 calls, ≈3–6 k input and
<500 output tokens — a fraction of a cent per turn. Local MiniLM embeddings are free. OUI-1 (or
OpenUI Gateway) is optional and may only compose layout. No silent paid-provider fallback: a
model failure is recorded or answered by the planner with a warning.

## Next

Run the whole final set through the model path and diff tool traces; replace heuristic routing
with a schema-constrained decoder plus retry; automate multi-turn scenarios in the harness;
LLM-assisted document extraction that still carries line provenance and human review; per-team
tenancy; streamed answers and cached rule lookups.
