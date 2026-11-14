# AEP-X: GitHub-only development and validation

## Objective
Run all future code review, workflow validation, regression testing and evidence collection on GitHub, without requiring free disk space on the developer's Windows PC.

## Verified baseline (2026-11-14)
- PR #277 merged into `master` as `37ebb45e518f63496961eaabbbae405ea7d79832`.
- `aws-actions/configure-aws-credentials@v4` and `actions/github-script@v7` passed local `actionlint` on the two changed workflows.
- Recent GitHub Actions runs were queued; runner assignment and completion remain unverified.
- The local C: drive is full. Do not require local clone, Docker, Python, or PostgreSQL to proceed.

## GitHub-only workflow
1. Make source changes through a feature branch and draft pull request using the GitHub web editor, Codespaces (only if capacity permits), or a connected GitHub integration.
2. Open **Actions → AEP-X GitHub-only validation control plane → Run workflow**. It checks workflow syntax, evidence-gate tests and milestone-report consistency and records queue evidence. It never deploys.
3. Open **Actions → MCP disposable PostgreSQL acceptance → Run workflow** to test against the job's disposable PostgreSQL 16 service.
4. Open **Actions → HITL P0 acceptance → Run workflow** to run offline and disposable PostgreSQL HITL tests.
5. Open **Actions → AEP-X release readiness → Run workflow** for the existing Docker-based release audit, once hosted runners are available.
6. Review all check conclusions and artifacts at the exact intended commit SHA. Queued, skipped, missing or failed required checks are **not passes**.
7. Require human approval before merging any security-sensitive change. Keep cloud deployment workflows manual and protected.

## Runner-queue blocker
If the diagnostic workflow itself remains queued, it cannot execute its diagnostic job. Use the GitHub Actions run page and repository Actions settings to inspect runner eligibility, policy, spending/billing restrictions and approval requirements. Compare with GitHub Status. Do not claim a root cause without evidence. Do not enable self-hosted runners on OCI or chargeable cloud resources as a workaround.

## Safety
- No workflow in this plan provisions OCI, AWS, OpenShift or production resources.
- Keep remote MCP execution, provider forwarding and production deployments disabled until separately authorized.
- Disposable PostgreSQL tests must use test-only credentials and a dedicated database.
- Do not force-merge or bypass required checks.
- Planning percentages are not test evidence.

## Remaining acceptance gates
- Hosted runner assignment and CI recovery.
- Complete offline workflow/evidence regression tests.
- MCP PostgreSQL RLS, race and cross-tenant negative tests.
- HITL identity, approvals, replay and reconciliation tests.
- Lease/budget recovery and duplicate billing tests.
- Release readiness and OCI Always Free staging review.
