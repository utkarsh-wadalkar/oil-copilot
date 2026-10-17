"""Asset Knowledge MCP endpoint (``POST /mcp``) -- Task 3N.

A deliberately small, stateless JSON-RPC 2.0 handler implementing exactly the MCP surface the
nao sidecar's MCP client needs. It is hand-rolled (rather than an OAuth resource server) so the
authorization model is *our* signed-actor capability, not an invented OAuth server:

* ``server/discover`` is answered with ``METHOD_NOT_FOUND`` so a modern-era MCP client falls
  back to the legacy ``initialize`` handshake (which this server speaks);
* ``initialize`` / ``ping`` / ``tools/list`` / ``resources/list`` / ``prompts/list`` require the
  enumerate/schema **discovery credential**;
* ``tools/call`` requires a verified **actor capability** and resolves the trusted nao subject
  to an app user; the discovery credential can never call a tool;
* notifications receive an empty ``202`` (the spec forbids a response body);
* no ``Mcp-Session-Id`` is issued, so the client opens no server-to-client GET stream.

The tool argument object never carries a caller identity: anything named ``user_id`` is dropped
and the identity is taken solely from the verified capability.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.domain import Operation
from app.mcp_auth import CapabilityError, verify_actor_capability, verify_discovery_token
from app.models import NaoAccount
from app.nao_tools import ASSET_TOOL_NAMES, run_asset_tool

PROTOCOL_VERSION = "2025-06-18"
HANDSHAKE_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
SERVER_INFO = {"name": "asset-knowledge", "version": "1.0.0"}

DISCOVERY_HEADER = "x-nao-discovery-token"
CAPABILITY_HEADER = "x-nao-actor-capability"

#: Read-only verbs reachable with the enumerate/schema discovery credential.
_DISCOVERY_METHODS = {"initialize", "ping", "tools/list", "resources/list", "resources/templates/list", "prompts/list"}
#: The only verb that requires (and is authorized by) a verified actor capability.
_ACTOR_METHODS = {"tools/call"}

_SCHEMA_OBJECT = {"type": "object", "properties": {}, "additionalProperties": False}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "asset_query",
        "description": (
            "Run a typed, parameterized Asset Knowledge query over effective (correction-applied) "
            "projections. No raw SQL and no raw uncorrected sensor rows. Returns a compact summary "
            "plus a server-side result_id; cite the summary and any warnings/conflicts you report."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": sorted(o.value for o in Operation)},
                "well_ids": {"type": "array", "items": {"type": "string"}},
                "area": {"type": "string"},
                "start": {"type": "string", "description": "ISO date, inclusive"},
                "end": {"type": "string", "description": "ISO date, inclusive"},
                "equipment_kind": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
                "producing": {"type": "boolean"},
                "reportable_only": {"type": "boolean"},
                "query": {"type": "string", "description": "free-text term for full-text operations"},
                "visual": {"type": "string", "enum": ["text", "card", "table", "line", "bar", "map", "heatmap"]},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    },
    {
        "name": "asset_status",
        "description": ("Latest recorded producing status per well with reason and staleness check "
                        "(equivalent to asset_query with operation=status)."),
        "inputSchema": {
            "type": "object",
            "properties": {"well_ids": {"type": "array", "items": {"type": "string"}}, "area": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "asset_data_dictionary",
        "description": "Return the units, available operations and rule/conflict conventions for Asset Knowledge.",
        "inputSchema": dict(_SCHEMA_OBJECT),
    },
]


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _jsonrpc_error(request_id: Any, code: int, message: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
                        status_code=status_code)


def create_mcp_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/mcp")
    def mcp_get():
        # Stateless: no session is issued, so the client never opens the server-to-client GET stream.
        return JSONResponse({"error": "the Asset Knowledge MCP is POST-only"}, status_code=405)

    @router.post("/mcp")
    async def mcp_post(request: Request, session: Session = Depends(get_session)):
        try:
            body = await request.json()
        except Exception:
            return _jsonrpc_error(None, -32700, "parse error")
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
            return _jsonrpc_error(body.get("id") if isinstance(body, dict) else None, -32600, "invalid request")
        method = body.get("method")
        request_id = body.get("id")
        is_notification = request_id is None

        # --- identity resolution ------------------------------------------------
        capability_header = request.headers.get(CAPABILITY_HEADER)
        bearer = None
        authorization = request.headers.get("authorization") or ""
        if authorization.lower().startswith("bearer "):
            bearer = authorization[7:].strip()
        capability_token = capability_header or bearer
        discovery_presented = request.headers.get(DISCOVERY_HEADER)

        actor = None
        if capability_token:
            try:
                actor = verify_actor_capability(capability_token, secret=settings.copilot_mcp_secret,
                                                issuer=settings.nao_actor_issuer,
                                                audience=settings.nao_actor_audience)
            except CapabilityError as exc:
                return _jsonrpc_error(request_id, -32001, f"invalid actor capability: {exc}", status_code=401)
        discovery_ok = verify_discovery_token(discovery_presented, settings.copilot_mcp_discovery_token)

        if not actor and not discovery_ok:
            return _jsonrpc_error(request_id, -32001, "authentication required", status_code=401)
        if method in _ACTOR_METHODS and actor is None:
            return _jsonrpc_error(request_id, -32001, "tools/call requires a signed actor capability", status_code=401)
        if method not in _ACTOR_METHODS and method not in _DISCOVERY_METHODS and method != "notifications/initialized":
            if is_notification:
                return JSONResponse(status_code=202)
            return _jsonrpc_error(request_id, -32601, f"method not found: {method}")

        # --- dispatch -----------------------------------------------------------
        if method == "notifications/initialized" or is_notification:
            return JSONResponse(status_code=202)
        if method == "initialize":
            requested = (body.get("params") or {}).get("protocolVersion")
            version = requested if requested in HANDSHAKE_VERSIONS else PROTOCOL_VERSION
            return _jsonrpc_result(request_id, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            })
        if method == "server/discover":
            # Legacy-only server: the client's auto probe falls back to `initialize`.
            return _jsonrpc_error(request_id, -32601, "method not found: server/discover")
        if method == "ping":
            return _jsonrpc_result(request_id, {})
        if method == "tools/list":
            return _jsonrpc_result(request_id, {"tools": TOOL_DEFINITIONS})
        if method in ("resources/list", "resources/templates/list"):
            return _jsonrpc_result(request_id, {"resources": []})
        if method == "prompts/list":
            return _jsonrpc_result(request_id, {"prompts": []})
        if method == "tools/call":
            return _handle_tools_call(session, settings, body, actor)

        return _jsonrpc_error(request_id, -32601, f"method not found: {method}")

    return router


def _handle_tools_call(session: Session, settings: Settings, body: dict[str, Any], actor) -> JSONResponse:
    request_id = body.get("id")
    params = body.get("params") or {}
    tool = params.get("name")
    arguments = params.get("arguments") or {}
    if tool not in ASSET_TOOL_NAMES:
        return _jsonrpc_result(request_id, {"content": [{"type": "text", "text": f"unknown tool {tool!r}"}],
                                            "isError": True})
    if not isinstance(arguments, dict):
        return _jsonrpc_result(request_id, {"content": [{"type": "text", "text": "arguments must be an object"}],
                                            "isError": True})
    # Resolve the *trusted* nao subject to an app user. An unmapped subject is never allowed to
    # act as anyone: there is no fallback identity.
    account = session.scalar(select(NaoAccount).where(NaoAccount.nao_user_id == actor.nao_user_id))
    if account is None:
        return _jsonrpc_error(request_id, -32001, "actor subject is not mapped to an app user", status_code=403)
    try:
        analysis_date = date.fromisoformat(settings.analysis_date)
    except ValueError:
        analysis_date = date.today()
    result = run_asset_tool(session, tool=tool, arguments=arguments, app_user_id=account.app_user_id,
                            nao_user_id=actor.nao_user_id, project_id=actor.project_id or account.nao_project_id,
                            request_id=actor.jti, conversation_id=None, analysis_date=analysis_date)
    return _jsonrpc_result(request_id, result)
