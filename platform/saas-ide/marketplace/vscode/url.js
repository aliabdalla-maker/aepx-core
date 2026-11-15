"use strict";
// Pure helpers (no vscode import) so they run under node:test.
const DEFAULT_IDE = "https://ide.softwareequality.com/";
const PRICING = "https://www.softwareequality.com/aepx#pricing";

/** The IDE URL must be https with no credentials; anything else falls back to the default. */
function ideUrl(configured) {
  try {
    const u = new URL(String(configured || DEFAULT_IDE));
    if (u.protocol !== "https:" || u.username || u.password) return DEFAULT_IDE;
    u.hash = "";
    return u.toString();
  } catch {
    return DEFAULT_IDE;
  }
}

module.exports = { DEFAULT_IDE, PRICING, ideUrl };
