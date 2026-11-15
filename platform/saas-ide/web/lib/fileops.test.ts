import { describe, expect, it } from "vitest";
import { applyMoveToFiles, applyMoveToTabs, movedPath, renameError, searchFiles } from "./fileops";

describe("rename and move", () => {
  it("maps a file or every file in a folder, and nothing else", () => {
    expect(movedPath("lib/a.py", "lib", "pkg")).toBe("pkg/a.py");
    expect(movedPath("lib", "lib", "pkg")).toBe("pkg");
    expect(movedPath("library/a.py", "lib", "pkg")).toBeNull();
  });
  it("keeps tabs and unsaved edits attached to moved files", () => {
    const moved = [{ from: "a.py", to: "src/a.py" }];
    expect(applyMoveToTabs([{ path: "a.py", content: "edited", saved: "old" }], moved))
      .toEqual([{ path: "src/a.py", content: "edited", saved: "old" }]);
    expect(applyMoveToFiles([{ path: "a.py", content: "x" }, { path: "b.py", content: "y" }], moved).map(f => f.path))
      .toEqual(["src/a.py", "b.py"]);
  });
  it("validates targets the same way the server does", () => {
    const existing = ["a.py", "b.py", "dir/c.py", "dir/sub/d.py"];
    expect(renameError("a.py", "b.py", existing)).toBe("b.py already exists.");
    expect(renameError("a.py", "a.py", existing)).toMatch(/current name/);
    expect(renameError("dir", "dir/inner", existing)).toMatch(/into itself/);
    expect(renameError("a.py", "../x.py", existing)).toMatch(/relative path/);
    expect(renameError("a.py", "  ", existing)).toBe("Enter a name.");
    expect(renameError("dir", "lib", existing)).toBe("");
  });
});

describe("project search", () => {
  const files = [{ path: "src/app.py", content: "import os\nprint('Hello')\n" }, { path: "README.md", content: "# hello app" }];
  it("finds names and lines, case-insensitively, with line numbers", () => {
    const { hits } = searchFiles(files, "hello");
    expect(hits).toEqual([{ path: "README.md", line: 1, text: "# hello app" }, { path: "src/app.py", line: 2, text: "print('Hello')" }]);
    expect(searchFiles(files, "app").hits[0]).toEqual({ path: "README.md", line: 1, text: "# hello app" });
    expect(searchFiles(files, "app").hits.some(h => h.path === "src/app.py" && h.line === 0)).toBe(true);
  });
  it("ignores one-letter queries and caps results", () => {
    expect(searchFiles(files, "a").hits).toEqual([]);
    const many = [{ path: "x.txt", content: "match\n".repeat(500) }];
    const r = searchFiles(many, "match", 50);
    expect(r.hits).toHaveLength(50); expect(r.truncated).toBe(true);
  });
});
