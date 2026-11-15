# AEP-X IDE — implementation progress (unified protocol v5.0)

Formula: `progress = 100 × verified_weight / total_weight`, over the 23 weighted requirements in
[REQUIREMENTS.csv](REQUIREMENTS.csv) (total weight 83). Per the protocol, code written, unrun tests,
screenshots, and a passing build are **never** counted as verified.

| Measure (2026-11-15, branch `feat/p01-identity-ux`) | Weight | % |
|---|---|---|
| **Verified in production** | 1 / 83 | **1.2 %** |
| Verified (production + local integration evidence) | 3 / 83 | 3.6 % |
| Implemented and tested locally, awaiting deploy + production check | 33 / 83 | 39.8 % |
| Blocked on owner action | 8 / 83 | 9.6 % |
| Partial / not started | 39 / 83 | 47.0 % |

```
Production-verified  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   1.2 %
Locally implemented  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  39.8 %  (not counted as verified)
```

## By phase

| Phase | State |
|---|---|
| P00 Inventory & root cause | Done — see [DEFECTS.md](DEFECTS.md) |
| P01 Identity | Code + local Keycloak 26 verification done; Google and mail need owner credentials, then deploy |
| P02 Workspace UX | Signed-out welcome, Save hint, honest panel states done locally; launcher status labels not started |
| P03 CRUD/ACL/RLS adversarial | Existing ACL tests only |
| P04 Software IDE depth | Not started |
| P05 Provider reliability | Not started |
| P06 Specialist IDEs | Editors shipped in #409; signed-in production use unverified |
| P07 In-product plugin marketplace | Not started |
| P08 PWA / ops | Release SHA + drift label, Operations states done locally |
| P09 CI / release gates | Existing CI runs tests; production-evidence gate not started |

Nothing in this branch is merged or deployed. Merging and deploying need explicit owner approval.
