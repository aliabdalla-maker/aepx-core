// Desktop shell: loads the hosted console (same build as the web/PWA). Hardened: context isolation,
// sandbox, no node integration, navigation restricted to the console and the control-plane origin.
const { app, BrowserWindow, shell, session } = require("electron");
const path = require("node:path");
const { allowedInWindow } = require("./policy");

const CONSOLE_URL = process.env.AAV_CONSOLE_URL || "https://api.softwareequality.com/apps/agentic-antivirus/";
const API_ORIGIN = new URL(CONSOLE_URL).origin;

function createWindow() {
  const win = new BrowserWindow({
    width: 1280, height: 860, title: "Agentic Antivirus",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: "deny" }; });
  win.webContents.on("will-navigate", (e, url) => { if (!allowedInWindow(url, API_ORIGIN)) { e.preventDefault(); shell.openExternal(url); } });
  win.loadURL(CONSOLE_URL);
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === "media")); // dictation only
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
