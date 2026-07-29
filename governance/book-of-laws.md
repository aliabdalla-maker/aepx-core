# AEP-X Book of Laws v1.0

The ten constitutional laws, seeded verbatim from the source manual's "AEP-X Zero" section and already referenced throughout ADLC Plan §2. One paragraph of rationale per law, per Instructional Manual §1.4.

## Law 1 — Identity Before Interaction

Nothing participates in AEP-X without identity. Every agent, tool, user, and organisation is identified before it can send or receive a message. *Rationale: this is the precondition for every other law — trust, evidence, and audit are all meaningless without a stable identity to attach them to.*

## Law 2 — Trust Before Execution

No action executes without a trust evaluation. The AEP-X Connector Bus enforces this structurally (SOA-Architecture.md §3.1) rather than by convention. *Rationale: prevents a compromised or low-reputation agent from taking action before its trust score is checked, not after.*

## Law 3 — Evidence Before Assertion

Every claim requires evidence, a confidence score, and a verification status; an unevidenced assertion is a protocol violation, not a stylistic weakness. *Rationale: this is what makes "hallucination" a measurable, enforceable failure mode instead of a vague quality concern.*

## Law 4 — Knowledge Before Generation

Knowledge → Memory → Reasoning → Generation, never reversed. *Rationale: an agent should retrieve what's already known before generating something new — generation is expensive and error-prone; retrieval is cheap and verifiable.*

## Law 5 — Reuse Before Computation

Cache → Memory → Workflow → Tool → Inference, in that order. *Rationale: this is the platform's core economic law — the 80% LLM-cost-reduction target (ADLC Plan §9) is a direct consequence of enforcing this ordering, not a separate optimisation.*

## Law 6 — Human Authority

Final authority for Healthcare, Government, Finance, Education, and Safety-critical domains rests with a human, corresponding to Safety classes S3/S4. *Rationale: some decisions carry consequences no automated confidence score should be allowed to fully own.*

## Law 7 — Explainability

Every decision must be able to answer: why, how, based on what evidence, and what alternatives were considered. *Rationale: explainability is what turns an audit log from a record into an accountability mechanism.*

## Law 8 — Auditability

Every action generates a record of who, what, when, where, why, and outcome. Governance Engine enforces this by consuming every event topic unconditionally (Microservices-Implementation-Guide.html §4.2). *Rationale: audit coverage that depends on every service remembering to call an audit API is audit coverage that will eventually have gaps; a passive listener doesn't have that failure mode.*

## Law 9 — Learning

Every interaction produces Experience → Knowledge → Learning → Improvement. ML Integration Service exists to close this loop (Microservices-Architecture-v2.md §4.2). *Rationale: without a real learning loop, "the system gets smarter over time" is marketing, not architecture.*

## Law 10 — Evolution

Every component must support upgrade, adaptation, replacement, and retirement without breaking the whole. *Rationale: the database-per-service and independent-deployability rules (Microservices-Implementation-Guide.html §4.3) exist specifically to make this law enforceable rather than aspirational.*
