# AEP-X Arabic Accessibility — FDE ADLC + SDLC Project Cycle

**Programme:** AEP-X Arabic Accessibility
**Repository:** `aliabdalla-maker/aepx-core`
**Delivery model:** Forward Deployed Engineering (FDE)
**Lifecycle:** Agentic Development Life Cycle (ADLC) + Software Development Life Cycle (SDLC)
**Primary locale:** Arabic (`ar`), with Modern Standard Arabic as the default written form
**Directionality:** RTL-first for Arabic, preserving LTR for code, identifiers, URLs, hashes, addresses, and protocol payloads
**Status:** Implementation baseline

---

## 1. Mission

Make AEP-X usable, understandable, testable, operable, and supportable by Arabic-speaking users without forking the protocol or weakening its governance, evidence, trust, safety, audit, or interoperability guarantees.

This is not a label-translation exercise. The programme must cover:

- Arabic UI and RTL behaviour across AEP-X Console, Workbench, Conformance UI, and focused console surfaces.
- Arabic agent input/output and bidirectional-text safety.
- Arabic documentation and operator guidance.
- Arabic-aware search, memory, knowledge retrieval, verification, and evidence display.
- Locale-safe APIs, schemas, SDKs, CLI output, telemetry, audit, and error messages.
- Accessibility, keyboard navigation, screen-reader semantics, and legible Arabic typography.
- Conformance tests proving Arabic support without breaking existing English behaviour.

## 2. FDE operating model

The FDE owns the full loop from field discovery to production evidence. Each deployment cycle runs:

`Discover → Baseline → Specify → Design → Build → Integrate → Validate → Deploy → Observe → Learn → Standardise`

The FDE must work against the running AEP-X system, not a detached translation branch. Arabic support is treated as a cross-cutting platform capability.

### FDE responsibilities

1. Shadow real Arabic-speaking users and operators.
2. Convert field friction into executable acceptance criteria.
3. Trace each requirement to repository components and tests.
4. Ship thin vertical slices to staging quickly.
5. Measure task completion, UI defects, model quality, and operational failures.
6. Feed proven changes back into RFCs, schemas, SDK conventions, and reusable components.

## 3. Combined ADLC + SDLC stage map

| Stage | ADLC purpose | SDLC activity | FDE field outcome | Exit gate |
|---|---|---|---|---|
| 0. Mobilise | Define mission and constraints | Repository/environment setup | Named users, use cases, owners | Programme charter approved |
| 1. Discover | Understand Arabic user needs | Requirements elicitation | Field journeys and pain points | Discovery baseline accepted |
| 2. Specify | Formalise desired behaviour | BRD/FR/NFR + acceptance criteria | Arabic backlog with measurable outcomes | Requirements freeze v1 |
| 3. Design | Define multilingual architecture | UX, i18n, data, API, security design | RTL prototypes and architecture decisions | Architecture gate |
| 4. Build | Implement agentic + software changes | Coding, content, translation resources | Working Arabic vertical slices | Feature-complete gate |
| 5. Integrate | Join platform layers | API/SDK/UI/service integration | End-to-end Arabic journeys | Integration gate |
| 6. Validate | Prove quality and safety | Functional, accessibility, security, LLM evals | Evidence-backed readiness | Release candidate gate |
| 7. Deploy | Controlled release | CI/CD, rollout, rollback | Arabic pilot in target environment | Pilot acceptance |
| 8. Operate | Run and support | SRE/monitoring/support | Stable Arabic production service | SLO gate |
| 9. Learn | Improve from evidence | Retrospective, analytics, defect learning | Prioritised improvements | Learning review |
| 10. Standardise | Make capability reusable | RFC/docs/conformance updates | Arabic becomes platform capability | GA / standardisation gate |

## 4. Stage 0 — Mobilise

### Objectives

- Confirm Arabic accessibility as a supported platform capability.
- Identify target personas and Arabic-speaking pilot users.
- Establish branch, environments, owners, metrics, and change-control model.

### Deliverables

- Programme charter.
- RACI for Product, FDE, UX, Arabic linguist/reviewer, Backend, Frontend, QA, Security, DevOps.
- Arabic glossary owner.
- Target environments: local → CI → staging → pilot → production.
- Initial risk register.

### Initial personas

- Arabic-speaking developer integrating AEP-X.
- Arabic-speaking operator monitoring health, governance, trust, and workflows.
- Arabic-speaking business user interacting with agents.
- Bilingual administrator switching between Arabic and English.

