const { app, BrowserWindow, shell, session } = require("electron");
const { URL } = require("node:url");
const APP_URL = process.env.AEPX_DESKTOP_URL || "https://ide.softwareequality.com";
const target = new URL(APP_URL);
if (target.protocol !== "https:" || target.username || target.password ||
    !["ide.softwareequality.com"].includes(target.hostname) ||
    target.port || target.pathname !== "/" || target.search || target.hash) {
  throw new Error("Only the approved HTTPS IDE origin is allowed");
}
app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 1440, height: 900,
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, partition: "persist:aepx" }
  });
  win.webContents.setWindowOpenHandler(({url}) => {
    try { const u = new URL(url); if (u.protocol === "https:" && u.hostname === target.hostname) {
      void shell.openExternal(url);
    }} catch (_) {}
    return {action:"deny"};
  });
  win.webContents.on("will-navigate", (event, url) => {
    const u = new URL(url);
    if (u.origin !== target.origin) event.preventDefault();
  });
  session.fromPartition("persist:aepx").setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  void win.loadURL(target.toString());
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
