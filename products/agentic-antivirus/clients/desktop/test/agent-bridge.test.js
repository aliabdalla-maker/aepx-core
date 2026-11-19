const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { makeHandler, agentPath, TOKEN_RE } = require("../agent-bridge");

const API = "https://api.softwareequality.com/apps/agentic-antivirus/api";
const unix = process.platform !== "win32";

function fakeAgent() {
  // Records its arguments and answers like aav-agent does (JSON on the last stdout line).
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "aavfake-"));
  const bin = path.join(dir, "aav-agent");
  fs.writeFileSync(bin, `#!/bin/sh
echo "$@" >> "${dir}/calls"
case "$*" in
  *" status"*) [ -f "${dir}/enrolled" ] && echo '{"device_id":"d1"}' && exit 0; echo "not enrolled" >&2; exit 2;;
  *" enrol "*) touch "${dir}/enrolled"; echo '{"device_id":"d1","tenant_id":"t1"}';;
  *" scan "*) echo '{"ok": true, "scanned": 12, "detections": 1, "errors": 0}';;
esac
`, { mode: 0o755 });
  return { bin, dir };
}

test("agent bridge is unavailable when no agent is bundled", async () => {
  assert.strictEqual(agentPath("/nonexistent"), null);
  const h = makeHandler({ bin: null, stateDir: "/tmp/x", apiBase: API });
  assert.deepStrictEqual(await h({ op: "status" }), { available: false });
});

test("enrol accepts only the configured control plane and a well-formed code", { skip: !unix }, async () => {
  const { bin, dir } = fakeAgent();
  let enrolled = 0;
  const h = makeHandler({ bin, stateDir: path.join(dir, "state"), apiBase: API, onEnrolled: () => enrolled++ });
  assert.strictEqual((await h({ op: "status" })).enrolled, false);
  assert.strictEqual((await h({ op: "enrol", url: "https://evil.example/api", token: "a".repeat(32) })).ok, false);
  assert.strictEqual((await h({ op: "enrol", url: API, token: "bad token; rm -rf /" })).ok, false);
  const ok = await h({ op: "enrol", url: API, token: "Abc_123-xyz.456789" });
  assert.strictEqual(ok.ok, true);
  assert.strictEqual(enrolled, 1);
  assert.strictEqual((await h({ op: "status" })).enrolled, true);
  const calls = fs.readFileSync(path.join(dir, "calls"), "utf8");
  assert.ok(calls.includes(`enrol --url ${API} --token Abc_123-xyz.456789`));
  assert.ok(!calls.includes("evil"));
});

test("scan returns the agent's result and only quick or full", { skip: !unix }, async () => {
  const { bin, dir } = fakeAgent();
  const h = makeHandler({ bin, stateDir: path.join(dir, "state"), apiBase: API });
  const r = await h({ op: "scan", type: "everything; whoami" });
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.result.scanned, 12);
  assert.ok(fs.readFileSync(path.join(dir, "calls"), "utf8").includes("scan --type quick"));
  assert.strictEqual((await h({ op: "nope" })).ok, false);
});

test("enrolment codes: URL-safe characters only", () => {
  assert.ok(TOKEN_RE.test("x".repeat(16)));
  assert.ok(!TOKEN_RE.test("short"));
  assert.ok(!TOKEN_RE.test("a b c d e f g h i j"));
});
