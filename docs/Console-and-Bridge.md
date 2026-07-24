# AEP-X Console & the AI ↔ Blockchain Bridge

Two related things shipped together (RFC-0008): a **single GUI over the whole
platform**, and a **bidirectional bridge between AI agents and blockchains**.
This doc is the operator's guide to both.

---

## 1. The AEP-X Console — one GUI for the whole platform

`platform/aepx-console` · **http://localhost:8083**

After `docker compose up --build`, the Console is the single pane of glass over
everything. It proxies through the SDK, so every action runs the same governed
path (trust → policy → audit) as any other client, and every action lands in a
**live audit feed** you can watch update.

| Section | What it does |
|---|---|
| **Overview** | Live health grid of all 18 services + platform stat tiles + the Ten Laws |
| **Connectors** | Browse the 107-connector catalogue; invoke any through the governed bus |
| **Trust & ID** | Trust-score lookup, mint/resolve `did:key`, register agents |
| **Memory & Flows** | Session memory write/read, capability discovery, run a workflow |
| **Blockchain** | Live node status (block / chain-ID / gas), governed contract read/write, the decision oracle, raw JSON-RPC console |
| **Governance** | Policy evaluation, ledger anchors + tamper-verify, the live audit trail |
| **Billing** | Check whether Stripe is configured; create a Checkout Session and open it |
| **Intelligence** | ML models/prediction and the Brain's self-healing status |
| **LLM Box** | Chat routed through the bus to the self-hosted `ml` connector |

Everything degrades cleanly: with services down or no chain configured, each
panel shows an honest "degraded / start the stack" state rather than breaking.

The three earlier focused GUIs remain: **LLM box** `:8080`, **Workbench**
`:8081`, **Conformance** `:8082`.

---

## 2. The bridge — both directions

### AI → chain (governed contract calls)
An agent reads or writes a smart contract as an ordinary connector call, so
trust + policy + audit apply to a signed transaction like any other call.

```python
from aepx import AepxClient
c = AepxClient()

# read a view function
c.chain.read(address, abi, "anchorCount", [])
# sign & send a state-changing call (needs EVM_PRIVATE_KEY on the connector)
c.chain.write(address, abi, "anchor", ["0x…32-byte-root…"])
```

With no chain/key configured, these return a clean `specialized_degraded`
result — never a 5xx — and the governance around the call still runs.

### chain → AI (the decision oracle)
`AEPXOracle.sol` emits `DecisionRequested`; the `services/oracle-bridge` service
watches for it, runs a **governed** AI call (bus → `ml`) plus a Verification
scoring pass, and writes the evidence-scored answer back on-chain via the
permissioned `fulfillDecision`. It also works fully off-chain:

```python
c.oracle.decide("Given a valid audit hash-chain, should settlement proceed?")
# -> {answer, confidence, band: GREEN|AMBER|RED|GREY, ai_source, ...}
```

Every bridge action is audited: Governance consumes the `oracle.requested` /
`oracle.fulfilled` topics, so it all appears in `GET /audit`.

---

## 3. Billing — Stripe payment processing

`services/billing` · proxied at Console **Billing** (`:8083`)

Creates Stripe-hosted **Checkout Sessions**. Two invariants, always:

- **The secret key never lives in the repo.** It's read only from the
  `STRIPE_API_KEY` environment variable at call time — set it locally in a
  git-ignored `.env` (see `.env.example`), or as a real secret in your
  deployment. Unset ⇒ the service returns `configured: false` and never
  attempts a charge — never a 5xx, never a live call.
- **AEP-X never handles card data.** The customer enters payment details on
  Stripe's hosted page; we only ever see the resulting session id and hosted
  URL. This also satisfies Law 6 (human approval for financial decisions) —
  a human completes the payment, the platform never moves funds on its own.

```bash
# .env (git-ignored) — copy from .env.example
STRIPE_API_KEY=sk_test_...   # or a scoped rk_live_... restricted key

docker compose up --build billing
curl -X POST http://localhost:8017/billing/checkout \
  -H "Content-Type: application/json" \
  -d '{"product":"AEP-X Professional","amount_minor":9900,"currency":"gbp"}'
# -> {"configured": true, "checkout_url": "https://checkout.stripe.com/...", "session_id": "cs_..."}
```

Or from the Console: **Billing → Create Checkout Session** — it shows the
session id and an "Open Stripe Checkout" link. **Check status** confirms a key
is configured without ever displaying it.

A **restricted key** (`rk_live_...`/`rk_test_...`) needs Checkout Session
write permission scoped on it in the Stripe Dashboard; a standard secret key
(`sk_...`) has full account access and should be preferred for anything beyond
read-only testing.

## 4. Live-chain mode (opt-in) — running the on-chain path for real

The default stack has **no chain**; the on-chain paths degrade cleanly. To run
them for real against a local EVM devnet:

```bash
# 1. start the anvil devnet
docker compose -f docker-compose.yml -f docker-compose.chain.yml up -d anvil

# 2. compile + deploy the three contracts, writing .env.chain
python scripts/deploy_contracts.py --rpc http://localhost:8545

# 3. bring the stack up wired to the chain
docker compose --env-file .env.chain \
  -f docker-compose.yml -f docker-compose.chain.yml up --build
```

Now the Console's **Blockchain** section shows a live node, `chain.write`
actually signs transactions, and the oracle writes answers back on-chain.

**Contracts** (reference sources in `governance/contracts/`):
`AEPXAnchor.sol` (audit-root anchoring), `AEPXPolicyRegistry.sol` (on-chain
risk ceiling), `AEPXOracle.sol` (request/fulfil decision oracle).

**Verified in CI:** the `contracts` job (`tests/test_contracts.py`) compiles all
three with solc 0.8.24 and exercises the request/fulfil, access-control,
anchor, and policy logic on an in-memory EVM — no Docker or anvil required.

---

## 5. SDK plugins

Built-in on every `AepxClient`: `did`, `connectors`, `trust`, `ledger`,
`audit`, **`chain`**, **`oracle`**. Third-party plugins load via the
`aepx.plugins` entry-point group (RFC-0007).
