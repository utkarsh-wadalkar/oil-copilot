# Asset Intelligence Copilot

A chat copilot for an oil field: ask a plain-English question about wells, spills, repairs or
compliance and get a grounded answer with the records and rule text it used, rendered inline
as the right visual (card, table, line chart, bar chart, map or heatmap).

Built for the **FlytBase Asset Intelligence Copilot** challenge (Hacktoberfest 2026).
The system is deliberately split into two halves: a **deterministic, auditable analytics core**
that owns every number, and a **model layer** that only chooses which tool to call and how to
present the result. The model can never invent a figure, a well, a citation or a threshold.

---

## What it does

- **Numbers from SQL, not from a language model.** Production state, downtime, spill totals,
  repair cost, compliance deadlines and RCA windows are computed by typed operations over
  PostgreSQL. The active value of a corrected field is resolved before every query.
- **Rules from the documents.** Well-type manuals and SOPs are parsed into `Rule` rows with a
  source file and line span. Thresholds such as the T200 production delta, the 5 bbl
  reportable limit, the 24 h notice and the 4 h containment limit are read from those rows,
  never hard-coded. `T350` inherits the `T200` escalation rule when its manual says so.
- **Evidence on every answer.** Each row carries evidence ids that resolve to an exact line
  span of the immutable source version (JSONL line, report line, SOP section).
- **Two memory levels.** Shared, well-scoped knowledge (claims, corrections, type-wide rule
  changes) is durable and visible to every user. Private conversation history is resolved
  only from the asking user's own saved results.
- **Corrections with a paper trail.** A correction is a draft: before/after preview, a
  plausibility check, the reason and author, then explicit confirmation. The original value
  is retained forever; every later answer uses the accepted value; conflicting corrections
  stay visible as a dispute instead of silently picking a winner.
- **Generative UI.** The validated answer envelope is composed client-side. When an OpenUI
  model is configured it may only choose layout; the values always come from the envelope.
  Without it the deterministic renderer draws the same answer.

## Architecture

