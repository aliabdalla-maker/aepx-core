"use strict";
// Pure helpers (no vscode import) so they run under node:test.
const DEFAULT_IDE = "https://ide.softwareequality.com/";
const PRICING = "https://www.softwareequality.com/aepx#pricing";

/** The IDE modules a new project can start in (mirrors GET /api/v1/ide-modules). */
const MODULES = [
  { id: "software", label: "Software IDE", detail: "Code, tests, CI/CD and deployment plans" },
  { id: "sound", label: "Sound IDE", detail: "Dialogue, effects, restoration, mixing and mastering" },
  { id: "music", label: "Music IDE", detail: "Composition, arrangement and AI music briefs" },
  { id: "film", label: "Movie & Film IDE", detail: "Scripts, storyboards, shot lists and edits" },
  { id: "animation", label: "Animation IDE", detail: "Scenes, keyframes, rigs and render scripts" },
  { id: "sdk", label: "SDK IDE", detail: "OpenAPI design, client libraries and docs" },
  { id: "social", label: "Social Media IDE", detail: "Campaigns, calendars and approved posts" },
  { id: "multimedia", label: "Multimedia IDE", detail: "Cross-media productions" },
  { id: "media", label: "Media IDE", detail: "Asset catalogue, metadata and rights" },
];

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

/** Opens the IDE's new-project dialog with a module preselected; unknown modules are ignored. */
function newProjectUrl(configured, moduleId) {
  const u = new URL(ideUrl(configured));
  if (MODULES.some(m => m.id === moduleId)) u.searchParams.set("new", moduleId);
  return u.toString();
}

module.exports = { DEFAULT_IDE, PRICING, MODULES, ideUrl, newProjectUrl };
