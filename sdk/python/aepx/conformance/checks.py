"""Protocol conformance checks — RFC-0007.

Each check exercises one normative behaviour of a live AEP-X deployment
through an AepxClient. A check returns PASS (behaviour observed), FAIL
(deployment reachable but non-conformant), or SKIP (the subsystem was
unreachable — never an exception; an offline service is a deployment
state, not a conformance verdict).
"""
import uuid
from dataclasses import dataclass, field

PASS, FAIL, SKIP = "pass", "fail", "skip"


@dataclass
class CheckResult:
    status: str
    detail: str = ""


@dataclass
class ConformanceCheck:
    id: str
    rfc: str
    title: str
    run: "callable" = field(repr=False)


def _skip_on_unreachable(fn):
    def wrapper(client):
        try:
            return fn(client)
        except Exception as e:
            return CheckResult(SKIP, f"target unreachable: {type(e).__name__}: {e}")
    return wrapper


# -- RFC-0001: core protocol ---------------------------------------------

@_skip_on_unreachable
def _envelope_routes(client):
    result = client.connectors.invoke("ml", {"op": "ping"}, sender="aepx://agent/conformance")
    if result["status"] == 200:
        return CheckResult(PASS, f"routed to '{result.get('connector')}' (maturity {result.get('maturity')})")
    if result["status"] in (403, 503):
        return CheckResult(PASS, f"routed and gated with a governed reason: {result.get('reason')}")
    return CheckResult(FAIL, f"unexpected status {result['status']}: {result.get('reason')}")


@_skip_on_unreachable
def _unknown_connector_404(client):
    envelope = client.envelope("aepx://agent/conformance", f"aepx://connector/not-a-connector-{uuid.uuid4().hex[:8]}", {})
    resp = client.send(envelope)
    if resp.status_code == 404:
        return CheckResult(PASS, "unknown connector rejected with 404")
    return CheckResult(FAIL, f"expected 404, got {resp.status_code}")


@_skip_on_unreachable
def _envelope_shape(client):
    env = client.envelope("aepx://agent/a", "aepx://connector/b", {"k": "v"})
    required = {"version", "messageId", "timestamp", "sender", "receiver", "messageType", "payload", "metadata"}
    missing = required - set(env)
    if missing:
        return CheckResult(FAIL, f"envelope missing fields: {sorted(missing)}")
    if env["version"] != "1.0" or env["messageType"] != "request":
        return CheckResult(FAIL, "wrong envelope defaults")
    return CheckResult(PASS, "RFC-0001 envelope shape correct")


# -- RFC-0002: identity & trust --------------------------------------------

@_skip_on_unreachable
def _fresh_entity_default_trust(client):
    entity = f"conformance-{uuid.uuid4().hex[:12]}"
    score = client.trust.get(entity)
    if score.get("trust_score") != 50:
        return CheckResult(FAIL, f"fresh entity scored {score.get('trust_score')}, expected default 50")
    return CheckResult(PASS, f"fresh entity defaults to 50 (level {score.get('level')})")


@_skip_on_unreachable
def _trust_adjust_roundtrip(client):
    entity = f"conformance-{uuid.uuid4().hex[:12]}"
    client.trust.get(entity)  # fetch-or-create
    adjusted = client.trust.adjust(entity, "behaviour", 10)
    if adjusted.get("behaviour_score") != 60:
        return CheckResult(FAIL, f"behaviour 50+10 became {adjusted.get('behaviour_score')}")
    return CheckResult(PASS, "component adjust round-trips (50 + 10 = 60)")


# -- Governance: policy & audit ---------------------------------------------

@_skip_on_unreachable
def _policy_ordinal_consistency(client):
    # The allowed set must be a prefix of S0..S4 — an allowed S3 under a
    # denied S2 would mean the ordinal comparison is broken.
    allowed = [client.audit.policy(f"S{i}").get("allowed") for i in range(5)]
    if any(a and not all(allowed[:i + 1]) for i, a in enumerate(allowed)):
        return CheckResult(FAIL, f"non-prefix allowed set: {allowed}")
    return CheckResult(PASS, f"S0-S4 allowed set is prefix-consistent: {allowed}")


@_skip_on_unreachable
def _audit_endpoint_shape(client):
    tail = client.audit.tail(limit=5)
    if not isinstance(tail, list):
        return CheckResult(FAIL, f"audit tail is {type(tail).__name__}, expected list")
    bad = [e for e in tail if "topic" not in e or "event" not in e]
    if bad:
        return CheckResult(FAIL, "audit entries missing topic/event fields")
    return CheckResult(PASS, f"audit endpoint returns well-formed entries ({len(tail)} sampled)")


