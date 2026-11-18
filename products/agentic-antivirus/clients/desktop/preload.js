// No Node APIs are exposed to the console; it talks to the control plane over HTTPS only.
const { contextBridge } = require("electron");
contextBridge.exposeInMainWorld("aavDesktop", { platform: process.platform, version: process.env.npm_package_version || "" });