### Gate 0

Proceed only when pilot users, target journeys, and owners are named.

## 5. Stage 1 — Discover

### Field discovery questions

- Can a first-time Arabic user understand the console without English assistance?
- Do navigation, tables, cards, timelines, logs, forms, and dialogs remain coherent in RTL?
- Are code, JSON, DIDs, hashes, URLs, smart-contract addresses, and trace IDs displayed safely inside RTL pages?
- Can Arabic queries pass through Gateway → Memory/Knowledge → Workflow → Safety → Verification without corruption?
- Are Arabic evidence citations understandable and attributable?
- Can a user switch language without losing session or task state?
- Are mixed Arabic/English technical terms readable?

### Discovery artefacts

- Current-state screen inventory.
- English hard-coded string inventory.
- CSS physical-direction inventory (`left`, `right`, `margin-left`, etc.).
- API/user-facing error inventory.
- Arabic model and embedding capability inventory.
- Documentation inventory.
- User journey baseline with completion time and failure count.

### Baseline metrics

Capture before implementation:

- Arabic journey completion rate.
- RTL visual defect count per page.
- Untranslated-string rate.
- Arabic response usefulness score.
- Arabic citation/evidence correctness.
- Accessibility violations.
- P95 latency delta for Arabic vs English.
- Token/cost delta for equivalent Arabic vs English tasks.

## 6. Stage 2 — Specify

### Functional requirements

**AR-FR-001 Locale selection** — User can select Arabic or English; preference persists per supported session/profile mechanism.

**AR-FR-002 Document direction** — Arabic mode sets `lang="ar"` and `dir="rtl"` at the document/application root. English remains `lang="en"`, `dir="ltr"`.

**AR-FR-003 RTL layout** — Navigation, panels, forms, chat bubbles, tables, dialogs, pagination, icons, and flows mirror appropriately.

**AR-FR-004 Bidi isolation** — Code, JSON, DIDs, UUIDs, URLs, emails, hashes, IPs, model names, connector IDs, contract addresses, CLI commands, and trace IDs remain LTR using explicit isolation.

**AR-FR-005 Translation catalogue** — User-facing strings are removed from hard-coded templates and resolved through locale resources.

**AR-FR-006 Arabic input** — Text entry, search, chat, workflows, connector parameters, and file metadata accept Unicode Arabic correctly.

**AR-FR-007 Arabic output** — Agent responses can be generated and rendered in Arabic while preserving evidence, confidence, cost, trust, and audit metadata.

**AR-FR-008 Mixed-language content** — Arabic sentences containing English technical terms remain visually stable and copyable.

**AR-FR-009 Arabic evidence** — Citations and verification evidence retain source identity and display direction safely.

**AR-FR-010 Arabic docs** — Getting started, operator quick-start, and key concepts are available in Arabic.

**AR-FR-011 Arabic CLI ergonomics** — CLI accepts Arabic payloads/filenames; machine-readable output remains locale-independent.

**AR-FR-012 Search/retrieval** — Arabic content can be indexed/retrieved with measured relevance; normalization must not change source evidence.

**AR-FR-013 Accessibility** — Arabic mode remains keyboard navigable and screen-reader understandable.

### Non-functional requirements

- UTF-8 end-to-end.
- No locale-dependent protocol schema changes unless explicitly versioned.
- API field names remain stable English identifiers unless a future RFC changes them.
- No translation of cryptographic identifiers, policy codes, RFC IDs, or machine-consumed enums.
- Arabic UI must not regress existing English tests.
- WCAG 2.2 AA target for user-facing Arabic surfaces.
- Translation resource completeness target: 100% release-blocking strings.
- Zero known critical bidi spoofing defects.
- Arabic P95 latency target: no more than 15% regression from comparable English path unless model provider imposes unavoidable variance and it is documented.

## 7. Stage 3 — Design

### 7.1 Locale architecture

Create a platform convention:

```text
locales/
  en.json
  ar.json
```

or component-local equivalent where framework constraints require it. Keys are semantic and stable, for example:

```json
{
  "console.send": "Send",
  "console.attach": "Attach",
  "health.healthy": "Healthy"
}
```

Arabic:

```json
{
  "console.send": "إرسال",
  "console.attach": "إرفاق",
  "health.healthy": "سليم"
}
```

Do not use English source text itself as the translation key.

### 7.2 CSS direction strategy

