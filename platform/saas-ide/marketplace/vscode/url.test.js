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
