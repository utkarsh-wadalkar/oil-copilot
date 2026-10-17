"""Task 3N: the Asset Knowledge MCP endpoint, its signed-actor contract and the salted run.

These tests exercise the *real* HTTP MCP endpoint (hand-rolled JSON-RPC) and, via the official
MCP Python SDK client, the real Streamable-HTTP protocol handshake. They assert the security
invariants the brief makes binding:

* the discovery credential can enumerate tools but can never call one;
* ``tools/call`` requires a signed actor capability and resolves the trusted nao subject to an
  app user -- a spoofed ``user_id`` argument or an unmapped subject is never trusted;
* the tool allowlist is fixed and never contains forbidden tools;
* credentials persist across a restart and no secret is ever written to stdout.
"""
import asyncio
import json
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx2
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base
from app.mcp_auth import (CapabilityError, mint_actor_capability, verify_actor_capability,
                          verify_discovery_token)
from app.main import create_app
from app.models import NaoAccount, NaoToolResult
from app.nao_bridge import NaoClient, NaoCredential, NaoCredentialStore

ROOT = Path(__file__).resolve().parents[2] / "assets/flytbase-dataset/sample-data"
USER_A = "U-201"
USER_B = "U-202"
NAO_A = "nao-user-a"
NAO_B = "nao-user-b"
NAO_UNMAPPED = "nao-user-z"
PROJECT = "proj-sidecar-1"
SECRET = "unit-test-secret-not-a-real-credential-000"
DISCOVERY = "unit-test-discovery-token-not-real-000"
FORBIDDEN = {"story", "task", "write", "python", "sandbox", "web_search", "followup",
             "create_story", "update_story", "confirm_correction", "execute_sql", "read_query_result"}


@pytest.fixture(scope="module")
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    from app.ingestion import ingest_dataset

    with session_factory() as session:
        batch = ingest_dataset(session, ROOT)
        assert batch.status == "published", batch.error
        session.add(NaoAccount(app_user_id=USER_A, nao_user_id=NAO_A, nao_email="a@sidecar.invalid",
                               nao_project_id=PROJECT))
        session.add(NaoAccount(app_user_id=USER_B, nao_user_id=NAO_B, nao_email="b@sidecar.invalid",
                               nao_project_id=PROJECT))
        session.commit()
    return session_factory


@pytest.fixture(scope="module")
def settings():
    return get_settings().model_copy(update={
        "ollama_api_key": "", "dataset_root": str(ROOT), "analysis_date": "2026-10-17",
        "copilot_mcp_secret": SECRET, "copilot_mcp_discovery_token": DISCOVERY,
        "nao_asset_server": "asset-knowledge", "nao_actor_issuer": "nao-sidecar",
        "nao_actor_audience": "asset-knowledge"})


@pytest.fixture(scope="module")
def app(factory, settings):
    engine = factory.kw["bind"]
    return create_app(engine, settings=settings)


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def _rpc(client, method, params=None, headers=None, request_id=1):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers or {})


def _capability(nao_user_id=NAO_A, project_id=PROJECT, **kwargs):
    return mint_actor_capability(secret=SECRET, issuer="nao-sidecar", audience="asset-knowledge",
                                 nao_user_id=nao_user_id, project_id=project_id, **kwargs)


def _actor_headers(nao_user_id=NAO_A, **kwargs):
    return {"X-Nao-Actor-Capability": _capability(nao_user_id, **kwargs)}


def _discovery_headers():
    return {"X-Nao-Discovery-Token": DISCOVERY}


# --- discovery credential ---------------------------------------------------

def test_tools_list_requires_a_credential(client):
    assert _rpc(client, "initialize", {"protocolVersion": "2025-06-18"}).status_code == 401
    assert _rpc(client, "tools/list").status_code == 401


def test_initialize_and_tools_list_with_discovery_credential(client):
    init = _rpc(client, "initialize", {"protocolVersion": "2025-06-18"}, _discovery_headers())
    assert init.status_code == 200
    assert init.json()["result"]["serverInfo"]["name"] == "asset-knowledge"
    listed = _rpc(client, "tools/list", headers=_discovery_headers())
    assert listed.status_code == 200
    assert {t["name"] for t in listed.json()["result"]["tools"]} == {
        "asset_query", "asset_status", "asset_data_dictionary"}


def test_discovery_credential_can_never_call_a_tool(client):
    response = _rpc(client, "tools/call", {"name": "asset_data_dictionary", "arguments": {}},
                    _discovery_headers())
    assert response.status_code == 401


