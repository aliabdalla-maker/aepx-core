"use client";
import { useEffect } from "react";
import { oidcManager } from "../../lib/auth";

/** Hidden iframe target for automatic silent token renewal. Renders nothing. */
export default function SilentRenew() {
  useEffect(() => { void oidcManager().signinSilentCallback().catch(() => undefined); }, []);
  return null;
}
