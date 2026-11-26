// Desktop shell: loads the hosted console (same build as the web/PWA) and runs the bundled endpoint agent for
// "Protect this computer" and "Scan this computer". Hardened: context isolation, sandbox, no node integration,
// navigation restricted to the console origin, and the agent bridge only answers that origin.
const { app, BrowserWindow, shell, session, ipcMain } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { allowedInWindow } = require("./policy");
const { agentPath, makeHandler, keepRunning } = require("./agent-bridge");

const CONSOLE_URL = process.env.AAV_CONSOLE_URL || "https://api.softwareequality.com/apps/agentic-antivirus/";
const API_ORIGIN = new URL(CONSOLE_URL).origin;
const API_BASE = new URL("api", CONSOLE_URL.endsWith("/") ? CONSOLE_URL : CONSOLE_URL + "/").href.replace(/\/$/, "");

let win = null;
let stopAgent = null;

// One window: opening the app again (Start menu, dock, desktop icon) focuses it instead of doing nothing.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); } });
}

function log(msg) {
  try { fs.appendFileSync(path.join(app.getPath("userData"), "desktop.log"), `${new Date().toISOString()} ${msg}\n`); }
  catch { /* logging must never stop the app */ }
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280, height: 860, minWidth: 360, minHeight: 480, title: "Agentic Antivirus", show: false,
    backgroundColor: "#eef1f4",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.once("ready-to-show", () => win.show());
  setTimeout(() => { if (win && !win.isVisible()) win.show(); }, 4000); // never stay invisible
  win.webContents.setWindowOpenHandler(({ url }) => {
    // "Continue with Google" opens Google Identity Services as a popup that posts the credential
    // back to its opener via postMessage. Shoving it to the external browser severs that channel,
    // so sign-in never completes in the desktop app. Keep Google's own auth popups in-app as child
    // windows (opener preserved); send everything else to the system browser.
    let host = "";
    try { host = new URL(url).host; } catch { /* malformed url -> treat as external */ }
    if (host === "accounts.google.com" || host.endsWith(".accounts.google.com")) {
      return {
        action: "allow",
        overrideBrowserWindowOptions: {
          width: 500, height: 650, title: "Sign in with Google", autoHideMenuBar: true,
          webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
        },
      };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => { if (!allowedInWindow(url, API_ORIGIN)) { e.preventDefault(); shell.openExternal(url); } });
  // No connection (offline, firewall, captive portal): show a page with a retry button instead of a blank window.
  win.webContents.on("did-fail-load", (_e, code, desc, url, isMain) => {
    if (!isMain || code === -3) return; // -3: navigation replaced
    log(`load failed ${code} ${desc} ${url}`);
    win.loadFile(path.join(__dirname, "offline.html"), { query: { url: CONSOLE_URL, reason: desc } });
  });
  win.webContents.on("render-process-gone", (_e, d) => { log(`renderer gone: ${d.reason}`); win.reload(); });
  win.on("closed", () => { win = null; });
  win.loadURL(CONSOLE_URL);
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === "media")); // dictation only
  const bin = agentPath(process.resourcesPath);
  const stateDir = path.join(app.getPath("userData"), "agent");
  const startAgent = () => { if (!stopAgent) stopAgent = keepRunning(bin, stateDir); };
  const handle = makeHandler({ bin, stateDir, apiBase: API_BASE, onEnrolled: startAgent });
  ipcMain.handle("aav:agent", (event, req) => {
    try {
      if (new URL(event.senderFrame.url).origin !== API_ORIGIN) return { available: false };
    } catch { return { available: false }; }
    return handle(req);
  });
  ipcMain.on("aav:retry", () => { if (win) win.loadURL(CONSOLE_URL); });
  // Already enrolled on an earlier run: resume real-time protection straight away.
  if (bin) handle({ op: "status" }).then((r) => { if (r.enrolled) startAgent(); });
  log(`started ${app.getVersion()} agent=${bin ? "bundled" : "not bundled"}`);
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on("before-quit", () => { if (stopAgent) stopAgent(); });
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
