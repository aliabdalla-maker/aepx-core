import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { ApiError, encodePath, ensureWorkspace, ideApi, isSafeRelativePath, makeRequester, runActions } from "./api";
import { adsenseSettings, impressionAllowed, readConsent, shouldRenderAd, writeConsent } from "./ads";
import { QUICK_TASKS, splitResult, usageWidth } from "./agentResult";
import { buildTree, closeTab, isDirty, languageFor, markSaved, openTab, parsePlan, updateTab } from "./workspace";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("api client", () => {
  it("sends bearer token, tenant header and JSON body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(201, { id: "p1", name: "x", description: "" }));
    const api = ideApi(makeRequester("https://api.test", "tok", "alpha", fetchMock as unknown as typeof fetch));
    await api.createProject("x");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.test/api/v1/projects");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ Authorization: "Bearer tok", "X-Tenant-ID": "alpha", "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ name: "x", description: "" });
  });

  it("refuses to call without a token and surfaces backend detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(409, { detail: "Retry not permitted" }));
    await expect(makeRequester("", "", "t", fetchMock as unknown as typeof fetch)("/x")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).not.toHaveBeenCalled();
    const r = makeRequester("", "tok", "t", fetchMock as unknown as typeof fetch);
    await expect(r("/x", "POST")).rejects.toThrow("409: Retry not permitted");
  });

  it("encodes ids and paths and rejects traversal before any request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, {}));
    const api = ideApi(makeRequester("", "tok", "t", fetchMock as unknown as typeof fetch));
    await api.decide("a/b", true);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/agent-runs/a%2Fb/decision?approved=true");
    await expect(api.saveFile("p", "../etc/passwd", "x")).rejects.toThrow("Invalid file path");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(encodePath("src/my file.ts")).toBe("src/my%20file.ts");
    for (const bad of ["", "/abs", "a//b", "a/./b", "a\\b", "a/../b", "x".repeat(513)]) expect(isSafeRelativePath(bad)).toBe(false);
    expect(isSafeRelativePath("src/app/main.py")).toBe(true);
  });

  it("offers lifecycle actions that match supervisor transitions", () => {
    expect(runActions("awaiting_approval", 0)).toMatchObject({ decide: true, enqueue: false, cancel: true });
    expect(runActions("approved", 0)).toMatchObject({ decide: false, enqueue: true, requestTool: true });
    expect(runActions("failed", 1).retry).toBe(true);
    expect(runActions("failed", 2).retry).toBe(false);
    expect(runActions("succeeded", 0)).toEqual({ decide: false, approveAndRun: false, enqueue: false, cancel: false, retry: false, requestTool: false });
    expect(runActions("awaiting_approval", 0).approveAndRun).toBe(true);
  });
});

describe("workspace helpers", () => {
  it("detects editor languages", () => {
    expect(languageFor("a/b/main.py")).toBe("python");
    expect(languageFor("App.TSX")).toBe("typescript");
    expect(languageFor("Dockerfile")).toBe("dockerfile");
    expect(languageFor("README")).toBe("plaintext");
  });

  it("builds a folders-first sorted tree without duplicates", () => {
    const tree = buildTree(["z.py", "src/b.ts", "src/a.ts", "src/lib/c.ts", "a.md", "src/a.ts"]);
    expect(tree.map(n => n.name)).toEqual(["src", "a.md", "z.py"]);
    expect(tree[0].children?.map(n => n.name)).toEqual(["lib", "a.ts", "b.ts"]);
    expect(tree[0].children?.[0].children?.[0].path).toBe("src/lib/c.ts");
  });

  it("manages tabs, dirty state and close focus", () => {
    let tabs = openTab([], "a.py", "1");
    tabs = openTab(tabs, "b.py", "2");
    tabs = openTab(tabs, "a.py", "ignored");
    expect(tabs).toHaveLength(2);
    tabs = updateTab(tabs, "a.py", "changed");
    expect(isDirty(tabs[0])).toBe(true);
    expect(isDirty(markSaved(tabs, "a.py")[0])).toBe(false);
    expect(closeTab(tabs, "b.py", "b.py").active).toBe("a.py");
    expect(closeTab(tabs, "a.py", "b.py").active).toBe("b.py");
    expect(closeTab([tabs[0]], "a.py", "a.py").active).toBe("");
  });

  it("parses the supervisor plan JSON text", () => {
    const plan = JSON.stringify([{ agent: "architect", action: "design", goal: "Boundaries" }]);
    expect(parsePlan(plan)).toEqual([{ title: "architect · design", detail: "Boundaries" }]);
    expect(parsePlan("not json")).toEqual([{ title: "not json" }]);
    expect(parsePlan(null)).toEqual([]);
    expect(parsePlan({ steps: ["a"] })).toEqual([{ title: "a" }]);
  });
});

