from aepx import AepxClient
from aepx.conformance import CHECKS, run_conformance

DID = "did:key:z6MkTESTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
DOC = {"id": DID, "verificationMethod": []}


def _wire_conformant_deployment(fake_api):
    """Fake a fully RFC-conformant deployment for every check."""
    def _bus(path, kwargs):
        name = kwargs["json"]["receiver"].rstrip("/").split("/")[-1]
        if name.startswith("not-a-connector"):
            return 404, {"detail": f"unknown connector '{name}' — not in catalogue"}
        return {"connector": name, "maturity": "specialized", "response": {}}

    fake_api.on("POST", "/bus/route", body_fn=_bus)
    fake_api.on("GET", "/trust/", body_fn=lambda path, kwargs: {
        "entity_id": path.split("/")[-1], "trust_score": 50, "level": "Provisional", "behaviour_score": 50})
    fake_api.on("POST", "/policy/evaluate", body_fn=lambda path, kwargs: {
        "risk_level": kwargs["params"]["risk_level"],
        "allowed": kwargs["params"]["risk_level"] in ("S0", "S1", "S2"),
        "max_risk_level": "S2"})
    fake_api.on("GET", "/audit", body=[{"topic": "connector.invoked", "event": {}}])
    fake_api.on("POST", "/did", body={"did": DID, "did_document": DOC, "private_key_hex": "ab" * 32})
    fake_api.on("GET", "/did/did:ethr", status=400, body={"detail": "unsupported DID method"})
    fake_api.on("GET", f"/did/{DID}", body=DOC)
    fake_api.on("GET", "/ledger/anchors", body=[{
        "seq_no": 1, "prev_hash": "0" * 64, "merkle_root": "aa", "anchor_hash": "bb", "last_audit_id": 20}])
    fake_api.on("GET", "/ledger/verify/20", body={"audit_id": 20, "anchored": True, "chain_valid": True})
    fake_api.on("GET", "/health", body={"identity": {"status": "ok"}, "trust": {"status": "ok"}})


def _fix_trust_adjust(fake_api):
    fake_api.on("POST", "/trust/", body_fn=lambda path, kwargs: {
        "entity_id": path.split("/")[-2], "behaviour_score": 60})


def test_fully_conformant_deployment_passes_every_check(fake_api):
    _fix_trust_adjust(fake_api)
    _wire_conformant_deployment(fake_api)
    report = run_conformance(AepxClient())
    assert report.failed == 0, [r for r in report.results if r["status"] == "fail"]
    assert report.skipped == 0, [r for r in report.results if r["status"] == "skip"]
    assert report.passed == len(CHECKS)
    assert report.conformant is True


def test_unreachable_deployment_skips_never_raises(fake_api):
    # No routes wired at all — every network-touching check must SKIP.
    report = run_conformance(AepxClient())
    assert report.failed == 0
    assert report.skipped > 0
    # skips alone don't make a deployment conformant
    non_network_passes = report.passed  # envelope-shape check is offline and passes
    assert report.conformant is (report.failed == 0 and non_network_passes > 0)


def test_nonconformant_deployment_fails(fake_api):
    _fix_trust_adjust(fake_api)
    _wire_conformant_deployment(fake_api)
    # Break one normative behaviour: unknown connectors return 200
    fake_api.routes = [r for r in fake_api.routes if r[1] != "/bus/route"]
    fake_api.on("POST", "/bus/route", body={"connector": "anything-goes"})
    report = run_conformance(AepxClient(), ids=["core.unknown-connector"])
    assert report.failed == 1
    assert report.conformant is False


def test_ids_filter_limits_the_run(fake_api):
    _wire_conformant_deployment(fake_api)
    report = run_conformance(AepxClient(), ids=["core.envelope-shape"])
    assert len(report.results) == 1
    assert report.results[0]["id"] == "core.envelope-shape"
    assert report.passed == 1


def test_report_serialises(fake_api):
    _wire_conformant_deployment(fake_api)
    report = run_conformance(AepxClient(), ids=["core.envelope-shape"])
    d = report.to_dict()
    assert d["conformant"] is True
    assert d["results"][0]["status"] == "pass"
    assert "bus_url" in d["target"]
