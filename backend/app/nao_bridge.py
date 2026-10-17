"""Minimal Python client for the pinned nao analytics sidecar (Task 3N).

The Copilot never re-implements nao's reasoning loop: it authenticates as a per-dataset-user
nao account, opens the sidecar's MCP endpoint over Streamable HTTP, and drives ``ask_nao`` /
``get_nao_answer``. Everything else (context, tools, the LLM loop) lives in nao.

Two hard rules from the brief:

* the client only ever uses the *private* ``(app_user_id, conversation_id)`` mapping plus a
  native per-user nao account; a nao chat id supplied by the browser is never trusted;
* if nao is unreachable or a session cannot be obtained, the caller is told **unavailable** —
  no fake answers are synthesized.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings

NAO_UNAVAILABLE = "nao sidecar unavailable"


@dataclass
class NaoCredential:
    """Exact private mapping for one dataset user's nao account."""

    app_user_id: str
    nao_user_id: str
    nao_email: str
    nao_password: str
    nao_project_id: str

    def public(self) -> dict[str, Any]:
        return {"app_user_id": self.app_user_id, "nao_user_id": self.nao_user_id,
                "nao_email": self.nao_email, "nao_project_id": self.nao_project_id}


class NaoCredentialStore:
    """File-backed credential store (git-ignored ``data/``), written and read 0600."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    def get(self, app_user_id: str) -> NaoCredential | None:
        raw = self._load().get(app_user_id)
        return NaoCredential(**raw) if raw else None

    def upsert(self, credential: NaoCredential) -> None:
        data = self._load()
        existing = data.get(credential.app_user_id)
        merged = {**(existing or {}), **asdict(credential)}
        data[credential.app_user_id] = merged
        self._save(data)

    def by_nao_user(self, nao_user_id: str) -> NaoCredential | None:
        for raw in self._load().values():
            if raw.get("nao_user_id") == nao_user_id:
                return NaoCredential(**raw)
        return None

    def all(self) -> list[NaoCredential]:
        return [NaoCredential(**raw) for raw in self._load().values()]


@dataclass
class NaoAskResult:
    status: str  # running | complete | needs_clarification | error | unavailable
    text: str = ""
    chat_id: str | None = None
    chat_url: str | None = None
    queries: list[dict[str, Any]] = field(default_factory=list)
    story_ids: list[str] = field(default_factory=list)
    clarification: dict[str, Any] | None = None
    error: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"complete", "error"}

    @classmethod
    def unavailable(cls, reason: str = NAO_UNAVAILABLE) -> "NaoAskResult":
        return cls(status="unavailable", error=reason)


class NaoUnavailableError(RuntimeError):
    """Raised when the sidecar cannot be reached or authenticated; never faked."""


class NaoClient:
    """Async-free façade over the sidecar's MCP endpoint.

    Public methods are synchronous so a FastAPI sync endpoint (threadpool) can call them; the
    async MCP session is driven internally with ``asyncio.run``.
    """

    def __init__(self, settings: Settings, store: NaoCredentialStore | None = None):
        self.settings = settings
        self.store = store or NaoCredentialStore(settings.nao_credentials_path)

    def available(self) -> bool:
        return bool(self.settings.nao_enabled and self.settings.nao_base_url)

    # -- sessions --------------------------------------------------------------
    async def _session_token(self, credential: NaoCredential) -> str:
        base = self.settings.nao_base_url.rstrip("/")
        async with httpx.AsyncClient(base_url=base, timeout=20.0) as client:
            response = await client.post("/api/auth/sign-in/email",
                                         json={"email": credential.nao_email, "password": credential.nao_password})
            if response.status_code >= 400:
                raise NaoUnavailableError(f"nao login failed ({response.status_code})")
            token_response = await client.get("/api/trpc/mcpEndpoint.getBearerToken")
            if token_response.status_code >= 400:
                raise NaoUnavailableError(f"nao bearer token failed ({token_response.status_code})")
            return _extract_token(token_response.json())

    # -- tools -----------------------------------------------------------------
    async def _call_tool(self, credential: NaoCredential, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        token = await self._session_token(credential)
        from mcp.client.client import Client
        from mcp.client.streamable_http import streamable_http_client

        url = f"{self.settings.nao_base_url.rstrip('/')}/mcp/{credential.nao_project_id}"
        http_client = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=120.0)
        transport = streamable_http_client(url, http_client=http_client)
        try:
            async with Client(server=transport, mode="legacy") as client:
                result = await client.call_tool(tool, arguments)
        finally:
            await http_client.aclose()
        if getattr(result, "is_error", False):
            raise NaoUnavailableError(_content_text(result) or f"{tool} failed")
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            return structured
        text = _content_text(result)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            pass
        return {"status": "complete", "text": text or ""}

    async def _ask_async(self, credential: NaoCredential, question: str,
                         chat_id: str | None) -> NaoAskResult:
        arguments: dict[str, Any] = {"question": question}
        if chat_id:
            arguments["chatId"] = chat_id
        return _to_result(await self._call_tool(credential, "ask_nao", arguments))

    async def _poll_async(self, credential: NaoCredential, chat_id: str) -> NaoAskResult:
        return _to_result(await self._call_tool(credential, "get_nao_answer", {"chatId": chat_id}))

    # -- sync façade -----------------------------------------------------------
    def ask_nao(self, app_user_id: str, question: str, chat_id: str | None = None) -> NaoAskResult:
        credential = self.store.get(app_user_id)
        if not credential:
            return NaoAskResult.unavailable("no nao account mapped for this user")
        if not self.available():
            return NaoAskResult.unavailable()
        try:
            return asyncio.run(self._ask_async(credential, question, chat_id))
        except NaoUnavailableError as exc:
            return NaoAskResult.unavailable(str(exc))
        except Exception as exc:  # noqa: BLE001 - transport errors are surfaced, never faked
            return NaoAskResult.unavailable(f"{type(exc).__name__}: {exc}")

    def get_nao_answer(self, app_user_id: str, chat_id: str) -> NaoAskResult:
        credential = self.store.get(app_user_id)
        if not credential:
            return NaoAskResult.unavailable("no nao account mapped for this user")
        if not self.available():
            return NaoAskResult.unavailable()
        try:
            return asyncio.run(self._poll_async(credential, chat_id))
        except NaoUnavailableError as exc:
            return NaoAskResult.unavailable(str(exc))
        except Exception as exc:  # noqa: BLE001
            return NaoAskResult.unavailable(f"{type(exc).__name__}: {exc}")


def _extract_token(payload: Any) -> str:
    """Pull the session token out of a tRPC/SuperJSON response, tolerating both shapes."""
    if isinstance(payload, dict):
        for key in ("token",):
            if isinstance(payload.get(key), str):
                return payload[key]
        result = payload.get("result")
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict):
                inner = data.get("json", data)
                if isinstance(inner, dict) and isinstance(inner.get("token"), str):
                    return inner["token"]
    raise NaoUnavailableError("nao bearer token response did not contain a token")


def _content_text(result: Any) -> str:
    parts = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _to_result(structured: dict[str, Any]) -> NaoAskResult:
    return NaoAskResult(
        status=str(structured.get("status", "complete")),
        text=str(structured.get("text", "") or ""),
        chat_id=structured.get("chatId"),
        chat_url=structured.get("chatUrl"),
        queries=list(structured.get("queries") or []),
        story_ids=list(structured.get("story_ids") or []),
        clarification=structured.get("clarification"),
        error=structured.get("error"),
    )
