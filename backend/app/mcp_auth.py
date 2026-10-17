"""Signed-actor capabilities for the Asset Knowledge MCP endpoint (Task 3N).

nao's reasoning loop never talks to the Copilot database directly. Every ``tools/call`` it
makes to ``/mcp`` carries a short-lived HS256 capability minted **per invocation** by the
patched nao sidecar from the trusted ``(projectId, userId)`` of the run. The model's tool
arguments are never consulted when minting it, so a spoofed ``user_id`` in the arguments is
ignored, and a capability signed for one user cannot be replayed as another.

Two distinct credentials reach ``/mcp``:

* the **actor capability** (this module) -- authorizes ``tools/call`` and binds the call to
  exactly one nao subject;
* the **discovery token** -- an enumerate/schema-only credential that authorizes
  ``initialize`` / ``tools/list`` but can never call a tool.

Both are compared in constant time. The actor capability additionally pins issuer, audience,
expiry and a bounded max-age, and carries a unique ``jti``.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import jwt

ISSUER = "nao-sidecar"
CLOCK_SKEW_SECONDS = 5


class CapabilityError(Exception):
    """A presented actor capability failed verification."""


@dataclass(frozen=True)
class ActorCapability:
    """A verified actor capability. ``nao_user_id`` is the *only* trusted caller identity."""

    nao_user_id: str
    project_id: str | None
    audience: str
    jti: str
    issued_at: int
    expires_at: int


def mint_actor_capability(*, secret: str, issuer: str, audience: str, nao_user_id: str,
                          project_id: str | None = None, ttl_seconds: int = 60,
                          jti: str | None = None, issued_at: datetime | None = None) -> str:
    """Mint an HS256 actor capability. Mirrors the nao sidecar's ``jose`` SignJWT exactly."""
    if not secret:
        raise CapabilityError("no capability secret configured")
    now = issued_at or datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": nao_user_id,
        "jti": jti or str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + int(ttl_seconds),
    }
    if project_id is not None:
        payload["project_id"] = project_id
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_actor_capability(token: str, *, secret: str, issuer: str, audience: str,
                            max_ttl_seconds: int = 120) -> ActorCapability:
    """Verify signature, issuer, audience and expiry, then enforce a bounded max-age.

    HS256 verification in PyJWT uses ``hmac.compare_digest`` and therefore compares the
    signature in constant time. Any failure raises :class:`CapabilityError` without echoing
    token material.
    """
    if not secret:
        raise CapabilityError("no capability secret configured")
    if not token:
        raise CapabilityError("missing capability")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=audience,
            issuer=issuer,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["iss", "aud", "sub", "jti", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:  # invalid signature, expired, wrong aud/iss, malformed
        raise CapabilityError(f"invalid capability: {type(exc).__name__}") from None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise CapabilityError("capability subject is not a string")
    try:
        issued_at = int(claims["iat"])
        expires_at = int(claims["exp"])
    except (KeyError, TypeError, ValueError):
        raise CapabilityError("capability is missing numeric iat/exp") from None
    now = int(datetime.now(timezone.utc).timestamp())
    # Reject a not-yet-valid token and one whose stated lifetime exceeds the policy cap.
    if issued_at - CLOCK_SKEW_SECONDS > now:
        raise CapabilityError("capability issued in the future")
    if expires_at - issued_at > max_ttl_seconds + CLOCK_SKEW_SECONDS:
        raise CapabilityError("capability lifetime exceeds the policy maximum")
    project_id = claims.get("project_id")
    return ActorCapability(
        nao_user_id=subject,
        project_id=project_id if isinstance(project_id, str) else None,
        audience=str(claims.get("aud")),
        jti=str(claims.get("jti")),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def verify_discovery_token(presented: str | None, expected: str) -> bool:
    """Constant-time comparison of the enumerate/schema credential."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
