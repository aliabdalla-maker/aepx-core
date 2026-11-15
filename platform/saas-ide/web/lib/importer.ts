// Import files, folders and .zip archives into a project. Everything runs in the browser; files are
// then saved one by one through the normal, audited, versioned save endpoint. Pure and unit-tested.
import { isSafeRelativePath } from "./api";

export type RawEntry = { path: string; data: Uint8Array };
export type PlannedFile = { path: string; content: string };
export type Skipped = { path: string; reason: string };
export type ImportPlan = { files: PlannedFile[]; skipped: Skipped[] };

export const MAX_FILES = 300;
export const MAX_FILE_BYTES = 1_000_000; // FileIn.content max_length on the API
const MAX_ZIP_ENTRIES = 5000;
const MAX_ZIP_TOTAL = 60_000_000; // uncompressed bytes, guards against zip bombs
const IGNORED_DIRS = new Set(["node_modules", ".git", "__pycache__", "__MACOSX", ".venv", "venv", ".next", "dist", "build", ".idea", ".vs"]);
const IGNORED_FILES = new Set([".DS_Store", "Thumbs.db", "desktop.ini"]);

/** "./a\\b/c.txt" -> "a/b/c.txt"; joins an optional target folder. */
export function normalisePath(path: string, prefix = ""): string {
  const clean = path.replace(/\\/g, "/").split("/").filter(p => p && p !== ".").join("/");
  const pre = prefix.replace(/\\/g, "/").split("/").filter(p => p && p !== ".").join("/");
  return pre ? `${pre}/${clean}` : clean;
}

/** Drop a single folder that wraps every entry (e.g. "repo-main/" in a GitHub zip). */
export function stripCommonRoot(paths: string[]): string[] {
  if (paths.length < 1 || !paths.every(p => p.includes("/"))) return paths;
  const root = paths[0].split("/")[0];
  return paths.every(p => p.split("/")[0] === root) ? paths.map(p => p.slice(root.length + 1)) : paths;
}

export function isBinary(data: Uint8Array): boolean {
  const n = Math.min(data.length, 8000);
  for (let i = 0; i < n; i++) if (data[i] === 0) return true;
  try { new TextDecoder("utf-8", { fatal: true }).decode(data); return false; } catch { return true; }
}

export function planImport(entries: RawEntry[], existing: Set<string>,
  o: { overwrite: boolean; prefix?: string; stripRoot?: boolean }): ImportPlan {
  const skipped: Skipped[] = [];
  const files: PlannedFile[] = [];
  const seen = new Set<string>();
  const names = entries.map(e => normalisePath(e.path));
  const paths = o.stripRoot ? stripCommonRoot(names) : names;
  entries.forEach((e, i) => {
    const original = names[i];
    const parts = paths[i].split("/");
    if (parts.some(p => IGNORED_DIRS.has(p)) || IGNORED_FILES.has(parts[parts.length - 1])) {
      skipped.push({ path: original, reason: "ignored folder or system file" }); return;
    }
    const path = normalisePath(paths[i], o.prefix);
    if (!path || !isSafeRelativePath(path) || path.length > 255) { skipped.push({ path: original, reason: "unsafe or too long path" }); return; }
    if (seen.has(path)) { skipped.push({ path, reason: "duplicate in this import" }); return; }
    if (e.data.length > MAX_FILE_BYTES) { skipped.push({ path, reason: "larger than 1 MB" }); return; }
    if (isBinary(e.data)) { skipped.push({ path, reason: "binary file (only text files can be imported)" }); return; }
    if (existing.has(path) && !o.overwrite) { skipped.push({ path, reason: "already exists (tick Replace existing files)" }); return; }
    if (files.length >= MAX_FILES) { skipped.push({ path, reason: `over the ${MAX_FILES}-file limit for one import` }); return; }
    seen.add(path);
    files.push({ path, content: new TextDecoder().decode(e.data) });
  });
  return { files, skipped };
}

// ------------------------------------------------------------------ .zip reading (stored + deflate)
const u16 = (b: Uint8Array, o: number) => b[o] | (b[o + 1] << 8);
const u32 = (b: Uint8Array, o: number) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;

async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Read a .zip archive. Directories are omitted; encrypted, multi-disk and ZIP64 archives are refused. */
export async function readZip(zip: Uint8Array): Promise<RawEntry[]> {
  let eocd = -1;
  for (let i = zip.length - 22; i >= Math.max(0, zip.length - 22 - 65535); i--) {
    if (u32(zip, i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("Not a .zip file");
  if (u16(zip, eocd + 4) !== 0 || u16(zip, eocd + 6) !== 0) throw new Error("Multi-part .zip archives are not supported");
  const count = u16(zip, eocd + 10);
  let p = u32(zip, eocd + 16);
  if (count === 0xffff || p === 0xffffffff) throw new Error("ZIP64 archives are not supported");
  if (count > MAX_ZIP_ENTRIES) throw new Error(`The archive has more than ${MAX_ZIP_ENTRIES} entries`);
  const out: RawEntry[] = [];
  let total = 0;
  for (let n = 0; n < count; n++) {
    if (p + 46 > zip.length || u32(zip, p) !== 0x02014b50) throw new Error("Damaged .zip file");
    const flags = u16(zip, p + 8), method = u16(zip, p + 10);
    const csize = u32(zip, p + 20), usize = u32(zip, p + 24);
    const nameLen = u16(zip, p + 28), extraLen = u16(zip, p + 30), commentLen = u16(zip, p + 32);
    const local = u32(zip, p + 42);
    const name = new TextDecoder().decode(zip.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extraLen + commentLen;
    if (name.endsWith("/")) continue;
    if (flags & 1) throw new Error("Encrypted .zip files are not supported");
    if (csize === 0xffffffff || usize === 0xffffffff) throw new Error("ZIP64 archives are not supported");
    total += usize;
    if (total > MAX_ZIP_TOTAL) throw new Error("The archive is too large to import (over 60 MB uncompressed)");
    if (local + 30 > zip.length || u32(zip, local) !== 0x04034b50) throw new Error("Damaged .zip file");
    const start = local + 30 + u16(zip, local + 26) + u16(zip, local + 28);
    const raw = zip.subarray(start, start + csize);
    if (usize > MAX_FILE_BYTES) { out.push({ path: name, data: new Uint8Array(MAX_FILE_BYTES + 1) }); continue; }
    let data: Uint8Array;
    if (method === 0) data = raw.slice();
    else if (method === 8) data = await inflateRaw(raw);
    else throw new Error(`Unsupported compression in ${name}`);
    if (data.length !== usize) throw new Error("Damaged .zip file");
    out.push({ path: name, data });
  }
  return out;
}

/** Summary line shown before and after an import. */
export function summarise(plan: ImportPlan): string {
  const f = plan.files.length, s = plan.skipped.length;
  return `${f} file${f === 1 ? "" : "s"} to import` + (s ? `, ${s} skipped` : "");
}
