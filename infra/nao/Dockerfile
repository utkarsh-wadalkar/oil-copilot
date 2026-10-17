# Lean, pinned nao sidecar image (Task 3N).
#
# Deliberately narrower than upstream's Dockerfile:
#   * no Vite frontend build and no `dist/` copy -> nao runs in API-only mode
#     (staticRoot is absent, so app.ts skips the static plugin);
#   * no Python/FastAPI warehouse sidecar, no Chromium, no warehouse extras —
#     the Copilot's typed Asset Knowledge MCP tools replace warehouse SQL;
#   * the JS dependency tree is installed from the committed lockfile.
#
# Build context is the repository root so the image can read the pinned
# `vendor/nao` checkout that `setup-nao.ps1` fetched. Do NOT commit `vendor/`.
#
#   docker build -f infra/nao/Dockerfile -t asset-copilot/nao:<sha> .

FROM node:24-slim AS base
WORKDIR /app
RUN npm install -g bun

# --- JS dependencies (all workspaces, single locked install) -----------------
FROM base AS deps
WORKDIR /app
COPY vendor/nao/package.json vendor/nao/bun.lock vendor/nao/bunfig.toml ./
COPY vendor/nao/apps/backend/package.json ./apps/backend/
COPY vendor/nao/apps/shared/package.json ./apps/shared/
# The backend imports `@nao/shared` modules (chart-builder.tsx) whose deps live in the frontend
# workspace and are hoisted at the root. Copy its package.json so the lockfile resolves, but never
# copy or build the frontend source: nao still runs API-only.
COPY vendor/nao/apps/frontend/package.json ./apps/frontend/
# --ignore-scripts skips the husky `prepare` hook.
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --ignore-scripts

# --- runtime -----------------------------------------------------------------
FROM base AS runtime
ARG APP_VERSION=dev
ARG APP_COMMIT=unknown

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libpq5 git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json ./package.json
COPY vendor/nao/apps/backend ./apps/backend
COPY vendor/nao/apps/shared ./apps/shared
COPY vendor/nao/example ./example
# Narrow, no-email account bootstrap (Task 3N); lives outside the pinned patch.
COPY infra/nao/bootstrap/nao-bootstrap.ts ./apps/backend/scripts/nao-bootstrap.ts

ENV MODE=prod \
    NODE_ENV=production \
    NAO_MODE=self-hosted \
    NAO_STORAGE_BACKEND=none \
    DOCKER=1 \
    APP_VERSION=$APP_VERSION \
    APP_COMMIT=$APP_COMMIT \
    FASTAPI_PORT=8005

# Metadata DB lives on a mounted volume (see compose.fragment.yml).
ENV DB_URI=sqlite:/app/data/nao-metadata.db \
    NAO_DEFAULT_PROJECT_PATH=/nao-project

EXPOSE 5005
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 \
    CMD curl -fsS http://127.0.0.1:5005/api/health || exit 1

# Bun executes the TypeScript entrypoint directly (no build step needed).
CMD ["bun", "run", "apps/backend/src/cli.ts", "serve", "--host", "0.0.0.0", "--port", "5005"]
