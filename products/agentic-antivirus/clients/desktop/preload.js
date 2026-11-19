// The console gets only these calls; no Node APIs. The main process checks the caller's origin and arguments.
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("aavDesktop", {
  platform: process.platform,
  agent: (req) => ipcRenderer.invoke("aav:agent", req),
  retry: () => ipcRenderer.send("aav:retry"),
});
