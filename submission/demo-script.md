# Demo video script — 5:00 hard cap

Record 1440p or 1080p, browser at 100% zoom, one window. Cut dead air: the answer latency is
4–6 s, so keep talking over it or trim. Speak in your own voice; the beats below are a spine,
not a script to read.

## 0:00–0:35 — The problem and the thesis

> "An operator asks which wells were down longest this summer, and why. The answer lives in
> inspections, repairs, SOPs and people's notes. The obvious build is 'put it all in a prompt'.
> I did the opposite: **the model chooses what to ask, never what is true**. Every number comes
> from typed SQL over versioned records; the model's job is tool choice and framing."

Show the workspace with the user picker visible.

## 0:35–1:30 — How it is built

> "Data lands as immutable source versions — file hash, path — and one record version per JSONL
> line with its line number. An active pointer decides what is current, so a re-import never
> rewrites history. Above that sit typed projections for analytics, and a rules table extracted
> from the manuals: the T200 production delta, the 5-barrel reportable limit, the 24-hour
> notice. Those are data with a cited line, not constants in code."

Gesture at the architecture in the README (or a slide): three tools — asset_query,
recall_results, propose_feedback.

> "Three tools. Query is typed and returns rows plus the evidence ids. Recall is scoped to the
> asking user. Feedback can only *prepare* a change; a human confirms it."

## 1:30–3:15 — Real use case A: compliance, end to end

Ask as **Michael Turner**:

> "Which rules has WELL-0001 broken in the last 12 months, and what is still open?"

Walk the render while it lands:

- table of breaches; point at SR-01's 41 hours against the 24-hour limit, SR-02's 7-hour
  containment against 4, SR-03 and RC-04 deadlines.
- open the evidence drawer on one row; show the exact SOP line and the regulator record.

> "Two of these are only provable from prose: the containment time exists only inside the
> repair report, and the RC-04 response is absent — so the answer says absent, it does not
> invent a response. The SOP text is a citation, not something the model paraphrased."

## 3:15–4:10 — Real use case B: a correction that must not silently win

Ask as **Michael Turner**:

> "The AI estimated the 24 Sep spill at WELL-0151 as 4.5 barrels. The field crew measured 5.4."

- the reply is a **draft**, with before → after and the reason.
- confirm it.
- ask as **Laura Simmons**: "Which spills in Northeast Block 8 in the last 90 days needed a
  report to the regulator?"

> "Notice what changed: 5.4 crosses the 5-barrel reportable threshold, so the answer now names
> WELL-0151 and flags that no written notice is on record. The original 4.5 estimate is still
> there, with who changed it and why. Laura never saw Michael's chat — she saw the shared record."

## 4:10–4:50 — The private memory line

Ask as **Jessica Reed**:

> "For the three wells we discussed yesterday, what have repairs cost this year?"

> "Jessica has no such conversation, so the answer refuses instead of borrowing Michael's
> history. That refusal is a design decision: an unresolved reference must never widen into a
> fleet-wide query."

Then as **Michael Turner**, ask the same and show it resolve to the three wells he actually
discussed, with per-well repair cost and citations.

## 4:50–5:00 — Limits and next

> "What I would fix next: exercise every final question through the model path, not just the
> deterministic planner, and replace heuristic routing with a schema-constrained decoder.
> The graph and Mem0 projections are optional — Postgres is the source of truth — and the nao
> analytics sidecar is not on the default path. Everything I showed is traceable to a line of
> source."

## Pre-flight

1. `docker compose up -d` and wait for backend `/health`.
2. Load the dataset; confirm `/capabilities` shows the model configured.
3. Two browsers tabs: app, and `answers.md` for the question list (do not show expected answers
   on camera).
4. Clear the thread sidebar so no stale rows distract.
5. Rehearse the correction once on a scratch well if the demo data is shared.
