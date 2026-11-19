// Self-host Monaco: copy the AMD build into public/ so the editor never loads from a third-party CDN
// (works under a strict CSP and on networks that block jsDelivr). Runs before `next dev` / `next build`.
import { cpSync, existsSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(dirname(require.resolve("monaco-editor/package.json")), "min", "vs");
const target = join(web, "public", "monaco", "vs");

if (!existsSync(source)) {
  console.error(`monaco-editor AMD build not found at ${source}`);
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });
console.log(`Monaco copied to ${target}`);
