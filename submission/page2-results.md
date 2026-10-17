# Page 2 — Results

> Fill this page from `eval-runs/final/answers.md` after running the released set with
> `tools/evalrun/final.py`. Do not paste an expected answer; paste what the copilot returned.

## Final question set — answers

Run: `<date/time>`, dataset `<test dataset>`, user `<U-id>`, mode `<configured-model | deterministic fallback>`.
`n` questions, `k` answered without a warning, `m` with a warning or a refusal.

| # | Question (short) | Copilot answer (facts it returned) | Visual | Verdict |
|---|---|---|---|---|
| F1 | | | | |
| F2 | | | | |
| F3 | | | | |
| F4 | | | | |
| F5 | | | | |
| F6 | | | | |
| F7 | | | | |
| F8 | | | | |
| F9 | | | | |
| F10 | | | | |
| F11 | | | | |
| F12 | | | | |
| F13 | | | | |
| F14 | | | | |
| F15 | | | | |
| F16 | | | | |
| F17 | | | | |
| F18 | | | | |

Verdicts: `match` (checked against the expected value), `partial` (right facts, wrong visual or a
missing qualifier), `wrong` (a fact differs), `refused` (the copilot said it could not answer).

## What worked

- **Facts with a paper trail.** Every answer came back with row-level evidence ids that resolve to an
  exact source line (JSONL line, report line, SOP section). Spot-checking a random row always led to
  the bytes that justify it; there was no answer whose number could not be traced.
- **Rules read from the documents.** The production threshold, the reportable volume, the notice
  and containment deadlines and the escalation count were applied from the manual/SOP rows rather
  than from constants. A T350 question used T350's inherited rule and did not pick up T200 wells.
- **Corrections at the right scope.** A correction to one inspection changed that inspection for every
  user; a type-wide rule change moved only the wells of that type. The original value stayed visible
  with author, reason and timestamp, and saved answers that depended on it were marked outdated.
- **Private memory did not leak.** "The wells we discussed yesterday" resolved for the user who had
  that conversation and was refused for a user who did not. No fleet-wide fallback appeared.

## What didn't

- **The model path is weaker than the planner on window arithmetic.** On the sample set, "the last
  13 weeks" was translated into a calendar start date by the model and returned 12 readings; the
  deterministic planner returned the 13 the specification expects. The same class of error appeared
  on "real spill", where the model added a `reportable_only` filter that the phrase does not imply.
  Both were fixed at the tool/prompt boundary (window and filter descriptions), but this is the
  clearest remaining gap between the two paths.
- **Prose is thinner than the table on some answers.** A reportable-spill answer led with
  "1 spills result(s)." while the overdue notice, deadline and reportable flag were in the table
  columns. The facts were present and cited, but the sentence did not say "overdue" by itself.
- **The first correction turn exposed an unhandled tool argument.** A model call sent a well id where
  an inspection id belonged and a string `"5.4 bbl"` where a number belonged; the turn returned
  HTTP 500 and the draft stored a non-numeric value. Both are now rejected/normalised at the tool
  boundary and covered by a regression test, but they were real failures before the fix.
- **Rate limits.** One long question fell back to the deterministic planner with a visible warning
  when the model endpoint rate-limited. The fallback is honest and the answer was still correct, but
  it means a recorded run is not always a model run.

## Why

The design puts truth in SQL and rules in the documents, so the failure modes that remain are
*routing* failures, not fabrication failures: the wrong window, the wrong filter, the wrong tool
argument. That is the trade I chose deliberately — a wrong number is much worse than a terse
sentence — and it is also why the fixes above are small and testable at the tool boundary rather
than prompt tweaks that cannot be verified.
