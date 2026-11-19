import { pgTable, serial, text, timestamp, integer, index } from "drizzle-orm/pg-core";

// One row per AEP-X ecosystem portal (CRM, ERP, TMS, FDE, EDU supply, Cybersecurity).
export const portals = pgTable("portals", {
  slug: text().primaryKey(),
  name: text().notNull(),
  code: text().notNull(),
  description: text().notNull().default(""),
  color: text().notNull().default("#7dd3fc"),
  baseUrl: text("base_url").notNull().default(""),
  status: text().notNull().default("unknown"), // online | degraded | offline | unknown
  latencyMs: integer("latency_ms"),
  lastCheckedAt: timestamp("last_checked_at"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

// A portal's link into an aepx-core service or connector.
export const connections = pgTable(
  "connections",
  {
    id: serial().primaryKey(),
    portalSlug: text("portal_slug").notNull().references(() => portals.slug, { onDelete: "cascade" }),
    target: text().notNull(),
    targetKind: text("target_kind").notNull().default("service"), // service | connector
    protocol: text().notNull().default("REST"),
    status: text().notNull().default("planned"), // planned | connected | degraded | offline
    notes: text().notNull().default(""),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (t) => [index("connections_portal_idx").on(t.portalSlug)],
);

// Work items tracked per portal (integrations, features, incidents, agent tasks).
export const tasks = pgTable(
  "tasks",
  {
    id: serial().primaryKey(),
    portalSlug: text("portal_slug").notNull().references(() => portals.slug, { onDelete: "cascade" }),
    title: text().notNull(),
    kind: text().notNull().default("integration"), // integration | feature | incident | agent-task
    status: text().notNull().default("backlog"), // backlog | in_progress | review | blocked | done
    priority: text().notNull().default("P2"), // P0..P3
    agent: text().notNull().default(""),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (t) => [index("tasks_portal_idx").on(t.portalSlug)],
);

// Autonomous agents operating across the ecosystem.
export const agents = pgTable("agents", {
  id: serial().primaryKey(),
  name: text().notNull().unique(),
  role: text().notNull(),
  portalSlug: text("portal_slug").references(() => portals.slug, { onDelete: "set null" }),
  status: text().notNull().default("idle"), // active | idle | paused | error
  trustScore: integer("trust_score").notNull().default(60),
  lastHeartbeatAt: timestamp("last_heartbeat_at").defaultNow(),
});

// Append-only activity / audit feed.
export const events = pgTable(
  "events",
  {
    id: serial().primaryKey(),
    portalSlug: text("portal_slug"),
    kind: text().notNull(),
    message: text().notNull(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (t) => [index("events_created_idx").on(t.createdAt)],
);