def test_server_discover_is_method_not_found_for_legacy_fallback(client):
    response = _rpc(client, "server/discover", {}, _discovery_headers())
    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32601


# --- allowlist --------------------------------------------------------------

def test_allowlist_never_includes_forbidden_tools(client):
    tools = {t["name"] for t in _rpc(client, "tools/list", headers=_discovery_headers()).json()["result"]["tools"]}
    assert tools.isdisjoint(FORBIDDEN)
    # There is deliberately no correction-confirmation tool.
    assert "confirm_correction" not in tools
    assert "confirm_feedback" not in tools


# --- signed actor capability ------------------------------------------------

def test_signed_actor_calls_tool_and_stores_owned_envelope(client, factory):
    response = _rpc(client, "tools/call", {"name": "asset_query",
                                           "arguments": {"operation": "status", "well_ids": ["WELL-0001"]}},
                    _actor_headers(NAO_A))
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] is False
    result_id = result["structuredContent"]["result_id"]
    with factory() as session:
        row = session.get(NaoToolResult, result_id)
        assert row is not None and row.app_user_id == USER_A and row.nao_user_id == NAO_A
        assert row.request_id  # the capability jti is recorded for correlation


def test_spoofed_user_id_argument_is_ignored(client, factory):
    response = _rpc(client, "tools/call",
                    {"name": "asset_query",
                     "arguments": {"operation": "status", "well_ids": ["WELL-0001"], "user_id": USER_B}},
                    _actor_headers(NAO_A))
    result_id = response.json()["result"]["structuredContent"]["result_id"]
    with factory() as session:
        row = session.get(NaoToolResult, result_id)
        # The model-supplied user_id was dropped; ownership follows the capability.
        assert row.app_user_id == USER_A


def test_forged_or_tampered_capability_is_rejected(client):
    forged = mint_actor_capability(secret="a-different-secret", issuer="nao-sidecar",
                                   audience="asset-knowledge", nao_user_id=NAO_A)
    assert _rpc(client, "tools/call", {"name": "asset_status", "arguments": {}},
                {"X-Nao-Actor-Capability": forged}).status_code == 401
    good = _capability(NAO_A)
    tampered = good[:-3] + ("aaa" if good[-3:] != "aaa" else "bbb")
    assert _rpc(client, "tools/call", {"name": "asset_status", "arguments": {}},
                {"X-Nao-Actor-Capability": tampered}).status_code == 401


