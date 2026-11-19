"""First-class enterprise domain registry for AEP-X.

The registry describes domain capabilities and connector affinity without
coupling orchestration to any one SaaS vendor.  It is intentionally metadata
only: external side effects still flow through the connector bus and the
existing governance/trust services.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DomainDefinition:
    name: str
    title: str
    description: str
    connectors: tuple[str, ...]
    capabilities: tuple[str, ...]
    approval_required: tuple[str, ...]
    data_classes: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


SCM = DomainDefinition(
    name="scm",
    title="Supply Chain Management",
    description=(
        "Supplier, procurement, inventory, demand-planning and logistics "
        "coordination through governed AEP-X connector execution."
    ),
    connectors=("sap", "oracle-erp", "dynamics365", "netsuite"),
    capabilities=(
        "supplier.read",
        "procurement.read",
        "inventory.read",
        "demand.forecast",
        "shipment.track",
    ),
    approval_required=(
        "purchase_order.approve",
        "supplier.activate",
        "inventory.writeoff",
    ),
    data_classes=("commercial", "supplier", "inventory", "logistics"),
)

HRM = DomainDefinition(
    name="hrm",
    title="Human Resource Management",
    description=(
        "Recruitment, onboarding, workforce, leave, skills and HR analytics "
        "with explicit human oversight for employment-impacting actions."
    ),
    connectors=("workday", "bamboohr", "successfactors", "sap"),
    capabilities=(
        "worker.read",
        "recruitment.read",
        "onboarding.status",
        "leave.read",
        "skills.read",
        "workforce.analytics",
    ),
    approval_required=(
        "hire.approve",
        "termination.approve",
        "payroll.change",
        "compensation.change",
    ),
    data_classes=("personal", "employment", "compensation", "special-category"),
)

DOMAIN_REGISTRY: dict[str, DomainDefinition] = {d.name: d for d in (SCM, HRM)}


def get_domain(name: str) -> DomainDefinition | None:
    return DOMAIN_REGISTRY.get(name.lower())


def connector_domains(connector_name: str) -> list[str]:
    return sorted(
        name for name, domain in DOMAIN_REGISTRY.items() if connector_name in domain.connectors
    )
