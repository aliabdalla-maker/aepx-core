"""Model Context Protocol server (INT-02, AX governed agent actions). Streamable-HTTP transport, JSON responses:
POST /v1/mcp with JSON-RPC 2.0 (initialize, ping, tools/list, tools/call; notifications are accepted with 202).

Authentication and authorisation are the REST API's: a Bearer session and X-Tenant-Id on every request, and each
tool calls the REST handler with the caller's Principal (RLS + RBAC). The only state-changing tool,
`propose_action`, goes through the same governed proposal path as POST /v1/actions: catalogue validation,
AEP-X policy, approval rules (RSP-01..10) and audit. An assistant can propose; it cannot approve.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app.deps import Principal, tenant_principal
from app.routers import actions, endpoints, incidents

router = APIRouter(prefix="/v1", tags=["mcp"])
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


def _obj(props: dict, required: tuple = ()) -> dict:
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


TOOLS = [
    {"name": "list_incidents", "description": "List incidents in this tenant, newest first.",
     "inputSchema": _obj({"status": {"type": "string", "enum": ["open", "investigating", "contained", "recovering",
                                                                 "resolved"]},
                          "limit": {"type": "integer", "minimum": 1, "maximum": 500}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "get_incident", "description": "One incident with its timeline, investigations and recovery items.",
     "inputSchema": _obj({"incident_id": {"type": "string", "format": "uuid"}}, ("incident_id",)),
     "annotations": {"readOnlyHint": True}},
    {"name": "list_alerts", "description": "List alerts, optionally filtered by status or severity.",
     "inputSchema": _obj({"status": {"type": "string"}, "severity": {"type": "string"},
                          "limit": {"type": "integer", "minimum": 1, "maximum": 500}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "list_devices", "description": "Device inventory with health issues (stale definitions, disabled sensors).",
     "inputSchema": _obj({"limit": {"type": "integer", "minimum": 1, "maximum": 1000}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "propose_action",
     "description": "Propose a response action from the catalogue (e.g. isolate_device, quarantine_file). It is "
                    "evaluated by AEP-X policy and usually waits for human approval in the console.",
     "inputSchema": _obj({"action_type": {"type": "string"},
                          "targets": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 100},
                          "params": {"type": "object"}, "reason": {"type": "string", "maxLength": 2000},
                          "incident_id": {"type": "string", "format": "uuid"}},
                         ("action_type", "targets", "reason")),
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
]


def _call(name: str, args: dict, p: Principal):
    lim = args.get("limit")
    if name == "list_incidents":
        p.require("incidents.read")
        return incidents.list_incidents(status=args.get("status"), limit=lim or 100, offset=0, p=p)
    if name == "get_incident":
        p.require("incidents.read")
        return incidents.get_incident(UUID(args["incident_id"]), p=p)
    if name == "list_alerts":
        return incidents.list_alerts(status=args.get("status"), severity=args.get("severity"), limit=lim or 100,
                                     offset=0, p=p)
    if name == "list_devices":
        return endpoints.devices(limit=lim or 200, offset=0, p=p)
    if name == "propose_action":
        p.require("actions.propose")
        body = actions.ProposeIn(action_type=args["action_type"], targets=args["targets"],
                                 params=args.get("params") or {}, reason=f"[via MCP] {args['reason']}",
                                 incident_id=args.get("incident_id"))
        return actions.propose_action(body, p=p)
    raise KeyError(name)


def _result(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid, code: int, message: str):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _handle(msg: dict, p: Principal):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
    rid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if rid is None:                       # notification (e.g. notifications/initialized): no response
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        from app.main import app
        return _result(rid, {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                             "capabilities": {"tools": {"listChanged": False}},
                             "serverInfo": {"name": "agentic-antivirus", "version": app.version},
                             "instructions": "Security operations tools for one tenant. Read freely; actions are "
                                             "proposals that humans approve in the console."})
    if method == "ping":
        return _result(rid, {})
    if method == "tools/list":
        return _result(rid, {"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS}:
            return _error(rid, -32602, f"unknown tool {name}")
        try:
            out = _call(name, args, p)
            return _result(rid, {"content": [{"type": "text", "text": json.dumps(out, default=str)}],
                                 "structuredContent": json.loads(json.dumps({"result": out}, default=str)),
                                 "isError": False})
        except HTTPException as exc:      # permission denied, not found, policy refusal: a tool-level error
            return _result(rid, {"content": [{"type": "text", "text": f"{exc.status_code}: {exc.detail}"}],
                                 "isError": True})
        except (KeyError, ValueError, ValidationError) as exc:
            return _error(rid, -32602, f"invalid arguments: {exc}")
    return _error(rid, -32601, f"method not found: {method}")


@router.post("/mcp")
async def mcp(request: Request, p: Principal = Depends(tenant_principal)):
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "parse error"), status_code=400)
    from starlette.concurrency import run_in_threadpool
    if isinstance(payload, list):
        out = [r for r in [await run_in_threadpool(_handle, m, p) for m in payload] if r is not None]
        return JSONResponse(out) if out else Response(status_code=202)
    res = await run_in_threadpool(_handle, payload, p)
    return JSONResponse(res) if res is not None else Response(status_code=202)


@router.get("/mcp")
def mcp_stream():
    # No server-initiated messages: the GET event stream is not offered (spec: 405).
    return Response(status_code=405, headers={"Allow": "POST"})
