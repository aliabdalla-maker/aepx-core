import { describe, expect, it } from "vitest";
import { isRunnable, runHint, runSucceeded, runSummary } from "./run";

const ON = { enabled: true, languages: ["python", "node"], reason: "" };

describe("Run button", () => {
  it("only offers Run for Python and JavaScript files", () => {
    expect(isRunnable("src/main.py")).toBe(true);
    expect(isRunnable("web/app.mjs")).toBe(true);
    expect(isRunnable("README.md")).toBe(false);
    expect(isRunnable(undefined)).toBe(false);
  });
  it("explains every disabled state, including the server's reason", () => {
    expect(runHint({ signedIn: false, status: ON, path: "a.py", running: false })).toMatch(/Sign in/);
    expect(runHint({ signedIn: true, status: ON, path: "a.md", running: false })).toMatch(/Only Python/);
    expect(runHint({ signedIn: true, status: null, path: "a.py", running: false })).toMatch(/Checking/);
    expect(runHint({ signedIn: true, status: { enabled: false, languages: [], reason: "Running code is not switched on for this workspace yet." }, path: "a.py", running: false }))
      .toBe("Running code is not switched on for this workspace yet.");
    expect(runHint({ signedIn: true, status: ON, path: "a.py", running: true })).toBe("Running…");
    expect(runHint({ signedIn: true, status: ON, path: "a.py", running: false })).toBe("");
  });
  it("summarises real results without inventing success", () => {
    const base = { stdout: "", stderr: "", truncated: false, duration_ms: 420 };
    expect(runSummary({ ...base, exit_code: 0, timed_out: false, runtime: "runsc" })).toBe("exit 0 · 0.42 s · gVisor sandbox");
    expect(runSummary({ ...base, exit_code: null, timed_out: true, truncated: true })).toBe("stopped: time limit · 0.42 s · output truncated");
    expect(runSucceeded({ ...base, exit_code: 0, timed_out: false })).toBe(true);
    expect(runSucceeded({ ...base, exit_code: 1, timed_out: false })).toBe(false);
  });
});
