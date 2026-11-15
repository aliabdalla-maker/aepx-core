---
name: aepx-ide
description: Use the AEP-X Universal Agentic IDE (ide.softwareequality.com) API — create projects in its nine IDE modules, run approval-gated agent crews, read and restore file versions, manage members and roles, and check the audit trail. Use when the user mentions AEP-X IDE projects, modules or agent runs.
---

# AEP-X Universal Agentic IDE

The IDE is a hosted, multi-tenant service. Every call needs:

- `Authorization: Bearer $AEPX_IDE_TOKEN` — an OIDC access token from https://auth.softwareequality.com
  (realm `aepx`). Ask the user to sign in at https://ide.softwareequality.com and provide a token; never
  guess, store or print it.
- `X-Tenant-ID: <workspace id>` — get it from `POST /api/v1/workspace` (personal workspace, `u-…`).

Base URL: `${AEPX_IDE_URL:-https://ide.softwareequality.com}`. Use `curl -sS` and `jq`.

## Modules

`GET /api/v1/ide-modules` (no auth) lists them. Available: `software`, `sound`, `music`, `film`,
`animation`, `sdk`, `social`, `multimedia`, `media`. Others have `status: planned` and cannot be chosen.

## Projects and files

| Task | Call |
| --- | --- |
| List projects | `GET /api/v1/projects` |
| Create in a module | `POST /api/v1/projects` `{"name","description","module"}` — starter files are created |
| Rename | `PATCH /api/v1/projects/{id}` `{"name"?, "description"?}` |
| Archive / restore | `DELETE /api/v1/projects/{id}` · `POST /api/v1/projects/{id}/restore` · `GET /api/v1/projects-archived` |
| Files | `GET /api/v1/projects/{id}/files` · `PUT …/files/{path}` `{"content"}` · `DELETE …/files/{path}` |
| History / restore | `GET …/history?path=` · `GET …/history/{version}?path=` · `POST …/restore-file` `{"path","version"}` |

Paths are relative, no `..`. Every save, delete and restore is a numbered version.

## Agent runs (human approval required)

1. `POST /api/v1/agent-runs` `{"project_id","task"}` → a plan with the module's crew, status `awaiting_approval`.
2. Show the plan to the user. Only after the user approves: `POST /api/v1/agent-runs/{id}/decision?approved=true`,
   then `POST /api/v1/agent-runs/{id}/enqueue`.
3. Poll `GET /api/v1/agent-runs/{id}` until `completed` or `failed`; `result` holds the answer.
   `GET /api/v1/ai-usage` shows today's allowance.

Never approve a run the user has not explicitly approved in this conversation.

## Roles and audit

- Roles: owner, admin, editor (developer), media_editor (media folders only), reviewer (read + approve), viewer.
  `GET /api/v1/me/permissions`, `GET /api/v1/acl/matrix`.
- Members (owners/admins): `GET /api/v1/members`, `PUT /api/v1/members/{subject}` `{"role"}` (`remove` removes).
- Audit (owners, admins, reviewers): `GET /api/v1/audit-events`, `GET /api/v1/audit-events/verify`.

A 403 means the role does not allow the action; report it rather than retrying another way.
