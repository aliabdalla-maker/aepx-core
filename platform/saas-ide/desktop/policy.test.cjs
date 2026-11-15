"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const p = require("./policy.cjs");

const IDE = "https://ide.softwareequality.com";
const IDPS = p.idpOrigins(["https://login.softwareequality.com", "http://evil.example", "nonsense"]);

test("only the approved bare IDE origin loads", () => {
  assert.equal(p.ideOrigin("https://ide.softwareequality.com"), IDE);
  for (const bad of ["http://ide.softwareequality.com", "https://ide.softwareequality.com:8443",
    "https://evil.example", "https://u:p@ide.softwareequality.com", "https://ide.softwareequality.com/x",
    "https://ide.softwareequality.com/?a=1"]) {
    assert.throws(() => p.ideOrigin(bad), /approved/);
  }
});

test("idp list keeps https origins only", () => {
  assert.deepEqual(IDPS, ["https://login.softwareequality.com"]);
});

test("in-app navigation: IDE and IdP only", () => {
  assert.equal(p.decide(IDE + "/callback?code=1", IDE, IDPS), "allow");
  assert.equal(p.decide("https://login.softwareequality.com/authorize", IDE, IDPS), "allow");
  assert.equal(p.decide("https://evil.example/", IDE, IDPS), "deny");
  assert.equal(p.decide("file:///etc/passwd", IDE, IDPS), "deny");
  assert.equal(p.decide("javascript:alert(1)", IDE, IDPS), "deny");
});

test("payments and the website open in the system browser", () => {
  assert.equal(p.decide("https://checkout.stripe.com/c/pay/cs_test", IDE, IDPS), "external");
  assert.equal(p.decide("https://billing.stripe.com/p/session/x", IDE, IDPS), "external");
  assert.equal(p.decide("https://www.softwareequality.com/aepx/download", IDE, IDPS), "external");
  assert.equal(p.decide("https://checkout.stripe.com:444/", IDE, IDPS), "deny");
});

test("permissions: clipboard write from the IDE only", () => {
  assert.equal(p.permissionAllowed("clipboard-sanitized-write", IDE + "/", IDE), true);
  assert.equal(p.permissionAllowed("clipboard-sanitized-write", "https://evil.example/", IDE), false);
  for (const perm of ["media", "geolocation", "notifications", "openExternal"]) {
    assert.equal(p.permissionAllowed(perm, IDE + "/", IDE), false);
  }
});

test("production sign-in pages stay inside the app window", () => {
  const pkg = require("./package.json");
  const ide = p.ideOrigin(pkg.aepx.ideUrl);
  const idps = p.idpOrigins(pkg.aepx.idpOrigins);
  assert.equal(p.decide("https://auth.softwareequality.com/realms/aepx/protocol/openid-connect/auth?x=1", ide, idps), "allow");
  assert.equal(p.decide("https://ide.softwareequality.com/callback?code=x", ide, idps), "allow");
  assert.equal(p.decide("http://auth.softwareequality.com/", ide, idps), "deny");
});
