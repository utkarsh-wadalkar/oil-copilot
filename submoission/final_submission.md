# Asset Intelligence Copilot

**FlytBase Hackathon | Utkarsh Wadalkar | 17 October 2026**  
**Repository:** https://github.com/utkarsh-wadalkar/oil-copilot

## Page 1 - System design

[![Architecture diagram of utkarsh-wadalkar/oil-copilot](https://gitdiagram.com/utkarsh-wadalkar/oil-copilot/diagram.png)](https://gitdiagram.com/utkarsh-wadalkar/oil-copilot?utm_source=readme&utm_medium=picture)

**Design principle.** The model chooses tools and frames the answer; deterministic code computes numbers, resolves corrections and supplies evidence. Next.js hosts chat, inline visuals, evidence and correction previews; FastAPI orchestrates queries; PostgreSQL is authoritative. Neo4j and Mem0 are optional projections.

### Storage and retrieval

Immutable source versions retain bytes, SHA-256, path and line provenance. Each JSONL record has a version; an active pointer selects the current record without rewriting history. Typed well, inspection, maintenance and regulator projections support SQL analytics. Manual/SOP thresholds live in sourced rule rows. Section-aware document chunks retain exact line spans and 384-dimensional MiniLM vectors. Imports validate IDs, references, units, ranges and path escapes; failed imports retain diagnostics.

`AssetKnowledge.query(QuerySpec)` queries effective, corrected facts for status, temperatures, spills, downtime, maintenance, RCA, containment, compliance, notes, documents and guidance. Vector search discovers prose; it never computes totals. Repair-report extraction supplies containment times and compliance findings with source lines.

### Tools and grounded answers

`asset_query` returns rows, calculations and evidence; `recall_results` resolves the current user's saved answers; `propose_feedback` prepares a draft without publishing. The loop allows six rounds/eight calls and returns malformed arguments as tool errors. Missing credentials or model failure can invoke the deterministic planner with a visible warning.

Production uses wellhead minus ambient temperature against the manual threshold. Downtime is seven days per non-producing weekly inspection, never repair hours. SQL computes spill totals, repair costs and heatmap cells. Notes remain attributed; informal explanations never silently override measured facts. Answer envelopes feed cards, tables, line/bar charts, maps and heatmaps; an optional OpenUI model composes layout.

### Memory, conflicts and new data

Shared corrections, claims and rules have inspection, well or well-type scope and are applied on every query. Private messages/results are user-scoped; recall rechecks ownership in PostgreSQL and requires an OWNS path in the graph. Missing personal history never widens to another user's results.

Writes follow prepare, preview and confirm: clarify target/value/unit, check plausibility, show before/after, detect conflicts and recheck the record at confirmation. Originals remain. Incompatible formal corrections become disputed while retaining the last accepted value; informal disagreements and unconfirmed claims stay visible. Stale recorded status and team overrides are labeled. Additive imports preserve versions, refresh rules and mark affected saved answers outdated; the analysis date is configurable.

### Models, cost and next steps

The design draft reports `gemma4:31b` via Ollama Cloud at 4-6 seconds/turn, 1-6 calls, about 3-6k input tokens and under 500 output tokens. These are observed estimates, not a billing benchmark. Local MiniLM embeddings have no provider token charge; optional UI generation adds provider-dependent cost. No silent paid-provider fallback is configured.

Next: run the released final set through the model path and compare tool traces; constrain tool decoding; automate multi-turn evaluation; add reviewed, evidence-preserving document extraction, team tenancy, streaming and rule caching.

<!-- PDF page break -->

## Page 2 - Results

**Evaluation scope.** These are the recorded **sample-set** answers for 200 wells, analysis date 2026-10-17; they are not claimed as released final-set results. The archived offline deterministic replay passes all 18 scenarios. The results draft reports live `gemma4:31b` spot checks on Q1, Q6, Q7, Q9, Q11, Q13 and Q15. Run `tools/evalrun/final.py` on the released dataset/questions and replace this table before submitting final-set results.

| Q | Recorded copilot answer | Visual |
|---|---|---|
| 1 | WELL-0001 not producing: INS-0001-0203, 15 Oct, drone/Ryan Brooks; delta 3.2 C < T200's 15 C. Jake Morales' CTX-0001-003 attributes shut-in from 7 Oct to rod-string replacement, return about 20 Oct; recorded active status is stale. | Card |
| 2 | Four T200 wells, inspected 15 Oct: WELL-0164 (4.1 C; pump jack not moving), WELL-0170 (2.9 C; bearing repair), WELL-0172 (5.7 C; flowline pinhole), WELL-0175 (0.4 C; no reason recorded). | Table |
| 3 | 13 readings, 23 Jul-15 Oct 2026; non-producing on 8 and 15 Oct, marked on the chart. | Line |
| 4 | Six spills, 15.1 bbl: 16 Mar 2023 (0.5), 27 Apr (2.6), 28 Sep (3.3), 19 Oct (0.3); 11 Jun 2026 (6.8), 1 Oct (1.6). INS-0001-0070 excluded as rainwater under CTX-0001-001. | Table |
| 5 | 21 days: 24 Jul (51.6 C wellhead, 43.1 C air, delta 8.5 C; prime mover trip), 16 and 23 Oct (stuffing-box leak). | Text |
| 6 | 16 Jun-16 Oct: WELL-0121 49 days, WELL-0138 42, WELL-0107 42; next WELL-0119 28. | Bar |
| 7 | Four pins: WELL-0151, 24 Sep, 4.5 bbl (32.12246, -102.18445); WELL-0165, 30 Jul, 1.2 (32.15665, -102.14522); WELL-0175, 30 Jul, 3.9 (32.18020, -102.14790); WELL-0186, 23 Jul, 0.6 (32.17552, -102.17775). | Map |
| 8 | 2026 spill counts by area/month: SW-23 35, SW-24 43, NE-7 37, NE-8 26; corrected detections removed. | Heatmap |
| 9 | Four breaches from 11 Jun's 6.8 bbl spill; USD 5,000 open: SR-01 notice at 41 h > 24 (REG-0001-001/002); SR-02 containment about 7 h > 4 (June report); SR-03 verification due 10 Aug open (REG-0001-003); RC-04 response due 30 Jul absent. Pending flowline RCA after three repairs and unrecorded 7 Oct shut-in. RC-02 met 7 Mar. | Table |
| 10 | SW-24 late containment: WELL-0082 about 7.1 h (MNT-0082-028), WELL-0100 about 8.1 h (MNT-0100-034), versus four-hour SOP. | Table |
| 11 | Michael Turner's recalled wells, 2026 repair cost: WELL-0121 USD 25,794; WELL-0138 USD 46,942; WELL-0107 USD 5,176. | Table |
| 12 | Preview INS-0164-0205 correction 24.0 to 41.0 C, retain original/author, flag conflicting pump-jack remark and request confirmation. Delta 21.1 C means producing; after confirmation, Q2 has three wells and explains the exclusion. | Card |
| 13 | Correct INS-0151-0201 from 4.5 to 5.4 bbl, retain AI estimate. Now reportable: SR-01 notice due 25 Sep absent (possible breach); SR-03 verification due 23 Nov; prior no-reporting classification invalid; 6.4 h containment breaches SR-02. | Table |
| 14 | Manual RCA threshold finds WELL-0108, WELL-0121 and WELL-0138 (three pump-jack repairs each). T350 team rule of two adds WELL-0120, not T200 WELL-0102; attributed to Michael, not the manual. | Table |
| 15 | Jessica sees WELL-0164 producing at Michael's corrected 41.0 C with inspector disagreement. Laura sees WELL-0151's 5.4 bbl spill needed a report; none recorded, overdue. | Card/table |
| 16 | WELL-0007 planned shut-in from 17 Oct for about ten days, attributed to Jake. Jessica's recall of three wells returns no earlier conversation of hers; Michael's history stays private. | Card/text |
| 17 | Tyler's running-fine claim stays unconfirmed: Jessica's 15 Oct inspection shows delta 0.4 C, not producing, matching Michael's note. Jake's WELL-0001 back-online claim also conflicts with inspection/CTX-0001-003; retain statements and request confirmation. | Card/table |
| 18 | Spill INS-0101-0197 (1.0 bbl) stands. Ryan's produced-water note and Chris' crude confirmation both appear; neither is a formal correction. Repair MNT-0101-029 supports the record. | Table |

### What worked, what did not, and why

**Worked:** line-level evidence, document-sourced thresholds, shared scoped corrections with originals retained, outdated-result flags and owner-only recall. Evidence: `../submission/evidence/sample-scenarios-report.md`; recorded answers: `../submission/evidence/sample-scenarios-answers.md`.

**Limitations:** the live path initially interpreted 13 weeks as 12 readings and added an unwanted reportable-only spill filter; the draft reports boundary fixes and rechecks. Malformed feedback once caused HTTP 500/string storage; the draft reports normalization/rejection and a regression test. Some prose omitted details present in table columns. One rate-limited turn visibly fell back to the planner. These observations identify tool routing and presentation as remaining risks; offline success does not establish full live-model or final-set accuracy.
