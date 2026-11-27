# Agentic Antivirus — owner decisions and release approvals

Product owner and release approval owner (D-02, PRJ-13, PRJ-14): **Ali**.

Every production deployment needs a recorded approval (RA-10). From v0.1.2 the record is the
GitHub `production` environment approval on the deploy job (required reviewer: Ali); this file
lists the decisions and the releases they gate.

## Decisions — 27 Nov 2026

Recorded by `tools/record_decisions.py --owner Ali --date 2026-11-27 --accept-all-proposed`.
All proposed defaults in `REBASELINE-R1.md` (*Accept proposed decision*) are accepted as written:

| Decision | Accepted value |
|---|---|
| D-03 / C-05 providers | No external providers in R1; live adapters in R2 |
| D-04 data classification | Telemetry = Confidential; UK GDPR; privacy page live; no voice recordings stored |
| D-05 test corpus | EICAR + benign OS/office corpus; equal-weight acceptance criteria |
| D-06 KPI targets | PRD values: OBJ-03 < 0.5 % false positives, OBJ-04 30 s, OBJ-05 3 pp CPU, DDL-02 60 s |
| D-07 LLM provider | None in R1; rules-based investigation, LLM opt-in off |
| D-08 OCI compartment | Existing compartment hosting the ai4business VM |
| D-09 self-correction cap | USD 1.00 per task |
| D-10 Windows agent | User-mode agent in R1; kernel blocking in R2 |
| D-11 / C-03 template modules | Apply as implemented; translations deferred |
| D-12 account model | B2B tenants, open self-registration and invitations |
| D-13 / C-04 locales | Keep both fil and tl |
| R1 delivery / ops | Channels = OCI + GitHub + Docker; operator = product owner; alerts via console + email; automated security tests accepted for the beta |

## Release approvals

| Release | Approved by | Date | Record |
|---|---|---|---|
| aav-v0.1.2 | Ali | pending | GitHub `production` environment approval on the deploy run |
