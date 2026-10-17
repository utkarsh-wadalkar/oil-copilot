# Fieldnote / Asset Intelligence frontend

The OpenUI chat workspace for the Asset Intelligence Copilot. It is a Next.js App
Router app (TypeScript, React 19, plain CSS) that renders server-validated
`AnswerEnvelope`s through `@openuidev/react-lang`.

This is **phase 4a**: one working vertical slice. It ships the user picker, the
thread sidebar, the composer, the answer renderer for `text`/`card` visuals, and
the evidence drawer. Line/bar/heatmap charts, the geographical map, the
correction drawer, update history and the capabilities/import panels are not part
of this phase.

## Requirements

- Node.js 20.9 or newer (developed on Node 26; the container uses `node:24-alpine`).
- A running backend at the API base URL (default `http://localhost:8000`).

## Environment

| Variable | Default | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Origin the **browser** calls the backend on. Public, not a secret. Backend secrets stay in the backend's own `.env`; this app never reads them. |

The backend already allows `http://localhost:3000` and `http://127.0.0.1:3000`
through CORS (`backend/app/config.py`).

## Run locally

From `frontend/`:

```bash
npm install                 # or: npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Then open http://localhost:3000, choose a dataset user in the header, and ask a
question. On Windows PowerShell set the variable first:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000"
npm run dev
```

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Next dev server on `0.0.0.0:3000` |
| `npm run build` | Production build (`.next/standalone`) |
| `npm start` | Serve the production build on `0.0.0.0:3000` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Contract, privacy and renderer-mapping tests (node's built-in runner) |

## Run with Docker Compose

From the repository root:

```bash
docker compose build frontend
docker compose up -d backend frontend
```

The `frontend` service builds `./frontend` (multi-stage `Dockerfile`), maps
`127.0.0.1:3000:3000`, and starts after `backend`. The public API URL is passed
as a build argument, because Next inlines public variables at build time.

## Privacy model

- Switching the dataset user replaces the whole session in one state transition
  (`sessionForUser`) *before* any request for the new user is issued, so the
  previous user's thread, messages, answers and evidence cannot flash on screen.
- In-flight requests carry a `PrivacyGuard` scope. Switching user, opening a
  thread or starting a new one calls `guard.reset()`, which aborts every live
  request and invalidates its epoch, so a slow response can neither paint nor
  dispatch into the new session.
- Browser storage remembers only the selected user id and thread id. Message
  bodies, answers and evidence stay in memory for the life of the tab.

## Layout

```
app/            layout, page, globals.css
components/     Workspace (orchestrator) + leaf components
lib/            contracts (zod), api client, session/privacy, storage, formatting
tests/          node:test suite over the real lib modules
```
