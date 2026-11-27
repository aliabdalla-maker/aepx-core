"""GraphQL read API (INT-02). POST /v1/graphql with {"query", "variables", "operationName"}.

Read-only by design: every resolver calls the same REST handler, with the caller's Principal, so tenant isolation
(RLS), RBAC and the endpoint-user "own devices only" rules are exactly those of the REST API. Changes (actions,
policies, isolation) stay on the governed REST/MCP proposal path with approvals; there are no mutations here.
Guards: query size, selection depth and list limits.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from graphql import (GraphQLError, ValidationRule, build_schema, graphql_sync, parse, specified_rules, validate)
from pydantic import BaseModel, Field

from app.deps import Principal, tenant_principal
from app.routers import endpoints, incidents

router = APIRouter(prefix="/v1", tags=["graphql"])

MAX_QUERY_CHARS = 10_000
MAX_DEPTH = 6

SDL = """
\"\"\"Agentic Antivirus read API. Field names match the REST resources.\"\"\"
type Query {
  me: Me!
  devices(limit: Int = 200): [Device!]!
  alerts(status: String, severity: String, limit: Int = 100): [Alert!]!
  incidents(status: String, limit: Int = 100): [Incident!]!
  incident(id: ID!): IncidentDetail
}
type Me { user_id: ID!, email: String!, tenant_id: ID!, roles: [String!]! }
type Device {
  id: ID!, hostname: String!, os: String, os_version: String, agent_version: String, criticality: String,
  policy_name: String, protection_status: String, isolation_state: String, definitions_version: String,
  last_seen_at: String, enrolled_at: String, issues: [String!]
}
type Alert {
  id: ID!, title: String!, severity: String!, status: String!, source: String, rule_id: String, technique: String,
  detected_at: String, hostname: String, incident_id: ID, action_taken: String
}
type Incident {
  id: ID!, title: String!, severity: String!, status: String!, category: String, created_at: String,
  updated_at: String, alert_count: Int
}
type IncidentDetail { incident: Incident!, timeline_json: String!, investigations_count: Int!, recovery_count: Int! }
"""
schema = build_schema(SDL)


def _plain(v):
    return json.loads(json.dumps(v, default=str))


class _Root:
    def __init__(self, p: Principal):
        self.p = p

    def me(self, _info):
        return _plain({"user_id": self.p.user_id, "email": self.p.email, "tenant_id": self.p.tenant_id,
                       "roles": sorted(self.p.roles)})

    def devices(self, _info, limit=200):
        return _plain(endpoints.devices(limit=max(1, min(limit, 1000)), offset=0, p=self.p))

    def alerts(self, _info, status=None, severity=None, limit=100):
        return _plain(incidents.list_alerts(status=status, severity=severity, limit=max(1, min(limit, 500)),
                                            offset=0, p=self.p))

    def incidents(self, _info, status=None, limit=100):
        self.p.require("incidents.read")
        return _plain(incidents.list_incidents(status=status, limit=max(1, min(limit, 500)), offset=0, p=self.p))

    def incident(self, _info, id):
        self.p.require("incidents.read")
        try:
            d = incidents.get_incident(UUID(id), p=self.p)
        except (ValueError, HTTPException):
            return None
        d = _plain(d)
        return {"incident": d["incident"], "timeline_json": json.dumps(d["timeline"]),
                "investigations_count": len(d["investigations"]), "recovery_count": len(d["recovery"])}


class _DepthLimit(ValidationRule):
    def enter_operation_definition(self, node, *_):
        def depth(sel_set, d):
            if not sel_set:
                return d
            return max((depth(getattr(s, "selection_set", None), d + 1) for s in sel_set.selections), default=d)
        if depth(node.selection_set, 0) > MAX_DEPTH:
            self.report_error(GraphQLError(f"query depth exceeds {MAX_DEPTH}", node))


class GraphQLIn(BaseModel):
    query: str = Field(max_length=MAX_QUERY_CHARS)
    variables: dict | None = None
    operationName: str | None = None


@router.post("/graphql")
def graphql_endpoint(body: GraphQLIn, p: Principal = Depends(tenant_principal)):
    try:
        doc = parse(body.query)
    except GraphQLError as exc:
        return {"errors": [{"message": exc.message}]}
    errors = validate(schema, doc, [*specified_rules, _DepthLimit])
    if errors:
        return {"errors": [{"message": e.message} for e in errors]}
    res = graphql_sync(schema, body.query, root_value=_Root(p), variable_values=body.variables,
                       operation_name=body.operationName)
    out: dict = {"data": res.data}
    if res.errors:
        out["errors"] = [{"message": _message(e), "path": e.path} for e in res.errors]
    return out


def _message(e: GraphQLError) -> str:
    orig = e.original_error
    if isinstance(orig, HTTPException):
        return f"{orig.status_code}: {orig.detail}"
    return e.message
