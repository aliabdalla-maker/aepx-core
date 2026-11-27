"""INT-02 protocols beyond REST: GraphQL read API and the MCP server. Both reuse the REST handlers, so tenant
isolation, RBAC and the governed action path must hold exactly as they do over REST."""
import json

import pytest


@pytest.fixture(scope="module")
def org(new_account, enrol, baseline_bundle):
    admin = new_account("gql")
    dev = enrol(admin, hostname="gql-host-1")
    return admin, dev


def gql(acct, query, variables=None):
    r = acct.post("/v1/graphql", json={"query": query, "variables": variables})
    assert r.status_code == 200, r.text
    return r.json()


def test_graphql_reads_through_the_rest_rules(org, invite):
    admin, dev = org
    out = gql(admin, "{ me { email roles } devices { id hostname agent_version issues } incidents { id title } }")
    assert "errors" not in out, out
    assert out["data"]["me"]["roles"] == ["tenant_admin"]
    assert [d["hostname"] for d in out["data"]["devices"]] == ["gql-host-1"]
    user = invite(admin, "endpoint_user")
    mine = gql(user, "{ devices { hostname } }")
    assert mine["data"]["devices"] == []                       # endpoint users only see their own devices
    denied = gql(user, "{ incidents { id } }")
    assert denied["data"] is None and "403" in denied["errors"][0]["message"]


def test_graphql_has_no_mutations_and_limits_depth(org):
    admin, _ = org
    errs = gql(admin, "mutation { isolate(id: 1) }")["errors"]
    assert "not configured to execute mutation" in errs[0]["message"]
    deep = "{ incident(id: \"00000000-0000-0000-0000-000000000000\") { incident { id } } }"
    assert gql(admin, deep)["data"]["incident"] is None        # unknown id: null, not someone else's data
    nested = "query { me { " + "email " * 3 + "} }"
    assert "errors" not in gql(admin, nested)
    assert admin.post("/v1/graphql", json={"query": "{" * 20000}).status_code == 422   # size cap


def test_graphql_is_tenant_isolated(org, new_account):
    admin, _ = org
    other = new_account("gql-other")
    r = other.client.post("/v1/graphql", json={"query": "{ devices { id } }"},
                          headers={"Authorization": f"Bearer {other.token}", "X-Tenant-Id": admin.tenant_id})
    assert r.status_code == 404


def rpc(acct, method, params=None, rid=1):
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if rid is not None:
        msg["id"] = rid
    return acct.post("/v1/mcp", json=msg)


def test_mcp_initialize_list_and_read_tools(org):
    admin, dev = org
    init = rpc(admin, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "test", "version": "1"}}).json()
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["serverInfo"]["name"] == "agentic-antivirus"
    assert rpc(admin, "notifications/initialized", rid=None).status_code == 202
    tools = {t["name"]: t for t in rpc(admin, "tools/list").json()["result"]["tools"]}
    assert {"list_incidents", "get_incident", "list_alerts", "list_devices", "propose_action"} <= tools.keys()
    assert tools["list_devices"]["annotations"]["readOnlyHint"] is True
    res = rpc(admin, "tools/call", {"name": "list_devices", "arguments": {}}).json()["result"]
    assert res["isError"] is False
    assert [d["hostname"] for d in json.loads(res["content"][0]["text"])] == ["gql-host-1"]
    assert rpc(admin, "nope").json()["error"]["code"] == -32601
    assert rpc(admin, "tools/call", {"name": "drop_tables"}).json()["error"]["code"] == -32602
    assert admin.get("/v1/mcp").status_code == 405


def test_mcp_propose_action_is_governed_and_needs_permission(org, invite):
    admin, dev = org
    r = rpc(admin, "tools/call", {"name": "propose_action", "arguments": {
        "action_type": "isolate_device", "targets": [dev["device_id"]], "params": {"expires_minutes": 60},
        "reason": "lateral movement suspected"}}).json()["result"]
    assert r["isError"] is False, r
    body = json.loads(r["content"][0]["text"])
    assert body["status"] == "proposed"                         # S2 action waits for a human approval
    stored = [a for a in admin.get("/v1/actions").json() if a["id"] == body["id"]][0]
    assert stored["reason"].startswith("[via MCP]")
    user = invite(admin, "endpoint_user")
    denied = rpc(user, "tools/call", {"name": "propose_action", "arguments": {
        "action_type": "isolate_device", "targets": [dev["device_id"]], "params": {"expires_minutes": 60},
        "reason": "x"}}).json()["result"]
    assert denied["isError"] is True and denied["content"][0]["text"].startswith("403")


def test_mcp_requires_a_session(client):
    r = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
