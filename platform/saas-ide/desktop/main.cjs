"use strict";
// AEP-X IDE desktop shell: a locked-down window onto the hosted web IDE. It holds no credentials of
// its own (the web app's OIDC session lives in a persistent, sandboxed partition) and exposes no
// Node APIs to the page. Plan, trial and ads are decided by the IDE backend exactly as on the web.
const path = require("node:path");
const { app, BrowserWindow, shell, session, Menu } = require("electron");
const policy = require("./policy.cjs");
const pkg = require("./package.json");

const IDE = policy.ideOrigin(process.env.AEPX_DESKTOP_URL || pkg.aepx.ideUrl);
const IDPS = policy.idpOrigins(pkg.aepx.idpOrigins);
const PARTITION = "persist:aepx";

if (!app.requestSingleInstanceLock()) app.quit();

function route(event, url) {
  const verdict = policy.decide(url, IDE, IDPS);
  if (verdict === "allow") return;
  if (event) event.preventDefault();
  if (verdict === "external") void shell.openExternal(url);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 960, minHeight: 600, show: false,
    title: "AEP-X Agentic IDE", backgroundColor: "#0b1020",
    webPreferences: {
      nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true,
      allowRunningInsecureContent: false, spellcheck: true, partition: PARTITION,
      devTools: !app.isPackaged,
    },
  });
  win.once("ready-to-show", () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    const verdict = policy.decide(url, IDE, IDPS);
    if (verdict !== "deny") void shell.openExternal(url);
    return { action: "deny" }; // never spawn extra app windows
  });
  win.webContents.on("will-navigate", route);
  win.webContents.on("will-redirect", route);
  win.webContents.on("will-attach-webview", (event) => event.preventDefault());
  // If the hosted IDE cannot be reached (offline, DNS, server down), show a branded screen that
  // retries automatically instead of an empty window. -3 is ERR_ABORTED (a normal redirect/stop).
  win.webContents.on("did-fail-load", (_event, code, _desc, url, isMainFrame) => {
    if (!isMainFrame || code === -3 || !String(url).startsWith(IDE)) return;
    void win.loadFile(path.join(__dirname, "offline.html"), { query: { target: IDE + "/" } });
    if (!win.isVisible()) win.show();
  });
  void win.loadURL(IDE + "/");
  return win;
}

app.on("second-instance", () => {
  const [win] = BrowserWindow.getAllWindows();
  if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
});

app.whenReady().then(() => {
  const ses = session.fromPartition(PARTITION);
  ses.setPermissionRequestHandler((wc, permission, callback) =>
    callback(policy.permissionAllowed(permission, wc.getURL(), IDE)));
  ses.setPermissionCheckHandler((wc, permission, origin) => policy.permissionAllowed(permission, origin, IDE));
  if (app.isPackaged) Menu.setApplicationMenu(Menu.buildFromTemplate([
    ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),
    { role: "editMenu" }, { role: "viewMenu" }, { role: "windowMenu" },
  ]));
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
