# Document Intelligence ingestion (`tools/docintel`)

Turns the FlytBase sample corpus (**`.md`** documents and **`.json`** registries) into a
knowledge graph in Neo4j, in the shape Neo4j's Document Intelligence / Graph Builder
produces, so it can be explored in **Bloom**.

```
(:Document)-[:HAS_CHUNK]->(:Chunk)-[:NEXT_CHUNK]->(:Chunk)
(:Chunk)-[:MENTIONS]->(:Well | :Person | :Equipment | :Protocol | :Regulation | ...)
(:Entity)-[:REQUIRES | :APPLIES_TO | :PERFORMED_BY | :LOCATED_IN | ...]->(:Entity)
```

plus the domain links that join documents to the physical fleet:

```
(:Well)-[:HAS_DOCUMENT]->(:Document)      (:Well)-[:OF_TYPE]->(:WellType)
(:Well)-[:LOCATED_IN]->(:Area)            (:Area)<-[:MANAGES]-(:Team)
(:Well)-[:HAS_EQUIPMENT]->(:Equipment)    (:Well)-[:ASSIGNED_TO]->(:Person)
(:Person)-[:MEMBER_OF]->(:Team)           (:Person)-[:HAS_ROLE]->(:Role)
```

## What is ingested

| Input | Handling |
|---|---|
| `fleet/sops/*.md`, `fleet/well-types/*.md` | LLM entity/relation extraction |
| `assets/<WELL>/maintenance-reports/*.md` | LLM entity/relation extraction |
| `fleet/areas.json`, `fleet/users.json` | deterministic structural load (+ a `Document`/`Chunk`) |
| `assets/<WELL>/metadata.json` | deterministic structural load (+ a `Document`/`Chunk`) |

Markdown is chunked (~2500 chars, 250 overlap), each chunk is sent to the Ollama Cloud
chat model, and the model may only emit the controlled vocabulary defined at the top of
`ingest.py`. Unknown labels/types are normalised or dropped, which keeps the Bloom
perspective clean.

## Running it

Use the project virtualenv (it already has `httpx`, `neo4j`, and `sentence-transformers`):

```powershell
# smoke test: two SOPs + the structural JSON
.venv\Scripts\python.exe tools\docintel\ingest.py --limit 3

# full fleet + ~20 wells (the default well list)
.venv\Scripts\python.exe tools\docintel\ingest.py

# a custom set of wells
.venv\Scripts\python.exe tools\docintel\ingest.py --wells WELL-0001,WELL-0002,WELL-0051

# re-extract everything and also store MiniLM chunk embeddings
.venv\Scripts\python.exe tools\docintel\ingest.py --force --embed
```

| Flag | Meaning |
|---|---|
| `--limit N` | only process the first `N` markdown documents |
| `--wells a,b,c` | restrict the per-well documents |
| `--workers N` | concurrent extraction calls (default 4) |
| `--chunk-size` / `--overlap` | chunking controls |
| `--force` | re-ingest even when the file hash is unchanged |
| `--embed` | compute 384-dim MiniLM embeddings per chunk |
| `--skip-md` / `--skip-structural` | run only one half |

**Idempotent and interrupt-safe:** every `Document` is keyed by its repository-relative path
and skipped when its `sha256` is unchanged. The hash is written **last**, so a document
interrupted mid-write is re-ingested next run rather than being skipped forever. Writes retry
transient Aura routing/connection blips with backoff instead of aborting the run.

## Viewing it in Bloom

1. Open the [Aura console](https://console.neo4j.io) and select the instance
   (`70671a34`).
2. Open **Bloom** (or **Explore**) from the instance tools.
3. Choose **Create perspective** — Bloom scans the graph and proposes categories from the
   node labels: pick `Well`, `Document`, `Chunk`, `Person`, `Equipment`, `Protocol`,
   `Regulation`, `Area`, `Team`, `WellType`.
4. Suggested starting views:
   - **Well → HAS_DOCUMENT → Document → HAS_CHUNK → Chunk** to walk a well's paperwork.
   - **Chunk → MENTIONS → Protocol / Regulation** to see which procedures and rules the
     reports cite.
   - **Well → HAS_EQUIPMENT → Equipment** for the physical breakdown of an asset.
   - Filter `Document.kind = 'maintenance_report'` to show only field reports.

Starter queries (Neo4j Browser / Bloom search phrases) are in
[`queries.cypher`](./queries.cypher).

## Notes

- The extraction model (`gemma4:31b` on Ollama Cloud) does not strictly honour JSON-schema
  mode, so responses are parsed tolerantly (code fences, arrays, `nodes`/`edges` aliases).
- Ollama Cloud on this plan does **not** serve embedding models, so chunk embeddings are
  opt-in via `--embed` and computed locally with MiniLM.
- A separate isolated venv (`C:\Temp2\ingest-venv`) holds `neo4j-graphrag` if we later want
  the official `SimpleKGPipeline`; the shipped pipeline avoids it because that library
  requires an embedder and strict structured output, neither of which this stack provides.
