import { describe, expect, it } from "vitest";
import { MAX_FILES, isBinary, normalisePath, planImport, readZip, stripCommonRoot, summarise } from "./importer";

const enc = (s: string) => new TextEncoder().encode(s);
// Built with Python zipfile: a "repo-main/" folder with a deflated app.py, a stored README,
// node_modules/x.js and a binary logo.png.
const ZIP = "UEsDBBQAAAAAAAAAIQAAAAAAAAAAAAAAAAAKAAAAcmVwby1tYWluL1BLAwQUAAAACAB7oW9dchVspBYAAAAsAQAAFAAAAHJlcG8tbWFpbi9zcmMvYXBwLnB5KyjKzCvRUMpIzcnJV9LkKhjl4uYCAFBLAwQUAAAAAAB7oW9d9MahhwcAAAAHAAAAEwAAAHJlcG8tbWFpbi9SRUFETUUubWQjIERlbW8KUEsDBBQAAAAIAHuhb12DFtyMAwAAAAEAAAAbAAAAcmVwby1tYWluL25vZGVfbW9kdWxlcy94LmpzqwAAUEsDBBQAAAAAAHuhb10+ApZuCwAAAAsAAAASAAAAcmVwby1tYWluL2xvZ28ucG5niVBORw0KGgoAAABQSwECFAMUAAAAAAAAACEAAAAAAAAAAAAAAAAACgAAAAAAAAAAAAAAgAEAAAAAcmVwby1tYWluL1BLAQIUAxQAAAAIAHuhb11yFWykFgAAACwBAAAUAAAAAAAAAAAAAACAASgAAAByZXBvLW1haW4vc3JjL2FwcC5weVBLAQIUAxQAAAAAAHuhb130xqGHBwAAAAcAAAATAAAAAAAAAAAAAACAAXAAAAByZXBvLW1haW4vUkVBRE1FLm1kUEsBAhQDFAAAAAgAe6FvXYMW3IwDAAAAAQAAABsAAAAAAAAAAAAAAIABqAAAAHJlcG8tbWFpbi9ub2RlX21vZHVsZXMveC5qc1BLAQIUAxQAAAAAAHuhb10+ApZuCwAAAAsAAAASAAAAAAAAAAAAAACAAeQAAAByZXBvLW1haW4vbG9nby5wbmdQSwUGAAAAAAUABQBEAQAAHwEAAAAA";
const zipBytes = () => Uint8Array.from(Buffer.from(ZIP, "base64"));

describe("paths", () => {
  it("normalises separators and joins a target folder", () => {
    expect(normalisePath(".\\src\\./a.ts")).toBe("src/a.ts");
    expect(normalisePath("a.ts", "/imports/")).toBe("imports/a.ts");
  });
  it("strips one wrapping folder only when every entry shares it", () => {
    expect(stripCommonRoot(["r/a", "r/b/c"])).toEqual(["a", "b/c"]);
    expect(stripCommonRoot(["r/a", "s/b"])).toEqual(["r/a", "s/b"]);
    expect(stripCommonRoot(["a", "r/b"])).toEqual(["a", "r/b"]);
  });
});

describe("planImport", () => {
  it("imports text, skips binaries, ignored folders, unsafe paths and existing files", () => {
    const plan = planImport([
      { path: "src/a.ts", data: enc("export {}") },
      { path: "img.png", data: new Uint8Array([137, 80, 0, 1]) },
      { path: "node_modules/x/index.js", data: enc("x") },
      { path: "../escape.txt", data: enc("x") },
      { path: "README.md", data: enc("# old") },
      { path: "big.txt", data: new Uint8Array(1_000_001).fill(65) },
    ], new Set(["README.md"]), { overwrite: false });
    expect(plan.files.map(f => f.path)).toEqual(["src/a.ts"]);
    const reasons = Object.fromEntries(plan.skipped.map(s => [s.path, s.reason]));
    expect(reasons["img.png"]).toMatch(/binary/);
    expect(reasons["node_modules/x/index.js"]).toMatch(/ignored/);
    expect(reasons["../escape.txt"]).toMatch(/unsafe/);
    expect(reasons["README.md"]).toMatch(/already exists/);
    expect(reasons["big.txt"]).toMatch(/1 MB/);
  });
  it("replaces existing files only when asked, and caps one import", () => {
    expect(planImport([{ path: "README.md", data: enc("new") }], new Set(["README.md"]), { overwrite: true }).files)
      .toEqual([{ path: "README.md", content: "new" }]);
    const many = Array.from({ length: MAX_FILES + 5 }, (_, i) => ({ path: `f${i}.txt`, data: enc("x") }));
    const plan = planImport(many, new Set(), { overwrite: false });
    expect(plan.files).toHaveLength(MAX_FILES);
    expect(summarise(plan)).toBe(`${MAX_FILES} files to import, 5 skipped`);
  });
  it("detects invalid UTF-8 as binary", () => {
    expect(isBinary(new Uint8Array([0xff, 0xfe, 0x41]))).toBe(true);
    expect(isBinary(enc("héllo"))).toBe(false);
  });
});

describe("readZip", () => {
  it("reads stored and deflated entries from a real archive", async () => {
    const entries = await readZip(zipBytes());
    expect(entries.map(e => e.path)).toEqual(["repo-main/src/app.py", "repo-main/README.md", "repo-main/node_modules/x.js", "repo-main/logo.png"]);
    expect(new TextDecoder().decode(entries[0].data)).toBe('print("hello")\n'.repeat(20));
    const plan = planImport(entries, new Set(), { overwrite: false, stripRoot: true });
    expect(plan.files.map(f => f.path)).toEqual(["src/app.py", "README.md"]);
    expect(plan.skipped.map(s => s.reason)).toEqual(expect.arrayContaining([expect.stringMatching(/ignored/), expect.stringMatching(/binary/)]));
  });
  it("rejects non-zip and damaged input", async () => {
    await expect(readZip(enc("not a zip at all, definitely not"))).rejects.toThrow("Not a .zip file");
    const z = zipBytes(); z[z.length - 22 + 16] ^= 0xff; // corrupt central-directory offset
    await expect(readZip(z)).rejects.toThrow(/Damaged|ZIP64/);
  });
});
