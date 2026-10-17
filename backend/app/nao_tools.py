"""Typed Asset Knowledge tools exposed to the nao reasoning loop over MCP (Task 3N).

These are the only way nao reaches the Copilot's facts. Each tool:

* accepts a *typed* argument object (never raw SQL text), which is validated into the
  existing :class:`~app.domain.QuerySpec` contract and executed through
  :class:`~app.knowledge.AssetKnowledge` -- i.e. parameterized SQLAlchemy over the effective
  (correction-applied) projections, never the raw uncorrected sensor rows;
* ignores any model-supplied ``user_id``: the caller identity is the verified actor from the
  signed capability;
* stores the full validated answer envelope server-side under the actor and returns only a
  compact reference plus a small preview, so the coordinator -- not the model -- owns the
  payload the UI renders.

There is deliberately **no** correction-confirmation tool and never will be: confirmation stays
in the Copilot's own prepare/confirm workflow.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.domain import Operation, QuerySpec
from app.knowledge import AssetKnowledge
from app.models import NaoToolResult, new_id

MAX_PREVIEW_ROWS = 25

#: The exact set of tools the Asset Knowledge server exposes.
ASSET_TOOL_NAMES = ("asset_query", "asset_status", "asset_data_dictionary")

_DATA_DICTIONARY: dict[str, Any] = {
    "source": "effective correction-applied projections (never raw sensor rows)",
    "units": {"temperature_c": "C", "spill_volume_bbl": "bbl", "spill_area_pct": "%",
              "downtime_days": "days", "containment_hours": "hours", "cost_usd": "USD"},
    "operations": {
        "status": "latest recorded producing status with reason and staleness check",
        "temperatures": "wellhead vs ambient readings with producing delta and threshold",
        "spills": "recorded spills with volume, area and reportable classification",
        "downtime": "non-producing day counts per well",
        "maintenance": "maintenance events with equipment kind and cost",
        "rca": "corrective-repair counts vs the RCA threshold per equipment",
        "containment": "containment hours vs the extracted SOP deadline",
        "compliance": "regulatory reporting/verification deadlines and breaches",
        "notes": "corrections and context notes with authorship and validity",
        "documents": "full-text search over active documents/manuals",
        "guidance": "applicable official procedures and derived deadlines",
    },
    "rules": "thresholds are extracted from active manuals/SOPs; team corrections may override",
    "conflicts": "disagreements are reported as conflicts for human confirmation, never resolved silently",
}


def run_asset_tool(session: Session, *, tool: str, arguments: dict[str, Any], app_user_id: str,
                   nao_user_id: str, project_id: str | None, request_id: str | None,
                   conversation_id: str | None, analysis_date: date) -> dict[str, Any]:
    """Execute one Asset Knowledge tool. Returns an MCP ``CallToolResult``-shaped dict."""
    args = {k: v for k, v in (arguments or {}).items() if k != "user_id"}  # never trust a model identity
    if tool == "asset_data_dictionary":
        return _ok({"dictionary": _DATA_DICTIONARY}, result_id=None, summary="asset data dictionary")
    if tool == "asset_status":
        args = {**args, "operation": "status"}
    if tool in ("asset_query", "asset_status"):
        return _asset_query(session, args=args, app_user_id=app_user_id, nao_user_id=nao_user_id,
                            project_id=project_id, request_id=request_id,
                            conversation_id=conversation_id, analysis_date=analysis_date)
    return _error(f"unknown tool {tool!r}")


def _asset_query(session: Session, *, args: dict[str, Any], app_user_id: str, nao_user_id: str,
                 project_id: str | None, request_id: str | None, conversation_id: str | None,
                 analysis_date: date) -> dict[str, Any]:
    allowed = {"operation", "well_ids", "area", "start", "end", "equipment_kind", "limit",
               "producing", "reportable_only", "query", "visual"}
    unknown = set(args) - allowed
    if unknown:
        return _error(f"unsupported arguments: {', '.join(sorted(unknown))}")
    try:
        spec = QuerySpec.model_validate(args)
    except Exception as exc:  # validation contract is the security boundary for arguments
        return _error(f"invalid asset query: {type(exc).__name__}: {exc}"[:500])
    if spec.operation in {Operation.compliance, Operation.guidance} and not (spec.well_ids or spec.area):
        # These operations are expensive and must be scoped; refuse an unbounded fleet sweep.
        return _error("compliance/guidance queries must name well_ids or an area")
    try:
        envelope = AssetKnowledge(session, analysis_date).query(spec)
    except ValueError as exc:
        return _error(f"asset query could not run: {exc}"[:500])
    payload = envelope.model_dump(mode="json")
    payload["_spec"] = spec.model_dump(mode="json")
    result_id = new_id()
    payload["result_id"] = result_id
    row = NaoToolResult(id=result_id, app_user_id=app_user_id, nao_user_id=nao_user_id,
                        project_id=project_id, request_id=request_id,
                        conversation_id=conversation_id, tool="asset_query",
                        status="complete", payload=payload)
    session.add(row)
    session.commit()
    preview = payload["findings"][0]["value"] if payload.get("findings") else []
    if isinstance(preview, list):
        preview = preview[:MAX_PREVIEW_ROWS]
    structured = {
        "result_id": result_id,
        "summary": payload["summary"],
        "analysis_date": payload["analysis_date"],
        "selected_well_ids": payload.get("selected_well_ids", []),
        "warnings": payload.get("warnings", []),
        "conflicts": payload.get("conflicts", []),
        "preview": preview,
        "preview_truncated": isinstance(payload.get("findings", [{}])[0].get("value"), list)
        and len(payload["findings"][0]["value"]) > MAX_PREVIEW_ROWS,
    }
    return _ok(structured, result_id=result_id, summary=payload["summary"])


def _ok(structured: dict[str, Any], *, result_id: str | None, summary: str) -> dict[str, Any]:
    text = f"{summary} (result_id={result_id})" if result_id else summary
    return {"content": [{"type": "text", "text": text}], "structuredContent": structured,
            "isError": False}


def _error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}
