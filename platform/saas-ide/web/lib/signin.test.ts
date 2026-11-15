import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import {
  DEFAULT_AUTH_OPTIONS, PANEL_TEXT, accountUrl, fetchAuthOptions, forgotPasswordUrl, panelStateFromError,
  parseAuthOptions, releaseLabel, saveHint, signinArgs,
} from "./signin";

const AUTH = "https://ide.softwareequality.com/auth/realms/aepx/";

describe("auth options", () => {
  it("accepts only booleans and falls back to e-mail only", () => {
    expect(parseAuthOptions(null)).toEqual(DEFAULT_AUTH_OPTIONS);
    expect(parseAuthOptions({ google: "yes", github: true, password_reset: true })).toEqual(
      { google: false, github: true, password_reset: true, registration: true, mfa: false });
  });
  it("never shows provider buttons when the API is down or errors", async () => {
    expect(await fetchAuthOptions("https://api", vi.fn().mockRejectedValue(new Error("offline")))).toEqual(DEFAULT_AUTH_OPTIONS);
    expect(await fetchAuthOptions("https://api", vi.fn().mockResolvedValue(new Response("x", { status: 503 })))).toEqual(DEFAULT_AUTH_OPTIONS);
    const ok = vi.fn().mockResolvedValue(new Response(JSON.stringify({ google: true, password_reset: true }), { status: 200 }));
    expect((await fetchAuthOptions("https://api", ok)).google).toBe(true);
    expect(ok).toHaveBeenCalledWith("https://api/api/v1/auth-options", { credentials: "omit" });
  });
});

describe("links", () => {
  it("builds Keycloak reset and account URLs", () => {
    expect(forgotPasswordUrl(AUTH, "aepx-ide-browser")).toBe(
      "https://ide.softwareequality.com/auth/realms/aepx/login-actions/reset-credentials?client_id=aepx-ide-browser");
    expect(accountUrl(AUTH, "signing-in")).toBe("https://ide.softwareequality.com/auth/realms/aepx/account/#/security/signingin");
    expect(accountUrl(AUTH, "linked-accounts")).toMatch(/#\/security\/linked-accounts$/);
    expect(accountUrl(AUTH, "device-activity")).toMatch(/#\/security\/device-activity$/);
  });
  it("maps buttons to authorisation parameters", () => {
    expect(signinArgs("email")).toEqual({});
    expect(signinArgs("create")).toEqual({ prompt: "create" });
    expect(signinArgs("google")).toEqual({ extraQueryParams: { kc_idp_hint: "google" } });
  });
});

describe("panel states", () => {
  it("distinguishes denied, unavailable and failed from empty", () => {
    expect(panelStateFromError(new ApiError(403, "Forbidden"))).toBe("denied");
    expect(panelStateFromError(new ApiError(401, "Unauthorized"))).toBe("denied");
    expect(panelStateFromError(new ApiError(503, "down"))).toBe("unavailable");
    expect(panelStateFromError(new TypeError("Failed to fetch"))).toBe("unavailable");
    expect(panelStateFromError(new ApiError(500, "boom"))).toBe("failed");
    expect(PANEL_TEXT.denied).not.toBe(PANEL_TEXT.empty);
  });
  it("explains a disabled Save", () => {
    expect(saveHint({ signedIn: false, hasFile: false, dirty: false })).toMatch(/Sign in/);
    expect(saveHint({ signedIn: true, hasFile: false, dirty: false })).toMatch(/Open a file/);
    expect(saveHint({ signedIn: true, hasFile: true, dirty: false })).toBe("No unsaved changes.");
  });
  it("labels the release and flags web/API drift", () => {
    expect(releaseLabel(undefined, null)).toEqual({ text: "", drift: false });
    expect(releaseLabel("0f9044c1234", "0F9044C")).toEqual({ text: "build 0f9044c", drift: false });
    expect(releaseLabel("0f9044c", "abcdef0")).toEqual({ text: "web 0f9044c · api abcdef0", drift: true });
    expect(releaseLabel("not-a-sha", "<b>")).toEqual({ text: "", drift: false });
  });
});
