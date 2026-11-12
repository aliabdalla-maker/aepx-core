import type { Config } from "@netlify/functions";
import { desc, eq } from "drizzle-orm";
import { db } from "../../db/index.js";
import { portals, connections, tasks, agents, events } from "../../db/schema.js";
import { ensureSeeded } from "../../db/seed.js";
import { probePortal } from "../../db/probe.js";

const CONNECTION_STATUS = ["planned", "connected", "degraded", "offline"];
const TASK_STATUS = ["backlog", "in_progress", "review", "blocked", "done"];
const TASK_KIND = ["integration", "feature", "incident", "agent-task"];
const PRIORITY = ["P0", "P1", "P2", "P3"];
const AGENT_STATUS = ["active", "idle", "paused", "error"];

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const str = (v: unknown, field: string, max = 200, required = true) => {
  if (v == null || v === "") {
    if (required) throw new HttpError(400, `${field} is required`);
    return undefined;
  }
  if (typeof v !== "string") throw new HttpError(400, `${field} must be a string`);
  const s = v.trim();
  if (s.length > max) throw new HttpError(400, `${field} must be at most ${max} characters`);
  return s;
};

const oneOf = (v: unknown, field: string, allowed: string[], required = false) => {
  const s = str(v, field, 40, required);
  if (s !== undefined && !allowed.includes(s)) throw new HttpError(400, `${field} must be one of ${allowed.join(", ")}`);
  return s;
};

// Only public http(s) URLs may be stored, since the probe fetches them server-side.
const publicUrl = (v: unknown) => {
  const s = str(v, "baseUrl", 300, false);
  if (!s) return "";
  let url: URL;
  try {
    url = new URL(s);
  } catch {
    throw new HttpError(400, "baseUrl must be a valid URL");
  }
  const host = url.hostname;
  if (
    !/^https?:$/.test(url.protocol) ||
    host === "localhost" ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    /^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|0\.|\[)/.test(host)
  ) {
    throw new HttpError(400, "baseUrl must be a public http(s) URL");
  }
  return url.toString();
};

const log = (portalSlug: string | null, kind: string, message: string) =>
  db.insert(events).values({ portalSlug, kind, message });

async function findPortal(slug: string) {
  const [portal] = await db.select().from(portals).where(eq(portals.slug, slug));
  if (!portal) throw new HttpError(404, `Unknown portal ${slug}`);
  return portal;
}

async function state() {
  const [p, c, t, a, e] = await Promise.all([
    db.select().from(portals).orderBy(portals.createdAt),
    db.select().from(connections).orderBy(connections.id),
    db.select().from(tasks).orderBy(desc(tasks.updatedAt)),
    db.select().from(agents).orderBy(agents.id),
    db.select().from(events).orderBy(desc(events.createdAt)).limit(80),
  ]);
  return { portals: p, connections: c, tasks: t, agents: a, events: e, generatedAt: new Date().toISOString() };
}

