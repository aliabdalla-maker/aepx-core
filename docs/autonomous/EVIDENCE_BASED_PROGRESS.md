# Evidence-based AEP-X progression

The previous repeated **77%** figure was a subjective estimate and must not be presented as measured completion. Use `python scripts/aepx_progress_tracker.py docs/autonomous/AEPX_PROGRESS_BASELINE.json` to compute a reproducible weighted score.

Weights: architecture 10, core application 15, security 20, PostgreSQL execution 15, Docker/OCI 10, autonomous engineering 15, CI/observability 10, scale/recovery 5 (total 100).

Each milestone has one of four states: `not_started` (0% of weight), `code_committed` (25%), `tests_verified` (70%), `accepted` (100%). Nonzero states require explicit evidence strings; this tool **does not validate evidence authenticity**. An independent reviewer must inspect PRs, passing CI runs, acceptance logs and trusted deployment receipts before changing the baseline. The initial manifest intentionally records **zero verified claims**, not that zero code exists. Treat this as **0% independently substantiated milestone credit**, not 0% engineering work.

## Immediate gates

1. Review draft PRs and GitHub Actions status, unblock queued runners (issue #279), and record exact run URLs and results.
2. Run guarded PostgreSQL RLS, grants, approval, nonce and concurrent transaction acceptance in disposable local staging; attach results.
3. Run opt-in Docker nonroot/read-only/network-isolation runtime acceptance; attach logs.
4. Implement OIDC-authenticated trusted controller, tenant membership, least-privilege DB grants and atomic approval+completion.
5. Demonstrate ten successful supervised engineering iterations, then 100, then 1,000 and 10,000 with budgets, immutable evidence and recovery tests.

No external provider calls, migrations, deployments, paid OCI resources or production permissions are changed by this tracker.

## Claimed versus independently verified progress

The CLI now emits `claimed_progress_percent` separately from `independently_verified_percent` (currently fixed at zero because this offline calculator does not authenticate evidence). For backward compatibility `progress_percent` still means **claimed**, not verified, progress. Even a manifest with every milestone marked `accepted` and arbitrary evidence strings must report zero independently verified credit. Never present `progress_percent` alone as real completion.

**Next implementation gate:** build a verifier for GitHub commit SHA and completed successful CI run identifiers, then validate signed or independently reviewed PostgreSQL/Docker acceptance artifacts. Only after these checks should the verified score become nonzero. No automatic approval is inferred from PR merge.
