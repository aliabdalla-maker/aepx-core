const test = require("node:test");
const assert = require("node:assert");
const { allowedInWindow } = require("../policy");
test("only bundled console and the control-plane origin load in the window", () => {
  assert.ok(allowedInWindow("file:///app/console/index.html", "https://api.softwareequality.com"));
  assert.ok(allowedInWindow("https://api.softwareequality.com/apps/agentic-antivirus/", "https://api.softwareequality.com"));
  assert.ok(!allowedInWindow("http://api.softwareequality.com/", "https://api.softwareequality.com"));
  assert.ok(!allowedInWindow("https://evil.example/", "https://api.softwareequality.com"));
  assert.ok(!allowedInWindow("javascript:alert(1)", "https://api.softwareequality.com"));
});