describe("web ads gating", () => {
  const live = adsenseSettings({ NEXT_PUBLIC_ADS_ENABLED: "true", NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR: "1234567890" });

  it("is off by default", () => {
    expect(shouldRenderAd(adsenseSettings({}), "sidebar", "granted")).toBe(false);
  });

  it("requires consent and a safe surface", () => {
    expect(shouldRenderAd(live, "sidebar", "granted")).toBe(true);
    expect(shouldRenderAd(live, "sidebar", "unknown")).toBe(false);
    expect(shouldRenderAd(live, "sidebar", "denied")).toBe(false);
    for (const s of ["editor", "approvals", "terminal"] as const)
      expect(shouldRenderAd({ ...live, slots: { [s]: "1234567890" } }, s, "granted")).toBe(false);
  });

  it("rejects AdMob unit IDs and malformed clients as web slots", () => {
    const admob = adsenseSettings({ NEXT_PUBLIC_ADS_ENABLED: "true", NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR: "ca-app-pub-2980680946304710/1032845563" });
    expect(shouldRenderAd(admob, "sidebar", "granted")).toBe(false);
    expect(shouldRenderAd({ ...live, client: "ca-app-pub-2980680946304710" }, "sidebar", "granted")).toBe(false);
  });

  it("thins impressions to the server-issued ad rate", () => {
    const shown = (rate: number) => Array.from({ length: 200 }, (_, i) => impressionAllowed(rate, i)).filter(Boolean).length;
    expect(shown(1)).toBe(200);            // trial / free: every opportunity
    expect(shown(0.05)).toBe(10);          // £4.99 subscriber: 1 in 20 = 95% fewer
    expect(shown(0)).toBe(0);
    expect(impressionAllowed(Number.NaN, 0)).toBe(false);
    expect(impressionAllowed(0.05, -1)).toBe(false);
  });

  it("treats unavailable storage as no consent", () => {
    expect(readConsent({ getItem: () => { throw new Error("blocked"); } })).toBe("unknown");
    expect(readConsent(undefined)).toBe("unknown");
    const store = new Map<string, string>();
    writeConsent({ setItem: (k, v) => void store.set(k, v) }, "granted");
    expect(readConsent({ getItem: k => store.get(k) ?? null })).toBe("granted");
  });

  it("stays consistent with monetization/ads-config.json", () => {
    const cfg = JSON.parse(readFileSync(join(__dirname, "..", "..", "monetization", "ads-config.json"), "utf8"));
    expect(cfg.adsense.client).toBe(adsenseSettings({}).client);
    expect(cfg.adsense.enabled).toBe(false);
    expect(cfg.admob.enabled).toBe(true); // owner chose the standard layout on 2026-11-15
    expect(cfg.admob.appId).toBe("ca-app-pub-2980680946304710~2617421798");
    expect(cfg.admob.adUnits).toHaveLength(6);
    for (const unit of cfg.admob.adUnits) {
      expect(unit.id).toMatch(/^ca-app-pub-2980680946304710\/\d{10}$/);
      expect(cfg.admob.allowedFormats).toContain(unit.format);
      expect(cfg.admob.allowedPlacements).toContain(unit.placement);
    }
    expect(new Set(cfg.admob.adUnits.map((u: { placement: string }) => u.placement)).size).toBe(6);
    expect(new Set(cfg.admob.adUnits.map((u: { id: string }) => u.id)).size).toBe(6);
  });
});

import { canApprove, canEdit, charsLeft, formatPence, providersFor, runtime, type MediaCapabilities } from "./media";

describe("Media Studio helpers", () => {
  const caps = {
    providers: { mock: { kinds: ["image", "music"], configured: true }, openai: { kinds: ["image", "script"], configured: true },
      runway: { kinds: ["video"], configured: false } },
    platforms: { x: { mode: "api", limit: 280, configured: true } },
    templates: [], approval_required: true, four_eyes: false,
  } as unknown as MediaCapabilities;
  it("formats cost estimates", () => {
    expect(formatPence(0)).toBe("free");
    expect(formatPence(40)).toBe("~40p");
    expect(formatPence(250)).toBe("~£2.50");
  });
  it("gates actions by role", () => {
    expect(canApprove("owner") && canApprove("admin")).toBe(true);
    expect(canApprove("editor")).toBe(false);
    expect(canEdit("editor")).toBe(true);
    expect(canEdit("viewer") || canEdit(undefined)).toBe(false);
  });
  it("lists only enabled providers for a kind, mock last", () => {
    expect(providersFor(caps, "image")).toEqual(["openai", "mock"]);
    expect(providersFor(caps, "video")).toEqual([]);
    expect(providersFor(null, "image")).toEqual([]);
  });
  it("counts characters per platform limit", () => {
    expect(charsLeft(caps, "x", "a".repeat(280))).toBe(0);
    expect(charsLeft(caps, "x", "a".repeat(281))).toBe(-1);
    expect(charsLeft(caps, "x", "👍")).toBe(279);
  });
  it("computes timeline runtime", () => {
    expect(runtime({ timeline: [{ shot_id: "a", start_s: 0, end_s: 5 }, { shot_id: "b", start_s: 5, end_s: 75 }] })).toBe("1:15");
    expect(runtime({ timeline: [] })).toBe("0:00");
  });
});

