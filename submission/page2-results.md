# Page 2 — Results

**Recorded answers.** Sample evaluation set (18 questions, 200 wells), run through the copilot on
17 Oct 2026 with analysis date 2026-10-17. The deterministic planner run passes every check in
`eval-runs/scenarios/scenario-report.md` (18/18); the live `gemma4:31b` run was spot-checked on
Q1, Q6, Q7, Q9, Q11, Q13 and Q15. Where the two paths differed, the difference is stated in
"What didn't". The released final set is run with `tools/evalrun/final.py`; this table is
replaced by those answers, not merged with them.

| # | Copilot answer (as recorded) | Visual |
|---|---|---|
| Q1 | Not producing. INS-0001-0203, 15 Oct 2026, drone, Ryan Brooks. Wellhead 3.2 °C above air, below T200's 15 °C. Reason CTX-0001-003 (Jake Morales): shut in from 7 Oct for rod-string replacement, back ~20 Oct, not yet in maintenance. Recorded status `active` is stale. | card |
| Q2 | Four T200 wells, all last inspected 15 Oct: WELL-0164 (4.1 °C, no recorded reason; remark "Pump jack not moving"), WELL-0170 (2.9 °C, open pump-jack bearing repair), WELL-0172 (5.7 °C, open flowline pinhole), WELL-0175 (0.4 °C, no recorded reason). | table |
| Q3 | 13 readings, 23 Jul–15 Oct 2026; not producing on 8 and 15 Oct (marked on the chart). | line |
| Q4 | 6 spills, 15.1 bbl: 16 Mar 2023 (0.5), 27 Apr (2.6), 28 Sep (3.3), 19 Oct (0.3), 11 Jun 2026 (6.8), 1 Oct (1.6). INS-0001-0070 excluded as rainwater per CTX-0001-001. | table |
| Q5 | 21 days: 24 Jul (51.6 °C vs 43.1 air = 8.5, prime mover trip), 16 and 23 Oct (stuffing-box leak). | text |
| Q6 | WELL-0121 49 d, WELL-0138 42 d, WELL-0107 42 d (next WELL-0119 28 d), window 16 Jun–16 Oct. | bar |
| Q7 | 4 pins: WELL-0151 24 Sep 4.5 bbl (32.12246, −102.18445), WELL-0165 30 Jul 1.2 (32.15665, −102.14522), WELL-0175 30 Jul 3.9 (32.18020, −102.14790), WELL-0186 23 Jul 0.6 (32.17552, −102.17775). | map |
| Q8 | 2026 spills by area×month: SW-23 35, SW-24 43, NE-7 37, NE-8 26; corrected detections removed. | heatmap |
| Q9 | Four breaches from the 11 Jun 6.8 bbl spill, USD 5,000 open: SR-01 reported after 41 h vs 24 (REG-0001-001; NOV REG-0001-002), SR-02 contained ~7 h vs 4 (only in the June report), SR-03 verification due 10 Aug still open (REG-0001-003), RC-04 response due 30 Jul absent. Pending: flowline RCA after 3 repairs and the unrecorded 7 Oct shut-in. RC-02 met 7 Mar 2026. | table |
| Q10 | Two late contains in SW-24: WELL-0082 ~7.1 h (MNT-0082-028), WELL-0100 ~8.1 h (MNT-0100-034), against the 4 h SOP limit. | table |
| Q11 | Recalled the three wells from Michael Turner's earlier answer: WELL-0121 USD 25,794, WELL-0138 USD 46,942, WELL-0107 USD 5,176 (2026 repairs). | table |
| Q12 | Records the correction against INS-0164-0205 (24.0 → 41.0 °C), keeps the original, attributes it, previews the flip to producing (21.1 °C above air), flags the disagreeing "Pump jack not moving" remark and asks to confirm. Re-asked Q2 answers three wells and says why WELL-0164 is absent. | card |
| Q13 | Records 4.5 → 5.4 bbl against INS-0151-0201, keeps the AI estimate. At 5.4 bbl it is reportable: SR-01 notice due 25 Sep with none recorded (possible breach), SR-03 verification due 23 Nov, the report's "moderate / no reporting duty" classification no longer holds, and its 6.4 h containment is an SR-02 breach. | table |
| Q14 | Manual threshold: WELL-0108, WELL-0121, WELL-0138 (3 pump-jack repairs each). After the T350 rule of 2: adds WELL-0120, not T200 WELL-0102; answer attributes the threshold to Michael Turner's team rule, not the manual. | table |
| Q15 | Jessica Reed: WELL-0164 is producing on the corrected 41.0 °C, corrected by Michael Turner, with the inspector's disagreeing note. Laura Simmons: WELL-0151 (5.4 bbl) needed a report; none recorded, flagged overdue. | card/table |
| Q16 | WELL-0007 planned shut-in from 17 Oct for ~10 days, attributed to Jake Morales. Jessica's "three wells we discussed" gets "no earlier conversation of yours" — Michael's history is not used. | card/text |
| Q17 | Tyler's "running fine" is kept unconfirmed; the 15 Oct inspection (Jessica Reed) shows 0.4 °C above air, so not producing — matching Michael's note; both statements retained, confirmation requested. Jake's "WELL-0001 back online" is likewise unconfirmed against the 15 Oct reading and CTX-0001-003's ~20 Oct return. | card/table |
| Q18 | Yes. Detection INS-0101-0197 (1.0 bbl) stands; Ryan Brooks' produced-water note and Chris Dalton's crude confirmation are both shown, neither is a formal correction, and the spill repair MNT-0101-029 exists. | table |

## What worked

The facts with a paper trail: every row's evidence resolves to an exact source line, and the
rules (T200/T350 production delta, 5 bbl reportable, 24 h notice, 4 h containment, 60-day
verification, RCA count) come from the manual/SOP rows, not code constants. Corrections apply at
their scope and reach every user while keeping the original with author and reason; outdated
results are marked. Private recall resolved for the owner and refused for everyone else.

## What didn't

- The live model path was weaker than the planner on window arithmetic: "last 13 weeks" became a
  calendar window (12 readings, not 13), and "real spill" initially added a `reportable_only`
  filter (1 pin, not 4). Both were fixed at the tool/prompt boundary and re-verified, but they
  show the remaining risk is *routing*, not fabrication.
- One live turn sent a well id where an inspection id belonged and `"5.4 bbl"` where a number
  belonged: it returned HTTP 500 and stored a string. Now normalised/rejected with a regression
  test. This was a real failure before the fix.
- Some prose is thinner than the table: "1 spills result(s)." led an answer whose overdue notice
  and deadline were only in the columns.
- One question fell back to the planner after a model rate limit (visible warning, correct answer).

## Why

Truth lives in SQL and the documents, so what remains is routing, not invention. That is the
trade: a terse sentence is better than a wrong number, and every fix above is a small, testable
change at the tool boundary rather than an unverifiable prompt tweak.
