import { eq } from "drizzle-orm";
import { db } from "./index.js";
import { portals, events } from "./schema.js";

type Portal = typeof portals.$inferSelect;

// Hits a portal's base URL (its /health if it responds, else the root) and records the result.
export async function probePortal(portal: Portal) {
  if (!portal.baseUrl) return { ...portal, status: "unknown" };
  const started = Date.now();
  let status = "offline";
  let latencyMs: number | null = null;
  try {
    const opts = { signal: AbortSignal.timeout(6000), redirect: "follow" as const };
    let res = await fetch(new URL("health", portal.baseUrl.replace(/\/?$/, "/")), opts).catch(() => null);
    if (!res?.ok) res = await fetch(portal.baseUrl, opts);
    latencyMs = Date.now() - started;
    status = res.ok ? (latencyMs > 2500 ? "degraded" : "online") : res.status < 500 ? "degraded" : "offline";
  } catch {
    latencyMs = null;
  }
  const [updated] = await db
    .update(portals)
    .set({ status, latencyMs, lastCheckedAt: new Date() })
    .where(eq(portals.slug, portal.slug))
    .returning();
  if (status !== portal.status) {
    await db.insert(events).values({
      portalSlug: portal.slug,
      kind: "health",
      message: `${portal.name} is now ${status}${latencyMs != null ? ` (${latencyMs} ms)` : ""}`,
    });
  }
  return updated;
}
