#!/usr/bin/env python3
"""Compile and deploy the AEP-X reference contracts (RFC-0006 / RFC-0008).

One tool, two uses:

  * As a library — `compile_contracts()` returns name -> {abi, bytecode};
    `deploy_all(w3, deployer, oracle_addr)` deploys the three contracts and
    returns their addresses. The contract integration test imports these.

  * As a CLI — `python scripts/deploy_contracts.py --rpc http://localhost:8545`
    deploys to a running chain (the anvil devnet from docker-compose.chain.yml)
    and writes governance/contracts/deployed-addresses.json plus a ready-to-source
    .env.chain, so the stack can be brought up wired to the chain. With no --rpc,
    it deploys to an in-memory EVM and just prints the addresses (a smoke test).

Kept dependency-light and opt-in: nothing in the default platform path imports
this, and the contracts still work purely as reference sources when no chain is
configured (the services degrade cleanly — RFC-0006 §3).
"""
import json
import os
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "governance" / "contracts"
CONTRACTS = ["AEPXAnchor", "AEPXPolicyRegistry", "AEPXOracle"]
SOLC_VERSION = "0.8.24"


def compile_contracts() -> dict:
    """Compile every .sol contract; return {name: {"abi", "bytecode"}}."""
    import solcx
    if SOLC_VERSION not in [str(v) for v in solcx.get_installed_solc_versions()]:
        solcx.install_solc(SOLC_VERSION)
    sources = {c: {"content": (CONTRACTS_DIR / f"{c}.sol").read_text(encoding="utf-8")} for c in CONTRACTS}
    compiled = solcx.compile_standard(
        {
            "language": "Solidity",
            "sources": {f"{c}.sol": sources[c] for c in CONTRACTS},
            "settings": {"outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}},
        },
        solc_version=SOLC_VERSION,
    )
    out = {}
    for c in CONTRACTS:
        art = compiled["contracts"][f"{c}.sol"][c]
        out[c] = {"abi": art["abi"], "bytecode": art["evm"]["bytecode"]["object"]}
    return out


def _deploy_one(w3, deployer, artifact, *args):
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx_hash = contract.constructor(*args).transact({"from": deployer})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.contractAddress


def deploy_all(w3, deployer: str, oracle_addr: str | None = None) -> dict:
    """Deploy the three contracts. `oracle_addr` is the account allowed to
    fulfil oracle requests (defaults to the deployer)."""
    art = compile_contracts()
    oracle_addr = oracle_addr or deployer
    anchor = _deploy_one(w3, deployer, art["AEPXAnchor"])
    # Seed the on-chain ceiling to S2 (index 2), matching Governance's
    # in-process _POLICIES["max_risk_level"] default so behaviour is
    # identical whether or not the chain is wired in.
    policy = _deploy_one(w3, deployer, art["AEPXPolicyRegistry"], 2)
    oracle = _deploy_one(w3, deployer, art["AEPXOracle"], oracle_addr)
    return {"AEPXAnchor": anchor, "AEPXPolicyRegistry": policy, "AEPXOracle": oracle}


def _env_lines(addrs: dict, rpc_url: str, private_key: str) -> str:
    return "\n".join([
        f"LEDGER_RPC_URL={rpc_url}",
        f"LEDGER_CONTRACT_ADDRESS={addrs['AEPXAnchor']}",
        f"POLICY_CONTRACT_ADDRESS={addrs['AEPXPolicyRegistry']}",
        f"LEDGER_PRIVATE_KEY={private_key}",
        f"ORACLE_RPC_URL={rpc_url}",
        f"ORACLE_CONTRACT_ADDRESS={addrs['AEPXOracle']}",
        f"ORACLE_PRIVATE_KEY={private_key}",
        f"EVM_RPC_URL={rpc_url}",
        f"EVM_PRIVATE_KEY={private_key}",
        "",
    ])


def main():
    import argparse
    from web3 import Web3

    p = argparse.ArgumentParser(description="Deploy AEP-X reference contracts.")
    p.add_argument("--rpc", help="EVM JSON-RPC URL (e.g. http://localhost:8545). Omit for in-memory smoke test.")
    p.add_argument("--private-key", default=os.getenv("DEPLOYER_PRIVATE_KEY"),
                   help="Deployer key (anvil account #0 default is well-known).")
    args = p.parse_args()

    if not args.rpc:
        from web3.providers.eth_tester import EthereumTesterProvider
        w3 = Web3(EthereumTesterProvider())
        addrs = deploy_all(w3, w3.eth.accounts[0])
        print("In-memory deploy OK:", json.dumps(addrs, indent=2))
        return

    # anvil's deterministic account #0
    key = args.private_key or "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 15}))
    acct = w3.eth.account.from_key(key)
    # eth-account keys need manual signing; use a middleware-free raw path
    from web3.middleware import SignAndSendRawMiddlewareBuilder
    w3.middleware_onion.inject(SignAndSendRawMiddlewareBuilder.build(acct), layer=0)
    w3.eth.default_account = acct.address

    addrs = deploy_all(w3, acct.address)
    (CONTRACTS_DIR / "deployed-addresses.json").write_text(json.dumps(addrs, indent=2), encoding="utf-8")
    env_path = Path(__file__).resolve().parents[1] / ".env.chain"
    env_path.write_text(_env_lines(addrs, args.rpc, key), encoding="utf-8")
    print("Deployed to", args.rpc)
    print(json.dumps(addrs, indent=2))
    print(f"\nWrote {env_path.name} — bring the stack up wired to the chain with:\n"
          f"  docker compose --env-file .env.chain -f docker-compose.yml -f docker-compose.chain.yml up --build")


if __name__ == "__main__":
    main()
