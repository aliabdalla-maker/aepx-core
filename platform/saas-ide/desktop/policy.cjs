"use strict";
// Navigation policy for the desktop shell. Pure functions so it is unit-tested with node:test.
//
//  * The window may show only the approved IDE origin and the configured identity-provider origins
//    (OIDC sign-in redirects through the IdP and back).
//  * Payment pages (Stripe Checkout / Customer Portal) never load inside the app: they open in the
//    user's default browser, where the address bar and padlock are visible.
//  * Other https links open externally only if their host is on the allowlist; everything else is denied.
const { URL } = require("node:url");

const PAYMENT_HOSTS = new Set(["checkout.stripe.com", "billing.stripe.com"]);
const EXTERNAL_HOSTS = new Set(["softwareequality.com", "www.softwareequality.com", ...PAYMENT_HOSTS]);
const APPROVED_IDE_HOSTS = new Set(["ide.softwareequality.com"]);

function parseHttps(raw) {
  let u;
  try { u = new URL(raw); } catch { return null; }
  if (u.protocol !== "https:" || u.username || u.password) return null;
  return u;
}

/** Validates the IDE origin the window loads. Throws on anything but an approved bare https origin. */
function ideOrigin(raw) {
  const u = parseHttps(raw);
  if (!u || !APPROVED_IDE_HOSTS.has(u.hostname) || u.port || u.pathname !== "/" || u.search || u.hash) {
    throw new Error("Only the approved HTTPS IDE origin is allowed");
  }
  return u.origin;
}

/** Validates configured IdP origins (https, no credentials); invalid entries are dropped. */
function idpOrigins(list) {
  return (Array.isArray(list) ? list : []).map(parseHttps).filter(Boolean).map((u) => u.origin);
}

/**
 * Decides what to do with a navigation or window.open target.
 * Returns "allow" (load in the app window), "external" (system browser) or "deny".
 */
function decide(raw, ide, idps) {
  const u = parseHttps(raw);
  if (!u) return "deny";
  if (u.origin === ide || idps.includes(u.origin)) return "allow";
  if (EXTERNAL_HOSTS.has(u.hostname) && !u.port) return "external";
  return "deny";
}

/** Only clipboard writes are granted; camera, mic, geolocation, notifications etc. are denied. */
function permissionAllowed(permission, requestingUrl, ide) {
  const u = parseHttps(requestingUrl || "");
  return permission === "clipboard-sanitized-write" && !!u && u.origin === ide;
}

module.exports = { ideOrigin, idpOrigins, decide, permissionAllowed, PAYMENT_HOSTS };