Prefer logical properties:

- `margin-inline-start/end`
- `padding-inline-start/end`
- `border-inline-start/end`
- `inset-inline-start/end`
- `text-align: start/end`

Avoid introducing new physical `left/right` dependencies unless direction-neutral.

Use direction-sensitive rules only where semantics require them:

```css
:root[dir="rtl"] .directional-icon { transform: scaleX(-1); }
.bidi-ltr { direction:ltr; unicode-bidi:isolate; text-align:left; }
```

Do not mirror universally meaningful icons such as play, media logos, or branded assets without UX review.

### 7.3 Bidi security

Treat bidirectional text as a security boundary.

- Isolate machine identifiers.
- Escape untrusted content.
- Detect/review unexpected bidi control characters in code/configuration/user-visible identifiers.
- Never allow visual order to obscure the actual value of a command, URL, contract address, DID, hash, or policy identifier.
- Logs and audit exports should preserve canonical value plus safe display value if necessary.

### 7.4 Arabic language design

- Use Modern Standard Arabic for product UI and formal documentation.
- Preserve recognised technical acronyms where translation would reduce clarity: API, SDK, JSON, RFC, MCP, CI/CD.
- Maintain a bilingual glossary for AEP-X-specific concepts such as Trust, Governance, Evidence, Verification, Workflow, Connector, Agent, Memory, Cache, Audit.
- Avoid dialect-specific wording in core product UI unless a future locale such as `ar-EG` or `ar-SA` is deliberately introduced.

### 7.5 Agent/LLM behaviour

Add locale as presentation/context metadata, not as a reason to bypass safety or evidence rules.

Desired policy:

```text
If response_locale = ar:
  answer in clear Modern Standard Arabic;
  preserve source citations exactly;
  keep code/JSON/identifiers unchanged;
  translate explanatory prose, not protocol fields;
  apply the same evidence, verification, safety and governance thresholds.
```

### 7.6 Search and retrieval

Evaluate rather than assume Arabic retrieval quality. Test:

- Arabic diacritics/no diacritics.
- Alef variants.
- Arabic and Western numerals.
- English technical keywords inside Arabic queries.
- Morphological variants.
- Arabic source documents vs English source documents queried in Arabic.

Any normalization is for retrieval matching only; source evidence remains immutable.

## 8. Stage 4 — Build

### Workstream A — Core i18n foundation

- Add locale registry.
- Add Arabic resource catalogue.
- Add language switcher.
- Persist locale.
- Set root `lang` and `dir` dynamically.
- Introduce translation helper.

### Workstream B — Console RTL conversion

Target `console/static/index.html` first because it is a concentrated vertical slice.

- Replace hard-coded UI strings.
- Convert layout CSS to logical properties.
- Mirror appropriate panel/navigation flow.
- RTL-enable chat and composer.
- Isolate badges/IDs/model names.
- Add automated Arabic smoke test.

### Workstream C — Platform surfaces

Apply the same shared conventions to:

- `platform/aepx-console`
- `platform/workbench`
- `platform/conformance`
- any operator/developer portal surfaces added later.

### Workstream D — Backend/API

- Ensure UTF-8 request/response handling.
- Add optional locale metadata only where presentation generation needs it.
- Keep protocol enums and field names locale-neutral.
- Make user-facing error messages localisable at presentation boundaries.
- Add Arabic fixture payloads to services that process natural language.

### Workstream E — Agentic intelligence

- Arabic prompt/output evaluation set.
- Arabic evidence and hallucination benchmark.
- Arabic retrieval benchmark.
- Arabic safety-policy tests.
- Arabic tool-use/function-calling tests with English schema names.

### Workstream F — Documentation

Minimum Arabic docs for pilot:

- README Arabic landing page or `README.ar.md`.
- Arabic quick start.
- Arabic operator guide.
- Arabic glossary.
- Arabic troubleshooting guide.

Canonical technical RFCs may remain English initially, but summaries should be translated and normative status clearly marked.

## 9. Stage 5 — Integrate

### Required end-to-end journeys

1. Arabic user opens AEP-X Console in Arabic.
2. Health and navigation render RTL.
3. User asks an Arabic question.
4. Request passes through governed AEP-X path.
5. Memory/knowledge retrieval accepts Arabic.
6. Verification scores evidence identically to English policy.
7. Response returns in Arabic.
8. Citation/source identifiers remain intact.
9. Audit entry is generated.
10. User switches to English and sees the same state.

