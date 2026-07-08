# RFC-0001: Core Protocol

Status: Draft
Author(s): AEP-X Founding Team
Created: 7 July 2026

## 1. Abstract

Defines the message envelope, message types, and capability contract every AEP-X component uses to communicate — the "birth certificate" of AEP-X, per the source manual.

## 2. Motivation

Without one wire format, every service pair would need its own translation layer. This RFC exists so that isn't true.

## 3. Design Goals

Interoperability, cost optimisation, anti-hallucination, trust-by-design, observability, vendor neutrality.

## 4. Specification

Message envelope:
```json
{
  "version": "1.0", "messageId": "uuid", "timestamp": "ISO8601",
  "sender": "aepx://agent/source", "receiver": "aepx://agent/target",
  "messageType": "request", "payload": {}, "metadata": {}, "signature": "jwt"
}
```
Message types: REQUEST, RESPONSE, EVENT, NEGOTIATION, DELEGATION, ESCALATION, BROADCAST.
Addressing scheme: `aepx://agent/{id}`, `aepx://tool/{id}`, `aepx://workflow/{id}`, `aepx://capability/{id}`, `aepx://memory/{id}`, `aepx://policy/{id}`, `aepx://connector/{name}` (extended by SOA-Architecture.md for the Connector Bus).

## 5. Data Model / Schema

See `schemas/sql/001_init.sql`, `schemas/openapi/registry.yaml`.

## 6. Security & Compliance Considerations

`signature` is a JWT signed by the sender's Identity Service-issued key; see RFC-0002.

## 7. Backward Compatibility

v1.x is additive-only per the Constitution's Standards Lifecycle (Article IV).

## 8. Reference Implementation

`services/gateway/`, `services/registry/`, and every service that sends or receives a message.

## 9. Open Questions

Whether `messageType` needs a distinct COMMAND type separate from REQUEST — deferred to pilot data, per ADLC Plan §15.5's "demote RFCs to living design docs until third-party implementers exist" recommendation.
