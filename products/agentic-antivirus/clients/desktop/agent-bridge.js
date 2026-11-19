// Runs the endpoint agent bundled with the desktop app so "Protect this computer" and "Scan this computer" work
// without a command line. Only the console's own origin can call it, and only with validated arguments.
const { execFile, spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const TOKEN_RE = /^[A-Za-z0-9_\-.]{16,256}$/;

function agentPath(resourcesPath) {
  const exe = path.join(resourcesPath || "", "agent", process.platform === "win32" ? "aav-agent.exe" : "aav-agent");
  return fs.existsSync(exe) ? exe : null;
}

function run(bin, args, timeoutMs) {
  return new Promise((resolve) => {
    execFile(bin, args, { timeout: timeoutMs, windowsHide: true, maxBuffer: 4 * 1024 * 1024 }, (err, stdout, stderr) => {
      const code = err ? (typeof err.code === "number" ? err.code : 1) : 0;
      let data = null;
      try { data = JSON.parse(String(stdout).trim().split("\n").pop() || "null"); } catch { /* not JSON */ }
      resolve({ code, data, error: code ? String(stderr || err.message).trim().slice(-400) : null });
    });
  });
}

/** Validates one request from the console and runs it. `apiBase` is the only control plane allowed. */
function makeHandler({ bin, stateDir, apiBase, onEnrolled }) {
  const base = ["--state", stateDir];
  return async (req) => {
    if (!bin) return { available: false };
    const op = req && req.op;
    if (op === "status") {
      const r = await run(bin, [...base, "status"], 30_000);
      return { available: true, enrolled: r.code === 0, status: r.data };
    }
    if (op === "enrol") {
      if (req.url !== apiBase) return { available: true, ok: false, error: "unexpected control plane address" };
      if (!TOKEN_RE.test(String(req.token || ""))) return { available: true, ok: false, error: "invalid enrolment code" };
      fs.mkdirSync(stateDir, { recursive: true });
      const r = await run(bin, [...base, "enrol", "--url", apiBase, "--token", req.token], 120_000);
      if (r.code === 0 && onEnrolled) onEnrolled();
      return { available: true, ok: r.code === 0, device: r.data, error: r.error };
    }
    if (op === "scan") {
      const type = req.type === "full" ? "full" : "quick";
      const r = await run(bin, [...base, "scan", "--type", type], type === "full" ? 6 * 3600_000 : 30 * 60_000);
      return { available: true, ok: r.code === 0 && !!(r.data && r.data.ok), result: r.data, error: r.error };
    }
    return { available: true, ok: false, error: "unknown operation" };
  };
}

/** Keeps `aav-agent run` going while the app is open (real-time protection and console commands). */
function keepRunning(bin, stateDir) {
  let child = null, stopped = false, delay = 5_000;
  const start = () => {
    if (stopped || !bin) return;
    child = spawn(bin, ["--state", stateDir, "run", "--interval", "10"], { windowsHide: true, stdio: "ignore" });
    const began = Date.now();
    child.on("exit", () => {
      child = null;
      if (stopped) return;
      delay = Date.now() - began > 60_000 ? 5_000 : Math.min(delay * 2, 300_000); // back off if it keeps failing
      setTimeout(start, delay);
    });
  };
  start();
  return () => { stopped = true; if (child) child.kill(); };
}

module.exports = { agentPath, makeHandler, keepRunning, TOKEN_RE };