Additional journeys:

- Arabic file upload and filename.
- Arabic connector invocation description with English connector identifier.
- Arabic workflow name/description.
- Arabic query against English technical evidence.
- Mixed Arabic/English code troubleshooting.
- Blockchain address and JSON-RPC payload displayed inside Arabic UI.

## 10. Stage 6 — Validate

### 10.1 Test pyramid

**Unit**

- Translation key resolution.
- Locale fallback.
- Direction calculation.
- Bidi isolation helper.
- Arabic Unicode input/output.

**Component/UI**

- RTL screenshots or DOM assertions.
- Keyboard navigation.
- Focus order.
- Form alignment.
- Long Arabic labels.
- Mixed text.

**Integration**

- Arabic requests through natural-language services.
- Arabic evidence retrieval.
- Locale preservation across frontend/backend.

**E2E**

- Full Arabic user journeys.
- Language switching.
- Refresh/session persistence.

**Accessibility**

- Automated WCAG checks.
- Keyboard-only journey.
- Arabic screen-reader review by a native speaker where possible.

**Security**

- Bidi-control-character test set.
- HTML/script injection in Arabic content.
- Confusable/identifier rendering review.

**Agentic evaluation**

- Known-answer Arabic benchmark.
- Citation precision.
- Evidence coverage.
- Refusal/safety parity.
- Tool-call correctness.
- Translation fidelity of policy explanations.

### 10.2 Release-blocking thresholds

- 100% critical translation keys populated.
- 0 Sev-1/Sev-2 RTL defects.
- 0 critical bidi/security defects.
- 100% critical Arabic E2E journeys pass.
- No regression in existing CI suite.
- Arabic known-answer evidence coverage ≥ existing AEP-X release threshold.
- Native-speaker product review passed.

## 11. Stage 7 — Deploy

### Release sequence

`developer local → CI → integration environment → staging → Arabic pilot cohort → general availability`

Use a feature flag or locale availability flag during pilot.

### Rollback

Arabic capability must be independently disableable without rolling back protocol/data migrations. Do not couple initial Arabic rollout to irreversible schema changes.

### Deployment checklist

- Locale files included in image/package.
- Cache invalidation verified.
- CSP/security headers unchanged or strengthened.
- Health endpoints unaffected.
- Monitoring dashboards split by locale where useful.
- Rollback tested.

## 12. Stage 8 — Operate

### Arabic SLO dashboard

Track:

- Arabic request count.
- Arabic success/error rate.
- P50/P95 latency.
- Arabic model/tool failures.
- Arabic retrieval relevance sample.
- Verification/evidence confidence distribution.
- Untranslated-string telemetry if implemented.
- UI/client exceptions by locale.
- Cost per Arabic governed execution.

### Support runbook

Every Arabic incident should capture:

- locale,
- direction,
- browser/client,
- exact canonical identifier/payload,
- screenshot if visual,
- trace/correlation ID,
- whether defect reproduces in English,
- whether issue is translation, layout, retrieval, model, protocol, or connector-specific.

## 13. Stage 9 — Learn

Run a weekly FDE evidence review during pilot.

Questions:

- Which Arabic journeys fail most often?
- Which English assumptions still leak into UX?
- Where does Arabic cause retrieval/model degradation?
- Which translations confuse users?
- Which technical terms should remain bilingual?
- Are support cases concentrated in specific connectors or services?

Convert findings into backlog items with evidence, not anecdote.

## 14. Stage 10 — Standardise and GA

Arabic is considered a platform capability only when:

- Shared i18n primitives are reused across AEP-X surfaces.
- Arabic conformance tests run automatically in CI.
- Documentation states support boundaries.
- Locale conventions are included in contribution guidance.
- New user-facing features require localisation acceptance criteria.
- Bidi safety rules are part of secure coding guidance.
- A repeatable process exists for additional locales.

## 15. FDE backlog — implementation order

### Epic 1 — Arabic foundation

- AR-001: locale registry and `ar` support.
- AR-002: translation catalogue and fallback.
- AR-003: root `lang`/`dir` switching.
- AR-004: persistent locale selection.
- AR-005: bidi-safe component utility.

### Epic 2 — Console

- AR-010: extract console hard-coded strings.
- AR-011: convert physical CSS directions to logical properties.
- AR-012: RTL chat/composer.
- AR-013: RTL side panels and health UI.
- AR-014: mixed Arabic/English identifier rendering.
- AR-015: console Arabic tests.

