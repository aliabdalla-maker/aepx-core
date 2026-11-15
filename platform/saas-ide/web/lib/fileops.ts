// Pure helpers for rename/move, folder delete and project search. The server does the real work
// (POST files-move, DELETE folders/...); these keep the open tabs and file list consistent with it.
import type { Tab } from "./workspace";
import { isSafeRelativePath } from "./api";

type FileEntry = { path: string; content: string };
export type Moved = { from: string; to: string }[];

/** Paths moved by renaming `from` (a file or a folder) to `to`. */
export function movedPath(path: string, from: string, to: string): string | null {
  if (path === from) return to;
  if (path.startsWith(from + "/")) return to + path.slice(from.length);
  return null;
}

export function applyMoveToFiles(files: FileEntry[], moved: Moved): FileEntry[] {
  const map = new Map(moved.map(m => [m.from, m.to]));
  return files.map(f => (map.has(f.path) ? { ...f, path: map.get(f.path)! } : f));
}

/** Open tabs follow their file; unsaved edits are kept. */
export function applyMoveToTabs(tabs: Tab[], moved: Moved): Tab[] {
  const map = new Map(moved.map(m => [m.from, m.to]));
  return tabs.map(t => (map.has(t.path) ? { ...t, path: map.get(t.path)! } : t));
}

export function inFolder(path: string, folder: string): boolean {
  return path.startsWith(folder + "/");
}

/** Validate a rename target before calling the server; returns an error message or "". */
export function renameError(from: string, to: string, existing: string[]): string {
  const target = to.trim();
  if (!target) return "Enter a name.";
  if (!isSafeRelativePath(target) || target.length > 255) return "Use a relative path without '..' or empty parts.";
  if (target === from) return "That is the current name.";
  if (target.startsWith(from + "/")) return "A folder cannot be moved into itself.";
  const moving = new Set(existing.filter(p => p === from || inFolder(p, from)));
  const clash = existing.find(p => !moving.has(p) && [...moving].some(m => movedPath(m, from, target) === p));
  return clash ? `${clash} already exists.` : "";
}

export type SearchHit = { path: string; line: number; text: string };

/** Case-insensitive search over file names and contents; at most `limit` hits. */
export function searchFiles(files: FileEntry[], query: string, limit = 200): { hits: SearchHit[]; truncated: boolean } {
  const q = query.trim().toLowerCase();
  const hits: SearchHit[] = [];
  if (q.length < 2) return { hits, truncated: false };
  for (const f of [...files].sort((a, b) => a.path.localeCompare(b.path))) {
    if (f.path.toLowerCase().includes(q)) hits.push({ path: f.path, line: 0, text: f.path });
    const lines = f.content.split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].toLowerCase().includes(q)) {
        hits.push({ path: f.path, line: i + 1, text: lines[i].trim().slice(0, 160) });
        if (hits.length >= limit) return { hits, truncated: true };
      }
    }
    if (hits.length >= limit) return { hits, truncated: true };
  }
  return { hits, truncated: false };
}