async function route(req: Request, parts: string[]) {
  const method = req.method;
  const body = method === "POST" || method === "PATCH" ? await req.json().catch(() => ({})) : {};
  const [resource, id, action] = parts;

  if (resource === "state" && method === "GET") return state();

  if (resource === "portals" && id) {
    const portal = await findPortal(id);
    if (action === "probe" && method === "POST") return probePortal(portal);
    if (!action && method === "PATCH") {
      const baseUrl = publicUrl(body.baseUrl);
      const [updated] = await db
        .update(portals)
        .set({ baseUrl, status: baseUrl ? portal.status : "unknown" })
        .where(eq(portals.slug, id))
        .returning();
      await log(id, "config", baseUrl ? `${portal.name} endpoint set to ${baseUrl}` : `${portal.name} endpoint cleared`);
      return baseUrl ? probePortal(updated) : updated;
    }
  }

  if (resource === "connections") {
    if (!id && method === "POST") {
      const portal = await findPortal(str(body.portalSlug, "portalSlug", 20)!);
      const [row] = await db
        .insert(connections)
        .values({
          portalSlug: portal.slug,
          target: str(body.target, "target", 80)!,
          targetKind: oneOf(body.targetKind, "targetKind", ["service", "connector"]) ?? "service",
          protocol: str(body.protocol, "protocol", 30, false) ?? "REST",
          status: oneOf(body.status, "status", CONNECTION_STATUS) ?? "planned",
          notes: str(body.notes, "notes", 500, false) ?? "",
        })
        .returning();
      await log(portal.slug, "connection", `Linked ${portal.code} → ${row.target} (${row.status})`);
      return row;
    }
    if (id) {
      const [existing] = await db.select().from(connections).where(eq(connections.id, Number(id)));
      if (!existing) throw new HttpError(404, "Connection not found");
      if (method === "PATCH") {
        const status = oneOf(body.status, "status", CONNECTION_STATUS);
        const notes = str(body.notes, "notes", 500, false);
        const [row] = await db
          .update(connections)
          .set({ ...(status && { status }), ...(notes !== undefined && { notes }), updatedAt: new Date() })
          .where(eq(connections.id, existing.id))
          .returning();
        if (status && status !== existing.status)
          await log(existing.portalSlug, "connection", `${existing.target} link: ${existing.status} → ${status}`);
        return row;
      }
      if (method === "DELETE") {
        await db.delete(connections).where(eq(connections.id, existing.id));
        await log(existing.portalSlug, "connection", `Removed link to ${existing.target}`);
        return { ok: true };
      }
    }
  }

  if (resource === "tasks") {
    if (!id && method === "POST") {
      const portal = await findPortal(str(body.portalSlug, "portalSlug", 20)!);
      const [row] = await db
        .insert(tasks)
        .values({
          portalSlug: portal.slug,
          title: str(body.title, "title", 160)!,
          kind: oneOf(body.kind, "kind", TASK_KIND) ?? "integration",
          status: oneOf(body.status, "status", TASK_STATUS) ?? "backlog",
          priority: oneOf(body.priority, "priority", PRIORITY) ?? "P2",
          agent: str(body.agent, "agent", 60, false) ?? "",
        })
        .returning();
      await log(portal.slug, "task", `New ${row.priority} ${row.kind}: ${row.title}`);
      return row;
    }
    if (id) {
      const [existing] = await db.select().from(tasks).where(eq(tasks.id, Number(id)));
      if (!existing) throw new HttpError(404, "Task not found");
      if (method === "PATCH") {
        const patch = {
          title: str(body.title, "title", 160, false),
          status: oneOf(body.status, "status", TASK_STATUS),
          priority: oneOf(body.priority, "priority", PRIORITY),
          kind: oneOf(body.kind, "kind", TASK_KIND),
          agent: typeof body.agent === "string" ? str(body.agent, "agent", 60, false) ?? "" : undefined,
        };
        const set = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined));
        const [row] = await db
          .update(tasks)
          .set({ ...set, updatedAt: new Date() })
          .where(eq(tasks.id, existing.id))
          .returning();
        if (patch.status && patch.status !== existing.status)
          await log(existing.portalSlug, "task", `“${existing.title}” moved ${existing.status} → ${patch.status}`);
        return row;
      }
      if (method === "DELETE") {
        await db.delete(tasks).where(eq(tasks.id, existing.id));
        await log(existing.portalSlug, "task", `Deleted “${existing.title}”`);
        return { ok: true };
      }
    }
  }

  if (resource === "agents" && id) {
    const [existing] = await db.select().from(agents).where(eq(agents.id, Number(id)));
    if (!existing) throw new HttpError(404, "Agent not found");
    if (action === "heartbeat" && method === "POST") {
      const [row] = await db
        .update(agents)
        .set({ lastHeartbeatAt: new Date() })
        .where(eq(agents.id, existing.id))
        .returning();
      return row;
    }
    if (!action && method === "PATCH") {
      const status = oneOf(body.status, "status", AGENT_STATUS, true)!;
      const [row] = await db
        .update(agents)
        .set({ status, lastHeartbeatAt: new Date() })
        .where(eq(agents.id, existing.id))
        .returning();
      await log(existing.portalSlug, "agent", `${existing.name}: ${existing.status} → ${status}`);
      return row;
    }
  }

  throw new HttpError(404, "Not found");
}

export default async (req: Request) => {
  const parts = new URL(req.url).pathname.replace(/^\/api\/?/, "").split("/").filter(Boolean);
  try {
    await ensureSeeded();
    return Response.json(await route(req, parts), { headers: { "cache-control": "no-store" } });
  } catch (err) {
    if (err instanceof HttpError) return Response.json({ error: err.message }, { status: err.status });
    console.error(err);
    return Response.json({ error: "Internal error" }, { status: 500 });
  }
};

export const config: Config = {
  path: "/api/*",
};
