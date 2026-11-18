const test = require("node:test");
const assert = require("node:assert");
const { allowedInWindow } = require("../policy");
test("only bundled console and the control-plane origin load in the window", () => {
  assert.ok(allowedInWindow("file:///app/console/index.html", "https://softwareequality.com"));
  assert.ok(allowedInWindow("https://softwareequality.com/apps/agentic-antivirus/", "https://softwareequality.com"));
  assert.ok(!allowedInWindow("http://softwareequality.com/", "https://softwareequality.com"));
  assert.ok(!allowedInWindow("https://evil.example/", "https://softwareequality.com"));
  assert.ok(!allowedInWindow("javascript:alert(1)", "https://softwareequality.com"));
});
