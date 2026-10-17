# Evaluation run harness

Loads a dataset, runs the question document through the copilot, records every answer, and
audits the answers. It is the submission path for the sample set and for a released test
set in the same format.

Everything runs **in process** through the real FastAPI app, so a run never depends on a
server that someone forgot to start. `--base-url` switches to a running server when you
want to exercise the network path.

## Two models, two jobs

| Model | Config | Job |
|---|---|---|
| Copilot | `OLLAMA_MODEL` (gemma4:31b) | talks to the engineer, chooses tools, produces the validated `AnswerEnvelope` |
| UI | `OPENUI_MODEL` (thesysdev/OUI-1) | composes the layout of that envelope. Never supplies a value |

Without model credentials the deterministic offline planner answers. That is the only
fully reproducible mode, and every run records which mode produced it in `manifest.json`.

## Run

```powershell
# 1. Load a dataset (sample, or a released test set in the same format)
.venv\Scripts\python.exe tools\evalrun\run.py load `
  --source assets/flytbase-dataset/sample-data `
  --database eval-runs\eval.sqlite3

# 2. Run the questions and record the answers
.venv\Scripts\python.exe tools\evalrun\run.py ask `
  --questions assets\flytbase-dataset\03-evaluation-queries.md `
  --database eval-runs\eval.sqlite3 `
  --out eval-runs\run-1

# 3. Audit the recorded answers
.venv\Scripts\python.exe tools\evalrun\run.py score --out eval-runs\run-1
```

`ask` defaults to the offline planner. Add `--live-model` to use the configured copilot
model, or `--base-url http://localhost:8000` to question a running server.

## What a run writes

| File | Contents |
|---|---|
| `manifest.json` | dataset, question file digest, mode, user, git HEAD, timestamp |
| `answers.jsonl` | one record per question: the question, the expected block, the full response |
| `answers.md` | the same, side by side with the expected text, for human grading |
| `score.json` / `score.md` | the mechanical audit |

## Question formats

The parser reads the dataset's own document (`**Q1. question**` then an `Expected` block),
plus a JSON list and a one-question-per-line text file. A released question set can be
dropped in without changes.

## What the audit proves, and what it does not

`score` checks that every numeral in the prose is traceable to `calculations` or
`visual.data`, and reports coverage, evidence counts, warnings and empty answers. That
proves **traceability**, not truth. Truth comes from comparing against the question
document's expected values, which this command deliberately does not encode: hard-coding
the sample answers would make the harness grade its own homework.

For truth, use `assets/flytbase-dataset/03-evaluation-queries.md` as the oracle, or
`.cursor/agents/copilot-qa` for the full weighted audit (independent recomputation from the
raw files, plus the adversarial probes).

## Reproducibility

`ask` reuses the loaded database instead of re-ingesting, so running the same questions
repeatedly answers the same stored records. That is what makes a three-run comparison
meaningful.
