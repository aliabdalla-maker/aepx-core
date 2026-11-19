"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { ideUrl, DEFAULT_IDE } = require("./url.js");

test("https IDE URLs are kept, everything else falls back", () => {
  assert.equal(ideUrl(undefined), DEFAULT_IDE);
  assert.equal(ideUrl("https://ide.example.org/workspace#x"), "https://ide.example.org/workspace");
  for (const bad of ["http://ide.example.org", "javascript:alert(1)", "file:///etc", "https://a:b@x.org", "%%%"]) {
    assert.equal(ideUrl(bad), DEFAULT_IDE);
  }
});

test("new-project links carry only known modules", () => {
  const { newProjectUrl, MODULES } = require("./url.js");
  assert.equal(MODULES.length, 9);
  assert.equal(newProjectUrl(undefined, "music"), "https://ide.softwareequality.com/?new=music");
  assert.equal(newProjectUrl("https://ide.example.org/app", "film"), "https://ide.example.org/app?new=film");
  assert.equal(newProjectUrl(undefined, "x&evil=1"), DEFAULT_IDE);
  assert.equal(newProjectUrl("http://bad", "sound"), "https://ide.softwareequality.com/?new=sound");
});
