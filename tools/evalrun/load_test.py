"""Load a released dataset into the configured database and project it into Neo4j/Mem0.

This is the "new data" path: it runs the same `ingest_dataset` the REST endpoint runs, then
drains the outbox so the graph projection reflects the new batch. It is idempotent by
(path, sha256), so re-running it does not duplicate sources; changed files become new versions
and the active pointers move.

    python tools/evalrun/load_test.py --source assets/flytbase-dataset/test-data/dataset
    python tools/evalrun/load_test.py --source ... --no-graph      # database only

Prints the batch status, per-kind counts, extraction warnings, and the graph/mem0 result.
Exits non-zero when the batch failed or the graph is configured but the projection failed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.graph import GraphMemory  # noqa: E402
from app.ingestion import ingest_dataset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True)
    parser.add_argument("--no-graph", action="store_true")
    parser.add_argument("--no-embeddings", action="store_true")
    parser.add_argument("--analysis-date", default=None)
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_dir():
        raise SystemExit(f"not a directory: {source}")
    settings = get_settings()
    if args.analysis_date:
        settings = settings.model_copy(update={"analysis_date": args.analysis_date})
    init_db()

    with SessionLocal() as session:
        batch = ingest_dataset(session, source, no_embeddings=args.no_embeddings)
        report = {"id": batch.id, "status": batch.status, "counts": batch.counts,
                  "warnings": (batch.counts or {}).get("warnings", []), "error": batch.error}
        print(json.dumps(report, indent=2, default=str))
        if batch.status != "published":
            return 1

        if not args.no_graph:
            graph = GraphMemory(settings)
            try:
                projected = graph.project_import(session, batch.id)
                session.commit()
                print(json.dumps({"graph_projected": projected, "health": graph.health()}, indent=2, default=str))
            except Exception as exc:  # a projection failure must be visible, not swallowed
                session.rollback()
                print(json.dumps({"graph_error": f"{type(exc).__name__}: {exc}"}, indent=2))
                return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
