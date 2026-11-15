import type { IdeModule } from "./api";

export const availableModules = (all: IdeModule[]) => all.filter(m => m.status === "available");
export const plannedModules = (all: IdeModule[]) => all.filter(m => m.status === "planned");

/** Display label for a project's module; unknown ids fall back to the Software IDE. */
export function moduleLabel(all: IdeModule[], id: string | undefined): string {
  return all.find(m => m.id === (id || "software"))?.name ?? "Software IDE";
}

/** Quick tasks for the agent panel: the module's own first, then general ones, de-duplicated. */
export function moduleTasks(all: IdeModule[], id: string | undefined, general: { label: string; task: string }[]) {
  const own = (all.find(m => m.id === (id || "software"))?.quick_tasks ?? [])
    .map(task => ({ label: task.length > 28 ? task.slice(0, 26).trimEnd() + "…" : task, task }));
  const seen = new Set(own.map(o => o.task));
  return [...own, ...general.filter(g => !seen.has(g.task))].slice(0, 10);
}

/** Human-readable relative age for version lists. */
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (!Number.isFinite(s)) return "";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