import { bundleIdFrom, nativeStore, transactionIdFrom } from "./nativeStore";

describe("iOS StoreKit bridge", () => {
  it("is detected only when the wrapper's handler exists", () => {
    expect(nativeStore(undefined)).toBeNull();
    expect(nativeStore({})).toBeNull();
    expect(nativeStore({ webkit: { messageHandlers: { aepxStore: { postMessage: "x" } } } })).toBeNull();
    const handler = { postMessage: () => undefined };
    expect(nativeStore({ webkit: { messageHandlers: { aepxStore: handler } } })).toBe(handler);
  });
  it("accepts only decimal transaction ids", () => {
    expect(transactionIdFrom({ originalTransactionId: "2000000123456789" })).toBe("2000000123456789");
    for (const bad of [null, {}, { originalTransactionId: 12 }, { originalTransactionId: "12a" },
      { originalTransactionId: "1".repeat(21) }]) expect(transactionIdFrom(bad)).toBeNull();
  });
  it("passes only well-formed bundle ids", () => {
    expect(bundleIdFrom({ bundleId: "com.equalitysoftware.aepx.ide" })).toBe("com.equalitysoftware.aepx.ide");
    expect(bundleIdFrom({ bundleId: "x'); alert(1)//" })).toBeUndefined();
    expect(bundleIdFrom(null)).toBeUndefined();
  });
});

describe("ensureWorkspace", () => {
  const ok = (body: unknown) => (async () => new Response(JSON.stringify(body), { status: 200 })) as unknown as typeof fetch;
  it("returns the personal workspace id from the API", async () => {
    const id = "u-" + "a".repeat(32);
    await expect(ensureWorkspace("https://ide.test", "tok", ok({ tenant_id: id }))).resolves.toBe(id);
  });
  it("rejects a malformed workspace id", async () => {
    await expect(ensureWorkspace("https://ide.test", "tok", ok({ tenant_id: "alpha" }))).rejects.toThrow();
  });
  it("surfaces API errors", async () => {
    const denied = (async () => new Response("{}", { status: 401 })) as unknown as typeof fetch;
    await expect(ensureWorkspace("https://ide.test", "tok", denied)).rejects.toThrow("401");
  });
});


describe("agent assistant", () => {
  it("splits answers into prose and file-tagged code blocks", () => {
    const answer = "Here is the API.\n\n`src/app.py`:\n```python\nprint('hi')\n```\nThen run it.\n```bash\nuvicorn app:app\n```\n```ts web/x.ts\nexport {};\n```";
    expect(splitResult(answer)).toEqual([
      { kind: "text", text: "Here is the API." },
      { kind: "code", lang: "python", code: "print('hi')", file: "src/app.py" },
      { kind: "text", text: "Then run it." },
      { kind: "code", lang: "bash", code: "uvicorn app:app" },
      { kind: "code", lang: "ts", code: "export {};", file: "web/x.ts" },
    ]);
  });

  it("never attaches unsafe paths and tolerates unclosed fences", () => {
    const blocks = splitResult("`../etc/passwd`:\n```\nx\n```\n```js /abs/y.js\nopen");
    expect(blocks.filter(b => b.kind === "code").every(b => !("file" in b))).toBe(true);
    expect(blocks[blocks.length - 1]).toMatchObject({ kind: "code", code: "open" });
  });

  it("clamps the usage bar and offers media and code quick tasks", () => {
    expect(usageWidth(140)).toBe("100%");
    expect(usageWidth(-5)).toBe("0%");
    expect(usageWidth(Number.NaN)).toBe("0%");
    const labels = QUICK_TASKS.map(q => q.label);
    expect(labels).toEqual(expect.arrayContaining(["REST API", "Soundtrack", "Film storyboard", "Social campaign"]));
  });

  it("calls the AI usage endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, { plan: "trial", agents_live: true }));
    const api = ideApi(makeRequester("https://api.test", "tok", "alpha", fetchMock as unknown as typeof fetch));
    await expect(api.aiUsage()).resolves.toMatchObject({ plan: "trial" });
    expect(fetchMock.mock.calls[0][0]).toBe("https://api.test/api/v1/ai-usage");
  });
});