def test_wrong_audience_and_expired_capability_are_rejected(client):
    wrong_aud = mint_actor_capability(secret=SECRET, issuer="nao-sidecar", audience="some-other-server",
                                      nao_user_id=NAO_A)
    assert _rpc(client, "tools/call", {"name": "asset_status", "arguments": {}},
                {"X-Nao-Actor-Capability": wrong_aud}).status_code == 401
    expired = _capability(NAO_A, ttl_seconds=60, issued_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert _rpc(client, "tools/call", {"name": "asset_status", "arguments": {}},
                {"X-Nao-Actor-Capability": expired}).status_code == 401


def test_unmapped_actor_subject_is_denied(client):
    response = _rpc(client, "tools/call", {"name": "asset_status", "arguments": {"well_ids": ["WELL-0001"]}},
                    _actor_headers(NAO_UNMAPPED))
    assert response.status_code == 403


def test_cross_user_cannot_reach_another_users_envelope(client, factory):
    # A row created by B is never owned by A even if the ids overlap; ownership is per capability.
    response = _rpc(client, "tools/call", {"name": "asset_status", "arguments": {"well_ids": ["WELL-0001"]}},
                    _actor_headers(NAO_B))
    result_id = response.json()["result"]["structuredContent"]["result_id"]
    with factory() as session:
        row = session.get(NaoToolResult, result_id)
        assert row.app_user_id == USER_B
        # And A's own results are never visible to B's subject.
        others = list(session.scalars(select(NaoToolResult).where(NaoToolResult.app_user_id == USER_A)))
        assert all(r.id != result_id for r in others)


def test_capability_verification_unit_roundtrip():
    token = mint_actor_capability(secret=SECRET, issuer="nao-sidecar", audience="asset-knowledge",
                                  nao_user_id=NAO_A, project_id=PROJECT)
    capability = verify_actor_capability(token, secret=SECRET, issuer="nao-sidecar",
                                         audience="asset-knowledge")
    assert capability.nao_user_id == NAO_A and capability.project_id == PROJECT
    with pytest.raises(CapabilityError):
        verify_actor_capability(token, secret=SECRET, issuer="nao-sidecar", audience="elsewhere")
    with pytest.raises(CapabilityError):
        verify_actor_capability(token, secret=SECRET, issuer="nao-sidecar", audience="asset-knowledge",
                                max_ttl_seconds=-1)


def test_discovery_token_compare():
    assert verify_discovery_token(DISCOVERY, DISCOVERY) is True
    assert verify_discovery_token("nope", DISCOVERY) is False
    assert verify_discovery_token(None, DISCOVERY) is False


# --- secret hygiene ---------------------------------------------------------

def test_no_secret_is_written_to_stdout(client, capsys):
    _rpc(client, "tools/call", {"name": "asset_query",
                                "arguments": {"operation": "status", "well_ids": ["WELL-0001"]}},
         _actor_headers(NAO_A))
    _rpc(client, "tools/list", headers=_discovery_headers())
    captured = capsys.readouterr()
    assert SECRET not in captured.out and DISCOVERY not in captured.out
    assert SECRET not in captured.err and DISCOVERY not in captured.err


# --- credential persistence -------------------------------------------------

def test_credentials_persist_across_restart(tmp_path):
    path = tmp_path / "nao-credentials.json"
    store = NaoCredentialStore(path)
    store.upsert(NaoCredential(app_user_id=USER_A, nao_user_id=NAO_A, nao_email="a@sidecar.invalid",
                               nao_password="strong-random-local-credential", nao_project_id=PROJECT))
    # A fresh store instance (a "restart") reads the same mapping without re-provisioning.
    reopened = NaoCredentialStore(path)
    credential = reopened.get(USER_A)
    assert credential is not None and credential.nao_user_id == NAO_A
    assert reopened.by_nao_user(NAO_A).app_user_id == USER_A
    # Re-upserting is idempotent and preserves the existing password when not supplied anew.
    reopened.upsert(NaoCredential(app_user_id=USER_A, nao_user_id=NAO_A, nao_email="a@sidecar.invalid",
                                  nao_password="strong-random-local-credential", nao_project_id=PROJECT))
    assert len(reopened.all()) == 1
    if os.name != "nt":
        assert (path.stat().st_mode & 0o777) == 0o600


# --- bridge -----------------------------------------------------------------

def test_nao_client_reports_unavailable_without_sidecar(settings, tmp_path):
    offline = settings.model_copy(update={"nao_enabled": False,
                                          "nao_credentials_path": str(tmp_path / "missing.json")})
    result = NaoClient(offline).ask_nao(USER_A, "Is WELL-0001 producing?")
    assert result.status == "unavailable" and result.text == ""


# --- real MCP SDK client round trip -----------------------------------------

def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="module")
def live_endpoint(app):
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=5)


async def _sdk_list_tools(url, headers):
    from mcp.client.client import Client
    from mcp.client.streamable_http import streamable_http_client

    http_client = httpx2.AsyncClient(headers=headers)
    transport = streamable_http_client(url, http_client=http_client)
    try:
        async with Client(server=transport, mode="legacy") as mcp_client:
            listing = await mcp_client.list_tools()
            return [tool.name for tool in listing.tools]
    finally:
        await http_client.aclose()


async def _sdk_call_tool(url, headers, name, arguments):
    from mcp.client.client import Client
    from mcp.client.streamable_http import streamable_http_client

    http_client = httpx2.AsyncClient(headers=headers)
    transport = streamable_http_client(url, http_client=http_client)
    try:
        async with Client(server=transport, mode="legacy") as mcp_client:
            return await mcp_client.call_tool(name, arguments)
    finally:
        await http_client.aclose()


def test_real_mcp_sdk_client_enumerates_with_discovery(live_endpoint):
    names = asyncio.run(_sdk_list_tools(live_endpoint, _discovery_headers()))
    assert set(names) == {"asset_query", "asset_status", "asset_data_dictionary"}


def test_real_mcp_sdk_client_calls_tool_as_actor(live_endpoint):
    # A tools/call connection still needs the discovery credential for its own `initialize`.
    headers = {**_discovery_headers(), **_actor_headers(NAO_A)}
    result = asyncio.run(_sdk_call_tool(live_endpoint, headers, "asset_query",
                                        {"operation": "status", "well_ids": ["WELL-0001"]}))
    assert result.is_error is False
    assert result.structured_content["result_id"]


def test_real_mcp_sdk_client_denied_with_discovery_only(live_endpoint):
    with pytest.raises(Exception):
        asyncio.run(_sdk_call_tool(live_endpoint, _discovery_headers(), "asset_status", {}))
