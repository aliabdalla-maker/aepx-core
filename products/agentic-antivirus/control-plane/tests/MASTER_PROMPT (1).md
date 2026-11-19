# Reusable master development prompt

Act as a principal software architect, full-stack engineer, accessibility specialist, localization engineer, agentic AI engineer, security architect, DevOps engineer and QA lead.

Take the requirements in application.yaml and produce a traceable, functional, production-oriented application using https://github.com/aliabdalla-maker/aepx-core as the governed interoperability layer for agent-to-tool and agent-to-external-system operations.

1. Inspect the repository at a pinned SHA and verify AEP-X gateway, SDK, connector bus, identity, trust, governance, safety, verification, workflow, audit, and connector maturity. Reuse proven implementations; do not treat stubs as live adapters.
2. Generate a PRD, user stories, functional and nonfunctional acceptance criteria, threat model, architecture, data model, APIs, UX flows, accessibility specification and localized design system.
3. Implement cross-platform UI, authenticated backend, persistent data, role-based permissions, system settings, dashboards, file and folder CRUD, bulk import/export, file-type handlers, integrations and agent orchestration.
4. Provide 100 selectable locales from the catalog, tested text localization, pluralization, date/time/number formats, fallback chains, bidirectional and RTL layout, locale-specific search and accessibility. Do not claim all translations or voices work without coverage evidence.
5. Implement text-to-speech read-aloud and optional speech-to-text with consent, language/voice selection, pause/resume, speed, audio device selection, downloadable output only where licensed and supported, and accessible alternatives.
6. Implement a virtual file system with secure uploads, streaming downloads, directory traversal, rename, move, copy, trash, restore, versioning, retention, malware checks, MIME sniffing, quota enforcement, size limits, checksums and path traversal/symlink defenses. Unsupported formats remain opaque; preview/edit/conversion must be capability-gated.
7. Implement configurable integration endpoints for in-house and existing ecosystems, including REST/OpenAPI, GraphQL, gRPC, webhooks, MCP, OAuth/OIDC, SMTP/IMAP, SFTP, database adapters and message brokers. Use private network controls and approved credentials. Treat ports as configured network endpoints, not automatically exposed listeners.
8. Route every agent-driven external operation through the AEP-X governed path: authenticate, authorize, evaluate trust/policy, require HITL for high-risk operations, reserve budgets, execute through verified allowlisted adapters, verify, audit and reconcile. Fail closed on missing governance.
9. Build and test web/PWA, Android, iOS, Windows, macOS and Linux artifacts on appropriate build environments, signing only when credentials are available.
10. Implement GitHub Actions, Docker, dependency scans, SBOM, unit/integration/contract/E2E/accessibility/localization/security/performance tests, metrics and traceable evidence.
11. Restrict OCI deployment to verified Always Free eligible resources in the configured region, with no paid fallback. Produce an infrastructure plan but never apply without approval.
12. Add bounded recursive self-correction: observe, diagnose, patch on branch, regression test, security scan, request approval, and record verified learning. Never silently modify production or retrain on private data.
13. Deliver source code, reproducible builds, test reports, locale/voice coverage matrix, file-handler capability matrix, connector maturity matrix, signed packages where possible, dashboards, runbooks and release evidence. Mark each feature planned/implemented/tested/staging-verified/production-verified.

Do not merge, provision, deploy, or publish without explicit human approval.
