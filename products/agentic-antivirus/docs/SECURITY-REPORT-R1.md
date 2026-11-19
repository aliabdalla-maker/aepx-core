# Security test report — Release 1 (DLV-07, RA-06)

Run 19 Nov 2026 on branch `fix/aav-console-desktop-scan` (PR #431).

| Check | Tool | Result |
|---|---|---|
| Static analysis, Python (4,844 LOC: control plane, agent, detection) | bandit | 0 high; 4 medium reviewed as false positives (below); 6 low |
| Python dependencies, control plane and agent | pip-audit | 0 known vulnerabilities |
| Web console production dependencies | npm audit --omit=dev | 0 vulnerabilities |
| Tenant isolation, RBAC, approvals, signed commands, prompt injection, SSRF | pytest (control plane) | 98 passed |
| Agent vault, signature pinning, isolation rules | pytest (agent) | 6 passed |
| Desktop window origin policy, agent bridge token/URL validation | node --test | 5 passed |
| Console, i18n, ads policy, voice | vitest | 17 passed |
| Accessibility (84 page/theme/locale checks) | axe gate | 0 serious or critical |

Medium findings reviewed:
- `actions.py:57`, `files.py:199`, `files.py:247` (B608): SQL text is assembled only from fixed allowlists (table map, validated
  sort column and direction); all values are bound parameters.
- `agent.py:271` (B108): the quick-scan path list includes the system TEMP folder on purpose (malware is commonly dropped there).

Not done: an independent penetration test. Proposed for Release 1 approval: accept the automated suite above for the beta and
commission an independent test before general availability.