[![Architecture diagram of utkarsh-wadalkar/oil-copilot](https://gitdiagram.com/utkarsh-wadalkar/oil-copilot/diagram.png)](https://gitdiagram.com/utkarsh-wadalkar/oil-copilot?utm_source=readme&utm_medium=picture)

The generated map of this repository (modules and their imports) is above; the runtime shape is below.

```
                    ┌────────────────────────── Next.js workspace ──────────────────────────┐
 user picker ─────► │ chat · answer parts · visual · evidence drawer · correction preview   │
                    └───────────────────────────────┬──────────────────────────────────────┘
                                                    │ REST + X-User-ID
                    ┌───────────────────────────────▼──────────────────────────────────────┐
                    │ FastAPI                                                              │
                    │  /conversations  /results  /feedback  /history  /imports  /mcp       │
                    │                                                                      │
                    │  Orchestrator ──► tool loop (gemma4:31b)                             │
                    │       │             ├─ asset_query      (typed, deterministic)       │
                    │       │             ├─ recall_results   (this user only)             │
                    │       │             └─ propose_feedback (draft, never publishes)     │
                    │       ▼                                                              │
                    │  AssetKnowledge ──► SQL over effective facts + Rule rows             │
                    └───────┬───────────────────────────────┬──────────────────────────────┘
                            │                               │
              ┌─────────────▼─────────────┐   ┌─────────────▼─────────────┐
              │ PostgreSQL + pgvector     │   │ Neo4j (optional projection)│
              │ authoritative facts,      │   │ evidence graph, recall,    │
              │ sources, rules, corrections│  │ exploration                │
              │ conversations, results    │   └───────────────────────────┘
              └───────────────────────────┘
```

**Storage and indexing**

| Store | Holds | Why |
|---|---|---|
| `SourceVersion` | immutable file content, sha256, path | provenance; every citation points into one of these |
| `RecordVersion` + `ActiveRecord` | every parsed record version, one pointer per record | re-import creates a new version, never mutates history |
| `InspectionFact`, `MaintenanceFact`, `RegulatorFact`, `WellFact` | typed query projections | fast SQL; corrections applied on read |
| `Rule` | threshold + well type + source/line span | the rules are data, not constants |
| `Correction`, `FeedbackDraft` | accepted/provisional/disputed changes and drafts | shared truth with an audit trail |
| `SavedResult`, `Message`, `Conversation` | answers and chat, user-scoped | private memory |
| `DocumentChunk` + pgvector | section-aware chunks with line spans | document search with exact excerpts |
| Neo4j | `Well`, `Rule`, `Result`, `Evidence`, `SourceVersion` edges | optional recall/exploration; never the source of truth |

**Retrieval.** Structured questions go through `AssetKnowledge.query(QuerySpec)`; there is no
vector top-k anywhere in a numeric path. Documents are found by section-aware search, and
free-text repair reports are mined on import for facts that exist only in prose (containment
time, the compliance table). Vector similarity is only a discovery aid for prose, never for a
total.

## Repository layout

```
backend/            FastAPI, ingestion, analytics, orchestration, memory/graph projections
frontend/           Next.js 16 + React 19 workspace, OpenUI Lang renderer
assets/             dataset checkout (git-ignored; see Setup)
infra/nao/          optional self-hosted nao analytics sidecar (profile-gated)
tools/evalrun/      load → ask → score harness for a question document
tools/docintel/     document → Neo4j knowledge-graph ingest helper
docker-compose.yml  postgres, neo4j, backend, worker, optional nao, frontend
```

## Setup

Prerequisites: Docker Desktop, Python 3.12+, Node 20+.

```powershell
git clone https://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset assets/flytbase-dataset
Copy-Item .env.example .env
# edit .env: OLLAMA_API_KEY, POSTGRES_PASSWORD

docker compose up -d --build
```

The dataset folder is mounted read-only at `/dataset`. Load it once:

```powershell
curl -X POST http://localhost:8000/imports -H "X-User-ID: U-201" -H "Content-Type: application/json" -d "{\"root\": null}"
curl http://localhost:8000/imports/status -H "X-User-ID: U-201"
```

Open <http://localhost:3000>, pick a user, ask a question.

Without `OLLAMA_API_KEY` the copilot still answers, using the deterministic offline planner.
That mode is fully reproducible and is what the recorded runs use unless `--live-model` is set.

### Running without Docker

```powershell
python -m venv .venv; .venv\Scripts\python -m pip install -e backend
$env:DATABASE_URL="postgresql+psycopg://copilot:<password>@localhost:5432/copilot"
$env:DATASET_ROOT="assets/flytbase-dataset/sample-data"
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000
cd frontend; npm install; npm run dev
```


## Loading the released test dataset

The test dataset (600 wells, today = 2027-01-15) loads through the same versioned path as the
sample. Importing it alongside the sample keeps every source, creates new versions for the 200
shared wells and adds the 400 new ones:

`powershell
python tools/evalrun/load_test.py --source assets/flytbase-dataset/test-data/dataset
`

Set ANALYSIS_DATE=2027-01-15 in .env first. The loader also projects the new batch into Neo4j
(Well, Rule, SourceVersion and their edges) and prints the projected count, so the graph
reflects the new data, not only PostgreSQL.

`powershell
# run the released questions through the copilot (threaded, with draft confirmation)
python tools/evalrun/final.py --base-url http://127.0.0.1:8000 \
  --turns eval-runs/final-turns.json --out eval-runs/final
`

### Generate OpenUI layouts with Ollama Cloud

Set `OPENUI_ENABLED=1` and `OPENUI_PROVIDER=ollama` in the root `.env`, then restart
the backend. This reuses `OLLAMA_BASE_URL=https://ollama.com`, `OLLAMA_MODEL=gemma4:31b`
and your existing server-side `OLLAMA_API_KEY`; no Thesys credits or second key are
required. Gemma receives OpenUI syntax and the generated component signatures to
compose layouts. OpenUI still renders validated answer values in the browser;
Gateway's automatic repair is bypassed. Set `OPENUI_PROVIDER=gateway` to return to
the existing `OPENUI_*` endpoint, model and credentials.

## Evaluation harness

```powershell
.venv\Scripts\python.exe tools\evalrun\run.py load --source assets\flytbase-dataset\sample-data --database eval-runs\eval.sqlite3
.venv\Scripts\python.exe tools\evalrun\run.py ask --questions assets\flytbase-dataset\03-evaluation-queries.md --database eval-runs\eval.sqlite3 --out eval-runs\run-1
.venv\Scripts\python.exe tools\evalrun\run.py score --out eval-runs\run-1
```

`ask` runs each question in process through the real app and writes `manifest.json`,
`answers.jsonl` and `answers.md`. Add `--live-model` to exercise the configured copilot model.
The score command proves traceability (every numeral maps to a calculation or visual row), not
truth; truth is checked against the question document.

## Models and cost

| Role | Default | Notes |
|---|---|---|
| Copilot | `gemma4:31b` through Ollama Cloud | tool selection + answer composition; ~4–6 s per turn in testing |
| Embeddings | `all-MiniLM-L6-v2` (local CPU, 384-d) | document chunks and Mem0 vectors |
| UI composition | `thesysdev/OUI-1` or OpenUI Gateway | optional; disabled by default, deterministic renderer is the fallback |

A conversation turn makes one to six chat requests (the tool loop) and no paid embeddings
call. In the recorded runs a turn cost roughly 3–6 k input tokens plus the tool results and
under 500 output tokens; at Ollama Cloud list pricing that is fractions of a cent per turn.
There is no silent fallback to a different paid provider: if the model fails, the turn is
recorded as failed or answered by the offline planner with a visible warning.

## Honest limitations

- The nao analytics sidecar (`infra/nao/`) is built but profile-gated and not part of the
  default stack; the copilot's own tool loop is the production path.
- Neo4j and Mem0 are **optional projections**. The API process resolves private recall from
  PostgreSQL so the feature works without them; the graph is for exploration and lineage.
- The deterministic planner covers the documented question families; a novel phrasing can
  route badly. The model path is the general path, the planner is the reproducible one.
- OpenUI composition is only exercised when an OUI-1-compatible endpoint is configured.

## License

MIT — see [LICENSE](LICENSE).
