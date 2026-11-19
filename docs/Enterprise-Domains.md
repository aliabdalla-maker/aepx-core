# AEP-X Enterprise Domains: SCM and HRM

AEP-X treats Supply Chain Management (SCM) and Human Resource Management (HRM)
as first-class enterprise domains rather than vendor-specific integrations.
The enterprise connector service publishes domain metadata through `/domains`,
`/domains/{domain}` and `/domains/{domain}/connectors`.

## SCM

SCM covers supplier, procurement, inventory, demand-planning and logistics
coordination. Initial connector affinity is SAP, Oracle ERP, Dynamics 365 and
NetSuite. Read/analysis capabilities include supplier and inventory reads,
demand forecasting and shipment tracking.

Actions that can create material commercial commitments remain human-governed.
The initial approval-required operations are `purchase_order.approve`,
`supplier.activate` and `inventory.writeoff`.

## HRM

HRM covers recruitment, onboarding, workforce and leave information, skills and
HR analytics. Initial connector affinity is Workday, BambooHR, SAP
SuccessFactors and SAP.

Employment-impacting operations are never represented as unattended default
actions. The domain marks `hire.approve`, `termination.approve`,
`payroll.change` and `compensation.change` as approval-required. HRM metadata
also identifies personal, employment, compensation and special-category data so
policy and audit layers can apply stricter handling.

## Domain-bound execution

Existing connector envelopes remain backwards compatible. A caller that wants
explicit domain isolation adds `metadata.domain`:

```json
{
  "sender": "aepx://agent/supply-planner",
  "receiver": "aepx://connector/sap",
  "payload": {"op": "inventory.read"},
  "metadata": {"domain": "scm"}
}
```

When a domain is supplied, the enterprise service rejects a connector that is
not registered for that domain. Successful results include both the requested
`domain` and all domain affinities for the connector.

## Governance integration

This domain registry is descriptive and routing-enforcing; it does not bypass
AEP-X governance. Side effects still pass through the existing connector bus,
trust, governance, safety and workflow layers. The `approval_required` metadata
is intended for the orchestration/governance layer to turn into mandatory human
approval gates in the next implementation increment.
