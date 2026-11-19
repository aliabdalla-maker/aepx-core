import { sql } from "drizzle-orm";
import { db } from "./index.js";
import { portals, connections, tasks, agents, events } from "./schema.js";

// Initial ecosystem map: each portal wired to the aepx-core services and
// catalogue connectors (connectors/catalogue.json) it depends on.
const PORTALS = [
  {
    slug: "crm", code: "CRM", name: "CRM Portal", color: "#38bdf8",
    description: "Customer relationship management — accounts, leads and agent-assisted sales pipelines.",
    links: [
      ["gateway", "service", "REST", "connected"], ["memory", "service", "REST", "connected"],
      ["knowledge", "service", "REST", "connected"], ["salesforce", "connector", "SOAP/REST", "connected"],
      ["hubspot", "connector", "REST", "planned"], ["zoho-crm", "connector", "REST", "planned"],
      ["dynamics365", "connector", "REST", "planned"],
    ],
  },
  {
    slug: "erp", code: "ERP", name: "ERP Portal", color: "#a78bfa",
    description: "Enterprise resource planning — finance, procurement, HR and inventory ledgers.",
    links: [
      ["gateway", "service", "REST", "connected"], ["workflow", "service", "REST", "connected"],
      ["billing", "service", "REST", "degraded"], ["sap", "connector", "SOAP/REST", "planned"],
      ["oracle-erp", "connector", "SOAP/REST", "planned"], ["netsuite", "connector", "REST", "planned"],
      ["workday", "connector", "SOAP/REST", "planned"],
    ],
  },
  {
    slug: "tms", code: "TMS", name: "TMS Portal", color: "#fbbf24",
    description: "Transportation management — routing, fleet telemetry, carrier events and dispatch.",
    links: [
      ["gateway", "service", "REST", "connected"], ["discovery", "service", "REST", "connected"],
      ["workflow", "service", "REST", "connected"], ["kafka", "connector", "Kafka", "degraded"],
      ["mqtt", "connector", "MQTT", "planned"], ["opcua", "connector", "OPC UA", "planned"],
    ],
  },
  {
    slug: "fde", code: "FDE", name: "Forward Development Engineering Portal", color: "#34d399",
    description: "Forward-deployed engineering — repos, CI/CD, release trains and SDK conformance.",
    links: [
      ["registry", "service", "REST", "connected"], ["verification", "service", "REST", "connected"],
      ["github", "connector", "REST", "connected"], ["jenkins", "connector", "REST", "connected"],
      ["jira", "connector", "REST", "planned"], ["terraform-cloud", "connector", "REST", "planned"],
    ],
  },
  {
    slug: "edu", code: "EDU", name: "Educational Servers Supply Management", color: "#f472b6",
    description: "Provisioning and supply of education servers, LMS tenancies and lab capacity.",
    links: [
      ["marketplace", "service", "REST", "connected"], ["cost-optimiser", "service", "REST", "connected"],
      ["moodle", "connector", "REST", "connected"], ["canvas", "connector", "REST", "planned"],
      ["google-classroom", "connector", "REST", "planned"], ["aws-s3", "connector", "S3", "connected"],
    ],
  },
  {
    slug: "sec", code: "SEC", name: "Cybersecurity Portal", color: "#f87171",
    description: "Trust, identity, policy and tamper-evident audit across every portal.",
    links: [
      ["trust", "service", "REST", "connected"], ["identity", "service", "REST", "connected"],
      ["safety", "service", "REST", "connected"], ["governance", "service", "REST", "connected"],
      ["ethereum", "connector", "JSON-RPC", "planned"], ["elasticsearch", "connector", "REST", "planned"],
    ],
  },
] as const;

const TASKS: Array<[string, string, string, string, string, string]> = [
  ["crm", "Sync Salesforce accounts into AEP-X memory", "integration", "in_progress", "P1", "crm-sync-agent"],
  ["crm", "Lead scoring via knowledge service", "feature", "backlog", "P2", ""],
  ["erp", "Billing service latency above SLO", "incident", "blocked", "P0", "erp-ledger-agent"],
  ["erp", "SAP purchase-order adapter", "integration", "backlog", "P1", ""],
  ["tms", "Kafka consumer lag on carrier events", "incident", "in_progress", "P1", "tms-dispatch-agent"],
  ["tms", "Route optimisation workflow", "agent-task", "review", "P2", "tms-dispatch-agent"],
  ["fde", "RFC-0007 conformance run on SDK", "agent-task", "done", "P2", "fde-release-agent"],
  ["fde", "Jenkins pipeline for connector-bus", "integration", "review", "P2", "fde-release-agent"],
  ["edu", "Provision 40 lab servers for spring term", "feature", "in_progress", "P1", "edu-supply-agent"],
  ["edu", "Canvas LTI connector", "integration", "backlog", "P3", ""],
  ["sec", "Anchor governance audit log on-chain", "feature", "backlog", "P2", "sec-sentinel-agent"],
  ["sec", "Rotate did:key identities for all agents", "agent-task", "in_progress", "P1", "sec-sentinel-agent"],
];

const AGENTS: Array<[string, string, string, string, number]> = [
  ["crm-sync-agent", "Customer data synchroniser", "crm", "active", 78],
  ["erp-ledger-agent", "Ledger reconciliation", "erp", "error", 64],
  ["tms-dispatch-agent", "Dispatch & routing planner", "tms", "active", 71],
  ["fde-release-agent", "Release & conformance runner", "fde", "idle", 85],
  ["edu-supply-agent", "Server supply planner", "edu", "active", 69],
  ["sec-sentinel-agent", "Threat & policy sentinel", "sec", "active", 92],
];

let seeded = false;

// Idempotent: only seeds when the portals table is empty.
export async function ensureSeeded() {
  if (seeded) return;
  const [{ count }] = await db.select({ count: sql<number>`count(*)::int` }).from(portals);
  if (count > 0) {
    seeded = true;
    return;
  }
  const inserted = await db
    .insert(portals)
    .values(PORTALS.map(({ links, ...p }) => p))
    .onConflictDoNothing()
    .returning({ slug: portals.slug });
  // Another request won the race and is seeding the rest.
  if (inserted.length === 0) {
    seeded = true;
    return;
  }
  await db.insert(connections).values(
    PORTALS.flatMap((p) =>
      p.links.map(([target, targetKind, protocol, status]) => ({
        portalSlug: p.slug, target, targetKind, protocol, status,
      })),
    ),
  );
  await db.insert(tasks).values(
    TASKS.map(([portalSlug, title, kind, status, priority, agent]) => ({
      portalSlug, title, kind, status, priority, agent,
    })),
  );
  await db
    .insert(agents)
    .values(AGENTS.map(([name, role, portalSlug, status, trustScore]) => ({ name, role, portalSlug, status, trustScore })))
    .onConflictDoNothing();
  await db.insert(events).values({ kind: "system", message: "Ecosystem tracker initialised with 6 portals" });
  seeded = true;
}
