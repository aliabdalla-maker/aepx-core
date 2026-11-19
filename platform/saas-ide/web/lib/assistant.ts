// In-app assistant: instant answers from the help file (free, works signed out) and AI requests
// that go through the governed agent pipeline (approved, metered, capped). Pure helpers only.

export type HelpTopic = { module: string; moduleTitle: string; title: string; body: string };
export type HelpHit = HelpTopic & { score: number };

/** Parse "# id | Module title" sections with "## Topic" entries. */
export function parseHelp(md: string): HelpTopic[] {
  const topics: HelpTopic[] = [];
  let module = "general", moduleTitle = "Getting started", current: HelpTopic | null = null;
  const close = () => { if (current) { current.body = current.body.trim(); if (current.body) topics.push(current); } current = null; };
  for (const line of md.replace(/\r\n/g, "\n").split("\n")) {
    const h1 = line.match(/^#\s+([a-z0-9-]+)\s*\|\s*(.+?)\s*$/i);
    if (h1) { close(); module = h1[1].toLowerCase(); moduleTitle = h1[2]; continue; }
    const h2 = line.match(/^##\s+(.+?)\s*$/);
    if (h2) { close(); current = { module, moduleTitle, title: h2[1], body: "" }; continue; }
    if (current) current.body += line + "\n";
  }
  close();
  return topics;
}

const STOP = new Set(("a an and are as at be by can do does for from how i if in is it its my of on or so the "
  + "this to what when where which who why with you your me we our use using").split(" "));

export function tokens(text: string): string[] {
  return (text.toLowerCase().match(/[a-z0-9]+/g) ?? [])
    .filter(t => t.length > 1 && !STOP.has(t))
    .map(t => (t.length > 4 && t.endsWith("s") ? t.slice(0, -1) : t));
}

/** Rank help topics for a question; the current module and general help are preferred. */
export function searchHelp(topics: HelpTopic[], question: string, module = "general", limit = 3): HelpHit[] {
  const q = [...new Set(tokens(question))];
  if (!q.length) return [];
  const hits: HelpHit[] = [];
  for (const t of topics) {
    const title = new Set(tokens(t.title)), body = tokens(t.body), bodySet = new Set(body);
    let score = 0;
    for (const w of q) {
      if (title.has(w)) score += 3;
      if (bodySet.has(w)) score += 1 + Math.min(body.filter(b => b === w).length - 1, 2) * 0.25;
    }
    if (!score) continue;
    const weight = t.module === module ? 1.5 : t.module === "general" ? 1 : 0.6;
    hits.push({ ...t, score: Math.round(score * weight * 100) / 100 });
  }
  return hits.sort((a, b) => b.score - a.score).slice(0, limit);
}

/** Topics to show before anything is typed: the module's own, then the basics. */
export function suggestedTopics(topics: HelpTopic[], module: string, limit = 6): HelpTopic[] {
  return [...topics.filter(t => t.module === module), ...topics.filter(t => t.module === "general")].slice(0, limit);
}

export async function loadHelp(fetcher: typeof fetch = fetch, url = "/help/aepx-help.md"): Promise<HelpTopic[]> {
  try {
    const r = await fetcher(url, { credentials: "omit" });
    return r.ok ? parseHelp(await r.text()) : [];
  } catch { return []; }
}

export type AiContext = { question: string; moduleName: string; file?: string; excerpts: HelpTopic[] };
const TASK_LIMIT = 4000; // RunRequest.task max_length on the API

/** The task sent to the agent pipeline: the question first, then bounded context. */
export function buildAiTask(c: AiContext): string {
  const question = c.question.trim().slice(0, 1500);
  let task = `Question from a user of the AEP-X ${c.moduleName}: ${question}\n\n`
    + "Answer as the AEP-X in-app assistant: be concise and practical, use the user's module and "
    + "file context, give step-by-step instructions or code in fenced blocks with file names when useful, "
    + "and say if something is not possible in AEP-X.\n";
  if (c.file) task += `\nOpen file: ${c.file.slice(0, 200)}\n`;
  for (const e of c.excerpts) {
    const add = `\nHelp: ${e.moduleTitle} — ${e.title}\n${e.body}\n`;
    if (task.length + add.length > TASK_LIMIT) break;
    task += add;
  }
  return task.slice(0, TASK_LIMIT);
}

/** What the "Ask AI" button can do right now, with the reason when it can't. */
export function aiAvailability(o: { signedIn: boolean; project: string; agentsLive: boolean; readOnly?: boolean }):
  { ok: boolean; reason: string } {
  if (!o.signedIn) return { ok: false, reason: "Sign in to ask the AI. Help answers work without signing in." };
  if (!o.project) return { ok: false, reason: "Open a project to ask the AI about your work." };
  if (o.readOnly) return { ok: false, reason: "Your role is read-only, so it cannot start AI requests." };
  if (!o.agentsLive) return { ok: false, reason: "AI is not switched on for this workspace yet. Help answers still work." };
  return { ok: true, reason: "" };
}

export const FINAL_STATUSES = new Set(["succeeded", "failed", "rejected", "cancelled"]);
