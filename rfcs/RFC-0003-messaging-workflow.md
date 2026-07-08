# RFC-0003: Messaging & Workflow

Status: Draft
Author(s): AEP-X Founding Team
Created: 7 July 2026

## 1. Abstract

Defines the event bus and orchestration modes for multi-step agent workflows.

## 2. Motivation

Tier 2 services (Workflow, Safety, Governance) communicate by publishing facts, not by calling each other directly (Microservices-Implementation-Guide.html §4.2) — this RFC is what makes that pattern well-defined rather than ad hoc.

## 3. Design Goals

Choreography over orchestration for cross-cutting concerns (audit, safety escalation, trust feedback); orchestration only within a single workflow run.

## 4. Specification

Orchestration modes: Sequential (built), Parallel/Conditional/Dynamic (deferred to Beta per Instructional Manual §4.2).

Event topics (see also `docs/` event-contract tables): `workflow.completed`, `safety.flagged`, `agent.registered`, `trust.updated`, `verification.completed`, `ml.prediction.made`, `knowledge.updated`, `connector.invoked`, `connector.failed`.

## 5. Data Model / Schema

`workflow.*` schema, Kafka topic definitions.

## 6. Security & Compliance Considerations

Governance Engine consumes every topic unconditionally for the audit trail (Law 8) — no other service needs to remember to call it.

## 7. Backward Compatibility

New topics are additive; consumers must ignore unrecognised fields.

## 8. Reference Implementation

`services/workflow/`, `services/safety/`, `services/governance/`, `services/verification/`, `services/ml-integration/`, `connector-bus/`.

## 9. Open Questions

Parallel/Conditional/Dynamic orchestration modes remain a Beta-phase build per the Instructional Manual's own scope discipline.