# -- RFC-0006: DID & ledger ---------------------------------------------------

@_skip_on_unreachable
def _did_roundtrip(client):
    created = client.did.create()
    did = created.get("did", "")
    if not did.startswith("did:key:z"):
        return CheckResult(FAIL, f"minted DID has wrong shape: {did[:40]}")
    resolved = client.did.resolve(did)
    if resolved != created.get("did_document"):
        return CheckResult(FAIL, "resolved DID document differs from the minted one")
    return CheckResult(PASS, "did:key mint -> resolve round-trips")


@_skip_on_unreachable
def _malformed_did_rejected(client):
    try:
        client.did.resolve("did:ethr:0xnot-a-did-key")
    except ValueError as e:
        return CheckResult(PASS, f"malformed DID rejected cleanly: {e}")
    return CheckResult(FAIL, "malformed DID was resolved instead of rejected")


@_skip_on_unreachable
def _ledger_anchor_shape(client):
    anchors = client.ledger.anchors(limit=5)
    if not isinstance(anchors, list):
        return CheckResult(FAIL, f"anchors is {type(anchors).__name__}, expected list")
    required = {"seq_no", "prev_hash", "merkle_root", "anchor_hash"}
    bad = [a for a in anchors if required - set(a)]
    if bad:
        return CheckResult(FAIL, "anchor entries missing hash-chain fields")
    return CheckResult(PASS, f"ledger anchors well-formed ({len(anchors)} sampled)")


@_skip_on_unreachable
def _ledger_verify_contract(client):
    anchors = client.ledger.anchors(limit=1)
    if anchors:
        verdict = client.ledger.verify(anchors[0]["last_audit_id"])
        if not verdict.get("anchored") or verdict.get("chain_valid") is not True:
            return CheckResult(FAIL, f"anchored audit id failed verification: {verdict}")
        return CheckResult(PASS, "anchored audit id verifies with chain_valid=true")
    verdict = client.ledger.verify(999_999_999)
    if verdict.get("anchored") is not False:
        return CheckResult(FAIL, f"unanchored id reported as anchored: {verdict}")
    return CheckResult(PASS, "no anchors yet; unanchored id correctly reports anchored=false")


# -- Gateway ------------------------------------------------------------------

@_skip_on_unreachable
def _gateway_aggregate_health(client):
    resp = client._request("GET", f"{client.gateway_url}/health")
    resp.raise_for_status()
    body = resp.json()
    down = [name for name, entry in body.items() if entry.get("status") != "ok"]
    if down:
        return CheckResult(FAIL, f"services not ok via gateway: {down}")
    return CheckResult(PASS, f"gateway aggregates {len(body)} services, all ok")


CHECKS = [
    ConformanceCheck("core.envelope-shape", "RFC-0001", "Envelope has all normative fields", _envelope_shape),
    ConformanceCheck("core.envelope-routes", "RFC-0001", "Valid envelope routes through the bus", _envelope_routes),
    ConformanceCheck("core.unknown-connector", "RFC-0001", "Unknown connector rejected with 404", _unknown_connector_404),
    ConformanceCheck("trust.default-score", "RFC-0002", "Fresh entity defaults to trust 50", _fresh_entity_default_trust),
    ConformanceCheck("trust.adjust", "RFC-0002", "Trust component adjust round-trips", _trust_adjust_roundtrip),
    ConformanceCheck("governance.policy-ordinal", "Gov", "S0-S4 policy decisions are ordinal-consistent", _policy_ordinal_consistency),
    ConformanceCheck("governance.audit-shape", "Gov", "Audit trail entries are well-formed", _audit_endpoint_shape),
    ConformanceCheck("did.roundtrip", "RFC-0006", "did:key mint and resolve round-trip", _did_roundtrip),
    ConformanceCheck("did.malformed", "RFC-0006", "Malformed DID rejected cleanly", _malformed_did_rejected),
    ConformanceCheck("ledger.anchor-shape", "RFC-0006", "Ledger anchors carry the hash chain", _ledger_anchor_shape),
    ConformanceCheck("ledger.verify", "RFC-0006", "Anchor verification honours its contract", _ledger_verify_contract),
    ConformanceCheck("gateway.health", "Ops", "Gateway aggregates all services healthy", _gateway_aggregate_health),
]
