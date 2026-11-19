// Pure editor-workspace helpers: language detection, file tree, open tabs and plan parsing.

const LANGUAGES: Record<string, string> = {
  py: "python", ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
  mjs: "javascript", cjs: "javascript", json: "json", md: "markdown", yml: "yaml", yaml: "yaml",
  html: "html", css: "css", scss: "scss", sql: "sql", sh: "shell", bash: "shell", go: "go",
  rs: "rust", java: "java", kt: "kotlin", kts: "kotlin", rb: "ruby", php: "php", cs: "csharp",
  cpp: "cpp", cc: "cpp", c: "c", h: "c", hpp: "cpp", toml: "ini", ini: "ini", xml: "xml",
  swift: "swift", dockerfile: "dockerfile",
};

export function languageFor(path: string): string {
  const name = path.split("/").pop()?.toLowerCase() ?? "";
  if (name === "dockerfile" || name.endsWith(".dockerfile")) return "dockerfile";
  if (name === "makefile") return "makefile";
  const dot = name.lastIndexOf(".");
  return dot > 0 ? LANGUAGES[name.slice(dot + 1)] ?? "plaintext" : "plaintext";
}

export type TreeNode = { name: string; path: string; children?: TreeNode[] };

/** Builds a sorted folder tree (folders first, then files, alphabetical) from flat paths. */
export function buildTree(paths: string[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", children: [] };
  for (const full of [...new Set(paths)]) {
    const parts = full.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join("/");
      const isFile = index === parts.length - 1;
      node.children ??= [];
      let child = node.children.find(c => c.name === part && Boolean(c.children) === !isFile);
      if (!child) {
        child = isFile ? { name: part, path } : { name: part, path, children: [] };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sort = (nodes: TreeNode[]): TreeNode[] => nodes
    .sort((a, b) => Number(Boolean(b.children)) - Number(Boolean(a.children)) || a.name.localeCompare(b.name))
    .map(n => (n.children ? { ...n, children: sort(n.children) } : n));
  return sort(root.children ?? []);
}

export type Tab = { path: string; content: string; saved: string };

export const isDirty = (tab: Tab) => tab.content !== tab.saved;

/** Opens (or focuses) a tab without duplicating it. */
export function openTab(tabs: Tab[], path: string, content: string): Tab[] {
  return tabs.some(t => t.path === path) ? tabs : [...tabs, { path, content, saved: content }];
}

/** Closes a tab and returns the path that should become active next. */
export function closeTab(tabs: Tab[], path: string, active: string): { tabs: Tab[]; active: string } {
  const index = tabs.findIndex(t => t.path === path);
  if (index < 0) return { tabs, active };
  const next = tabs.filter(t => t.path !== path);
  if (active !== path) return { tabs: next, active };
  const neighbour = next[Math.min(index, next.length - 1)];
  return { tabs: next, active: neighbour?.path ?? "" };
}

export function updateTab(tabs: Tab[], path: string, content: string): Tab[] {
  return tabs.map(t => (t.path === path ? { ...t, content } : t));
}

export function markSaved(tabs: Tab[], path: string): Tab[] {
  return tabs.map(t => (t.path === path ? { ...t, saved: t.content } : t));
}

export type PlanStep = { title: string; detail?: string };

/** The backend stores the supervisor plan as JSON text; accept a string, list or object. */
export function parsePlan(plan: unknown): PlanStep[] {
  let value = plan;
  if (typeof value === "string") {
    const text = value.trim();
    try { value = JSON.parse(text); } catch { return text ? [{ title: text }] : []; }
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const inner = (value as Record<string, unknown>).steps ?? (value as Record<string, unknown>).plan;
    value = Array.isArray(inner) ? inner : [value];
  }
  if (!Array.isArray(value)) return [];
  return value.slice(0, 50).map((step): PlanStep => {
    if (typeof step === "string") return { title: step };
    if (step && typeof step === "object") {
      const s = step as Record<string, unknown>;
      // supervisor.plan_steps() emits {agent, action, goal}.
      const title = s.agent !== undefined
        ? [s.agent, s.action].filter(v => v !== undefined).map(String).join(" · ")
        : String(s.title ?? s.name ?? s.step ?? s.role ?? "Step");
      const detail = s.goal ?? s.detail ?? s.description ?? s.task ?? s.output;
      return detail === undefined ? { title } : { title, detail: String(detail) };
    }
    return { title: String(step) };
  });
}