### Epic 3 — Agentic path

- AR-020: locale propagation to presentation-generation path.
- AR-021: Arabic LLM prompt policy.
- AR-022: Arabic retrieval benchmark.
- AR-023: Arabic evidence/verification benchmark.
- AR-024: Arabic safety parity tests.

### Epic 4 — Platform UIs

- AR-030: `platform/aepx-console` localisation.
- AR-031: Workbench localisation.
- AR-032: Conformance localisation.

### Epic 5 — Developer experience

- AR-040: Arabic quick start.
- AR-041: Arabic glossary.
- AR-042: CLI Unicode and Arabic examples.
- AR-043: SDK Arabic examples.

### Epic 6 — CI and release

- AR-050: Arabic static translation completeness check.
- AR-051: RTL/browser smoke tests.
- AR-052: Arabic agentic evaluation job.
- AR-053: Arabic accessibility test job.
- AR-054: pilot release checklist and telemetry.

## 16. Suggested sprint plan

### Sprint 1 — Foundation and console vertical slice

- Locale registry.
- `en` + `ar` resource files.
- language switcher.
- root direction switch.
- console RTL conversion.
- bidi isolation.
- smoke tests.

**Demo:** Arabic user can operate core console chat without layout breakage.

### Sprint 2 — Agentic Arabic quality

- Locale-aware response behaviour.
- Arabic fixtures.
- retrieval/evidence benchmark.
- verification and safety parity.

**Demo:** Arabic question → governed Arabic answer with evidence.

### Sprint 3 — Whole-platform UX

- AEP-X Console, Workbench, Conformance surfaces.
- keyboard/accessibility work.
- bilingual glossary.

**Demo:** Arabic operator can navigate key platform tools.

### Sprint 4 — Pilot hardening

- performance.
- security/bidi tests.
- observability.
- Arabic docs.
- native-speaker UAT.

**Demo:** release-candidate Arabic pilot.

## 17. Definition of Done for every Arabic story

A story is not done until:

- English and Arabic paths both work.
- RTL/LTR has been tested.
- mixed technical text is safe.
- automated test added or updated.
- accessibility considered.
- telemetry/logging remains useful.
- no protocol identifier was translated accidentally.
- documentation/glossary updated if terminology changed.
- acceptance criteria demonstrated against a running environment.

## 18. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Literal translation produces poor technical Arabic | High | Native technical reviewer + glossary |
| RTL breaks existing layouts | High | Logical CSS properties + visual regression tests |
| Bidi text hides malicious identifiers | Critical | Explicit isolation + security tests |
| Arabic model quality differs by provider | High | Provider benchmark and governed fallback |
| Arabic retrieval has weak recall | High | Arabic evaluation dataset; measured normalization strategy |
| Translation drifts from product changes | Medium | CI completeness check and key-based resources |
| English-only operational messages remain | Medium | inventory + progressive extraction |
| Localisation changes protocol semantics | Critical | locale only at presentation/natural-language boundaries |

## 19. Success KPIs

Pilot target metrics:

- ≥95% Arabic task completion on defined critical journeys.
- 0 critical RTL/bidi defects.
- 100% critical UI translation coverage.
- ≥90% native-review terminology acceptance on first pilot review, improving thereafter.
- Arabic evidence/citation quality within 5 percentage points of equivalent English benchmark.
- Arabic P95 latency within the NFR target relative to English.
- No measurable regression in existing English CI/conformance.

## 20. Governance and change control

Changes that only affect presentation/localisation follow normal SDLC review.

Changes to any of the following require architecture/governance review:

- protocol schema,
- identity/trust semantics,
- risk classification,
- verification thresholds,
- audit canonical representation,
- connector contract,
- RFC normative language.

Arabic accessibility must never weaken the AEP-X constitutional requirements of identity, trust, evidence, governance, safety, or human authority.

## 21. Immediate repository actions

1. Add this programme document.
2. Open the Arabic accessibility epic and child issues from §15.
3. Implement Sprint 1 on a feature branch.
4. Add Arabic fixtures and CI checks.
5. Deploy a staging pilot.
6. Collect FDE user evidence.
7. Refine and standardise the multilingual capability for reuse by future locales.

---

**Outcome:** AEP-X should become Arabic-accessible as a governed platform capability, with Arabic and RTL treated as first-class engineering concerns across the ADLC and SDLC—not as an after-the-fact translation layer.
