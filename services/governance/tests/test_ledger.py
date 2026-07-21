from app import ledger


def test_merkle_root_empty_is_genesis():
    assert ledger.merkle_root([]) == ledger.GENESIS_HASH


def test_merkle_root_deterministic():
    hashes = ["a" * 64, "b" * 64, "c" * 64]
    assert ledger.merkle_root(hashes) == ledger.merkle_root(list(hashes))


def test_merkle_root_order_sensitive():
    assert ledger.merkle_root(["a" * 64, "b" * 64]) != ledger.merkle_root(["b" * 64, "a" * 64])


def test_event_hash_deterministic_and_sensitive_to_content():
    h1 = ledger.event_hash(1, "connector.invoked", {"agent_id": "x"})
    h2 = ledger.event_hash(1, "connector.invoked", {"agent_id": "x"})
    h3 = ledger.event_hash(1, "connector.invoked", {"agent_id": "y"})
    assert h1 == h2
    assert h1 != h3


def test_local_hash_chain_anchor_is_deterministic_and_chained():
    anchor = ledger.LocalHashChainAnchor()
    root = "d" * 64
    a1 = anchor.anchor(ledger.GENESIS_HASH, root)
    a2 = anchor.anchor(ledger.GENESIS_HASH, root)
    assert a1["anchor_hash"] == a2["anchor_hash"]  # deterministic given the same inputs
    assert a1["backend"] == "local-hashchain"
    assert a1["tx_ref"] is None

    a3 = anchor.anchor(a1["anchor_hash"], root)
    assert a3["anchor_hash"] != a1["anchor_hash"]  # chained to the previous anchor, not just the root


def test_evm_anchor_client_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("LEDGER_RPC_URL", raising=False)
    monkeypatch.delenv("LEDGER_CONTRACT_ADDRESS", raising=False)
    monkeypatch.delenv("LEDGER_PRIVATE_KEY", raising=False)
    client = ledger.EVMAnchorClient()
    assert client.configured() is False
    assert client.anchor("e" * 64) is None


def test_read_onchain_max_risk_level_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("LEDGER_RPC_URL", raising=False)
    monkeypatch.delenv("POLICY_CONTRACT_ADDRESS", raising=False)
    assert ledger.read_onchain_max_risk_level() is None


def test_policy_evaluate_unaffected_when_onchain_unconfigured(monkeypatch):
    # Zero behaviour change when the smart-contract policy path isn't
    # configured — the existing seed-policy tests must keep passing as-is.
    monkeypatch.delenv("LEDGER_RPC_URL", raising=False)
    monkeypatch.delenv("POLICY_CONTRACT_ADDRESS", raising=False)
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post("/policy/evaluate", params={"risk_level": "S1"})
    assert resp.json() == {"risk_level": "S1", "allowed": True, "max_risk_level": "S2"}


def test_anchoring_and_verify_against_the_in_memory_fallback():
    # No Postgres in the unit-test environment (mirrors
    # test_record_falls_back_to_memory_without_postgres in test_health.py)
    # — this drives enough events through _record to cross the anchor
    # batch threshold using the fallback lists, then checks /ledger/anchors
    # and /ledger/verify/{audit_id} against that fallback path.
    from fastapi.testclient import TestClient
    from app.main import app, _record, _AUDIT_FALLBACK, _LEDGER_FALLBACK

    client = TestClient(app)
    anchors_before = len(_LEDGER_FALLBACK)

    for i in range(30):
        _record("connector.invoked", {"i": i})

    anchors = client.get("/ledger/anchors").json()
    assert len(anchors) > anchors_before

    latest = max(anchors, key=lambda a: a["seq_no"])
    verified = client.get(f"/ledger/verify/{latest['last_audit_id']}").json()
    assert verified["anchored"] is True
    assert verified["chain_valid"] is True
    assert verified["anchor"]["seq_no"] == latest["seq_no"]

    unanchored_id = max(e["id"] for e in _AUDIT_FALLBACK) + 1_000_000
    not_found = client.get(f"/ledger/verify/{unanchored_id}").json()
    assert not_found == {"audit_id": unanchored_id, "anchored": False, "chain_valid": None, "anchor": None}


def test_verify_detects_tampering():
    # The actual tamper-evidence property: corrupt one historical
    # anchor_hash in place and confirm chain_valid flips to False for
    # every anchor from that point on — this must run last since it
    # deliberately corrupts shared fallback state for the rest of the
    # module's test session.
    from fastapi.testclient import TestClient
    from app.main import app, _record, _LEDGER_FALLBACK

    client = TestClient(app)
    for i in range(30):
        _record("connector.invoked", {"tamper-check": i})

    assert len(_LEDGER_FALLBACK) >= 1
    _LEDGER_FALLBACK[0]["anchor_hash"] = "0" * 64  # corrupt the earliest anchor

    latest = max(_LEDGER_FALLBACK, key=lambda a: a["seq_no"])
    verified = client.get(f"/ledger/verify/{latest['last_audit_id']}").json()
    assert verified["anchored"] is True
    assert verified["chain_valid"] is False
