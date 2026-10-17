# Pinned nao analytics sidecar (Task 3N)

This directory builds and runs the self-hosted [nao](https://github.com/getnao/nao)
analytics engine as a **private sidecar** for the Asset Intelligence Copilot. nao owns the
reasoning/tool loop; the Copilot owns validated domain tools, persistence and confirmation.

nao is pinned to upstream commit **`975ec422b9625be2369638273b79c5ef60a7b213`** (see
`upstream.sha`). Never vendor the whole checkout into the app tree: `vendor/` is git-ignored
and the image is built from a fetched-and-pinned clone with a small tracked patch applied.

## Layout

```
infra/nao/
  Dockerfile              lean multi-stage image (Bun backend only, no Vite UI, no Chromium, no warehouse extras)
  setup-nao.ps1           fetch + pin the upstream clone, apply patch, build the image (Windows/PowerShell)
  compose.fragment.yml    the nao service block to merge into the root docker-compose.yml (DO NOT edit that file here)
  upstream.sha            pinned commit
  env/nao.env.example     non-secret env template (tracked)
  patch/                  tracked source patch (allowlist + signed actor) + regenerate script
  project/                read-only nao project context mounted at /nao-project
  bootstrap/              narrow no-email account bootstrap helper (runs inside the pinned checkout)
  secrets/                secret generation (writes to git-ignored data/, never tracked)
  tests/                  focused regression tests for the patch and the MCP bridge
```

## Build

```powershell
pwsh infra/nao/setup-nao.ps1                 # fetch vendor/nao at the pinned SHA + apply patch + docker build
pwsh infra/nao/setup-nao.ps1 -SkipFetch      # patch/build the existing vendor/nao checkout
```

The image tag is `asset-copilot/nao:<short-sha>`, pinned by the compose fragment.

## Run

1. Merge `compose.fragment.yml` into the root `docker-compose.yml` (see the header of that
   file for the exact insertion point and required volumes/networks).
2. Generate secrets (writes `data/nao-secrets.env` + `data/nao-credentials.json`, both
   git-ignored) and confirm they are ignored before anything is written:

   ```powershell
   python infra/nao/secrets/generate_nao_secrets.py
   ```

3. `docker compose up -d nao` then bootstrap the per-dataset-user nao accounts (no email is
   ever sent — see `bootstrap/nao-bootstrap.ts` and `docs`/report for the flow).

## Enforced restrictions (in code, not in the prompt)

The tracked patch `patch/0001-copilot-sidecar.patch` changes the pinned checkout so that a
Copilot-bridged `ask_nao` run can only use a fixed built-in allowlist
(`read, list, grep, search, load_skill, mcp_call, clarification`) and so that the Asset
Knowledge MCP server receives a **per-invocation signed actor capability** derived from the
trusted `(projectId, userId)` — never from model output or shared mutable config. Correction
confirmation is **not** and never will be an MCP tool.
