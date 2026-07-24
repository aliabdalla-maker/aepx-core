# AEP-X Monetization Strategy

*Prepared 24 July 2026 · Equality Software Ltd / AEP-X Programme*

The architecture dictates the model: **open-core + governed-infrastructure**.
The free layer drives adoption and protects the "vendor-neutral" credibility
central to the pitch; revenue comes from what enterprises can't or won't
self-run — **trust, compliance, scale, and support**. The through-line: *don't
monetize the protocol, monetize governance at scale.* Trust scoring,
compliance evidence, the marketplace publish gate, audit anchoring, and the
decision oracle are each cheap for us to run once and expensive for a customer
to build or self-operate. That asymmetry is the durable margin.

---

## The five revenue lines

### 1. Open-core licensing — the wedge
- **Free / OSS core**: protocol, SDK, the 16 services, Connector Bus, the
  self-hosted stack, and the AEP-X Console. Drives adoption and credibility.
- **Enterprise Edition** (paid): SSO/SAML, multi-tenant, HA, the compliance
  packs (ISO 27001/42001, SOC 2, EU AI Act evidence), and priority support.
  Biggest near-term line; no infrastructure for us to run.

### 2. Managed cloud — recurring, highest long-term margin
Host the governed platform so customers don't run 16 services + Kafka + a chain.
- **Usage-based**: per governed execution / per active agent / per GB of
  memory + cache.
- The platform's **cache-first economics are the margin engine** — we bill for
  outcomes while our cost floor stays low (the 80% LLM-reduction story both
  sells the product *and* protects our COGS).

### 3. Marketplace take-rate — the rails already exist
The Marketplace Engine's **governed publish gate** (trust ≥ 60 AND policy
allow, fail-closed) makes "vetted, governed agents" a premium buyers pay for.
A transaction business that scales with the ecosystem, not headcount.
- Default split: **Creator 90% / Platform 5% / Foundation 5%**.

### 4. Certification & training — high-margin, brand-building
- Developer certification: 5 levels, **£150–£1,500 / exam**.
- Organisation certification: **£2,500–£25,000**.
- Bootcamps: **£500–£5,000 / learner**.
- Doubles as a talent funnel and adoption driver.

### 5. Blockchain / bridge lines — the newest moat (RFC-0008)
Monetization nobody else combines:
- **Oracle-as-a-service** — metered per on-chain decision fulfilled
  (evidence-scored AI answers written to contracts). A real product for
  on-chain protocols needing trustworthy AI inputs.
- **Governed contract execution** — enterprises pay for auditable,
  policy-gated agent→chain actions; the trust + policy + audit wrapper is the
  value, not the RPC.
- **Compliance anchoring** — the tamper-evident audit ledger sold to regulated
  firms needing provable audit trails.

---

## Pricing (indicative)

| Product | Model | Indicative price |
|---|---|---|
| Community / OSS core | Free | £0 |
| Professional (managed) | Subscription | £99–£499 / month |
| Enterprise Edition | Annual contract | £25k–£250k / year |
| Managed cloud — usage | Metered | per execution / agent / GB |
| Marketplace | Take-rate | 10% platform+foundation (Creator 90%) |
| Certification | Per exam | £150–£1,500 (org £2.5k–£25k) |
| Training / bootcamps | Per learner | £500–£5,000 |
| Oracle-as-a-service | Metered | per on-chain decision fulfilled |

---

## Sequencing (mapped to funding stages)

| Stage | Lead revenue | Rationale |
|---|---|---|
| **Now → Yr 1** | Enterprise Edition + certification | Fastest cash, nothing to host; grants (Innovate UK/UKRI) bridge the gap |
| **Yr 1–2** | Managed cloud (usage) | Recurring base once pilots convert |
| **Yr 2–3** | Marketplace take-rate | Compounds as the ecosystem grows |
| **Yr 3+** | Oracle / bridge metered + compliance anchoring | Highest moat; follows on-chain adoption |

Revenue targets align with the ADLC Plan (§13): £100k ARR (Yr 1) → £500k–£1M
(Yr 2) → £2M (Yr 3) → £10M+ (Yr 5).

---

## Payment processing

Payments run through **`services/billing`** — Stripe-hosted Checkout Sessions
created via the Stripe REST API. Two safety invariants: the secret key is read
only from the `STRIPE_API_KEY` environment variable (never in the repo or git
history — supply it via a secrets manager at deploy time), and card data never
touches AEP-X (the customer pays on Stripe's hosted page, which also honours
Law 6 — human approval for financial decisions). Unset key ⇒ the service
degrades cleanly and never attempts a charge.

## The honest caveat

The binding risk is **adoption, not architecture** (ADLC Plan Critical
Evaluation §15). Every line above needs a user base first. So the practical
near-term priority is **Enterprise Edition + certification** — revenue that
doesn't require scale — while the **free OSS core and Console build the
funnel**. Monetize the marketplace and oracle lines only once the ecosystem
and on-chain adoption are real; pricing them before demand exists is the same
"build-ahead-of-adoption" trap the Critical Evaluation warned against.

---

*Related: [ADLC-Plan](ADLC-Plan.md) §13 (commercial milestones), [Handoff](Handoff.html) (scope &amp; funding), [Connector-Catalogue](Connector-Catalogue.md), [Console-and-Bridge](Console-and-Bridge.md).*
