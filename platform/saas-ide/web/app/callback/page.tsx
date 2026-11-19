"use client";
import { useEffect, useState } from "react";
import { oidcManager } from "../../lib/auth";

export default function Callback() {
  const [status, setStatus] = useState("Completing sign-in…");
  useEffect(() => {
    oidcManager().signinRedirectCallback()
      .then(() => window.location.replace("/"))
      .catch(() => setStatus("Sign-in failed. Please try again."));
  }, []);
  return <main className="auth">
    <h1>AEP-X Agentic IDE</h1>
    <p role="status">{status}</p>
    <a href="/">Return to workspace</a>
  </main>;
}
