# Demo video — 5:00 (2:00 system, 3:00 one scenario end to end)

Record at 1080p, browser at 100% zoom, one window, no terminal unless you need it. Speak in your
own voice; the text below is a spine, not a script to read. Numbers in **bold** are the ones to say
exactly.

Before recording: `docker compose up -d` (or the local uvicorn), `ANALYSIS_DATE=2027-01-15`, test
dataset loaded, `/health` ok, `/capabilities` shows the model configured. Clear the thread sidebar
or pick your demo user fresh so old threads don't distract.

---

## 0:00–0:20 — What this is

[Show the workspace, user picker visible.]

> "This is the Asset Intelligence Copilot. An operator asks a question in plain English about
> wells — status, spills, repairs, compliance — and gets an answer with the records and the rule
> text it used, drawn as the right visual. My governing decision: **the model chooses what to ask,
> never what is true.**"

## 0:20–1:05 — How it is built

[Show the architecture diagram from the README, or a slide of it.]

> "Data lands as immutable source versions — file hash and path — and one record version per JSONL
> line with its line number. An active pointer decides what is current, so re-importing the test
> dataset created new versions for the shared wells and never rewrote history. Above that sit typed
> projections for analytics, a rules table extracted from the manuals and SOPs with the exact line
> they came from, and a graph projection in Neo4j for lineage and recall."

> "Three tools. `asset_query` is typed — the model cannot write SQL, it picks an operation and a
> window, and the code decides thresholds and totals. `recall_results` is scoped to the asking user.
> `propose_feedback` can only prepare a change; a human confirms it."

## 1:05–1:35 — Why the split

> "Every number is SQL over the *effective* value of a record — after corrections. The production
> threshold comes from the well-type manual: T200, T350 and T500 each have their own. Downtime is
> seven days per non-producing weekly inspection, not repair hours. A spill total or a heatmap cell
> is an aggregate, never a vector search. If the data cannot answer something, it says which field
> is missing instead of substituting a different quantity."

## 1:35–2:00 — Evidence and memory

> "Every row carries evidence ids that resolve to an exact source line — a JSONL line, a report
> line, an SOP section. Two memory levels: shared knowledge — corrections, claims, team rules with
> an explicit scope — and private conversation history, re-validated against the asking user on
> every read. A reference this user never made returns 'no earlier conversation of yours', never
> someone else's."

---

## 2:00–5:00 — One scenario, end to end

[Pick the user in the header. Ask exactly as written. Talk over the 3–6 s latency.]

### 2:00 — The question

As **Laura Simmons (HSE)**:

> "Since 1 Nov 2026, every time an operator note reports gas at a well, did we get someone out to
> that well in time under our operating procedures? List every report and whether the response met
> the deadline."

### 2:20 — What came back

[Point at the table.]

> "One row per gas report: the well, the area, when the note was written, the response — a
> maintenance job or a **manual** inspection, because the SOP says a drone inspection does not
> count — the hours to response, the deadline, and Met or Missed."

> "The deadline is not a constant. The operations SOP revision 2 cuts it from **24 hours to 12**
> for reports from 1 January 2027, so the rows before that date are judged against 24 and the ones
> after against 12. The rule is a row in the database with a source line, not a number in my code."

### 2:50 — Evidence

[Open the evidence drawer on one missed row.]

> "Here is the operator's note, the job that responded, and the SOP section that sets the deadline
> — three different sources, one answer."

### 3:10 — The judgement

> "This is the part a chat model usually gets wrong: it is a join between unstructured text, a
> structured job table and a document rule, with a date-dependent threshold. The answer states the
> count and names the misses rather than saying 'all handled'."

### 3:40 — Same session, follow-up

> "An operator reported a gas smell at WELL-0332 on 3 Dec. What was the H2S reading?"

> "The reading exists only inside the repair report's safety section. It is extracted at ingest with
> its line provenance, so the copilot can answer it and cite it — it isn't summarised from a pile of
> PDFs at question time."

### 4:10 — Private vs shared

[Switch user in the header to **Nathan Pierce**.]

> "A different user gets a clean workspace. Ask him 'the wells we discussed yesterday' and he gets a
> refusal, not Laura's history. Now a shared statement — Nathan says a recalled pump was swapped —
> is prepared as a draft, and after he confirms it, Robert sees it. Shared facts travel, private
> conversation does not."

### 4:40 — Honest limits

> "Two of the eleven questions ask for quantities the dataset does not contain: reservoir pressure
> and produced barrels. The copilot says so and names the missing field instead of inventing a
> proxy. Where a question needs a judgement — which well to fix first — it gives a transparent
> ranked heuristic and labels it as one."

### 4:55 — Close

> "Built with FastAPI, PostgreSQL with pgvector, Neo4j for projection and lineage, and gemma4:31b
> for tool choice. The deterministic planner is the reproducible path; the model is the general one.
> Everything on screen traces back to a line of source."

---

## If the gas question misbehaves on the day

Swap the 2:00–3:40 block for **Q11** (one turn: "Which region of the field consistently runs
hotter?") and then **Q6** (status disagreements). Q11 is the safest visual demo; Q6 shows the
conflict handling. Keep the evidence-drawer beat and the user-switch beat — those are the parts
that prove the design.
