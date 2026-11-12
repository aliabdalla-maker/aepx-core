import type { Config } from "@netlify/functions";
import { ne } from "drizzle-orm";
import { db } from "../../db/index.js";
import { portals } from "../../db/schema.js";
import { probePortal } from "../../db/probe.js";

// Re-checks every portal with a configured endpoint so the tracker stays live.
export default async () => {
  const configured = await db.select().from(portals).where(ne(portals.baseUrl, ""));
  await Promise.allSettled(configured.map(probePortal));
};

export const config: Config = {
  schedule: "*/15 * * * *",
};
