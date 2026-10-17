# Asset Intelligence Copilot implementation

## Binding design
Local Next.js/TypeScript chat, FastAPI/Python, PostgreSQL/pgvector authoritative facts and saved results, independent Neo4j Community evidence graph, self-hosted Mem0 semantic recall, Ollama Cloud gemma4:cloud, local all-MiniLM-L6-v2 embeddings. No paid model fallback. No Git commits. Preserve existing docs and .gitignote.

## Tasks
1. Foundation: Docker Compose, configuration, SQLAlchemy persistence, Pydantic answer contracts and health entry point.
2. Asset Knowledge: transactional versioned ingestion, citations, extracted rules/reports, typed deterministic analytics and audited corrections. Validate against sample data.
3. Conversation Memory and Answer Orchestration: provider tool loop, exact saved results, private recall/current comparison, graph and Mem0 outbox worker, REST interfaces and failure behavior.
4. OpenUI frontend: user picker, persistent threads, conversational rendering, evidence drawer, corrections, original/current comparison, requested visuals.
5. Scenario evaluation, integration review and documentation: all 18 scenarios, import/restart/privacy/failure tests, build/typecheck, local run instructions and limitations.

## Shared invariants
Immutable original sources and results; effective facts apply formal corrections globally at their explicit scope. Informal contradictions are retained. Never use vector top-k for numeric totals. Every calculated finding links to actual source record/rule evidence. Private chat retrieval is user-scoped, including graph traversal. Indexes are retryable projections; PostgreSQL is the source of truth. Analysis date defaults 2026-10-17; Q6 window 2026-06-16 through 2026-10-16. No hardcoded scenario result lists or expected totals in production. UI validates and resolves trusted data, never arbitrary generated code.
