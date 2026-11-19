"use client";
// Signed-out home: every way in that actually works on this deployment, and nothing that doesn't.
// Provider buttons appear only when the API reports them configured (GET /api/v1/auth-options).
import type { AuthOptions } from "../lib/signin";

type Kind = "email" | "create" | "google" | "github";
type Props = { configured: boolean; options: AuthOptions; forgotUrl: string; onSignIn: (kind: Kind) => void };

export default function SignedOutWelcome({ configured, options, forgotUrl, onSignIn }: Props) {
  if (!configured) {
    return <div className="welcome">
      <h2>Welcome to AEP-X</h2>
      <p className="muted">Sign-in is not set up on this deployment yet, so the workspace can’t open.</p>
    </div>;
  }
  return <div className="welcome">
    <h2>Welcome to AEP-X</h2>
    <p className="muted">Sign in to open your projects, run the agent crew and keep a full audit trail.</p>
    <div className="signin-actions">
      {options.google && <button className="primary" onClick={() => onSignIn("google")}>Continue with Google</button>}
      {options.github && <button onClick={() => onSignIn("github")}>Continue with GitHub</button>}
      <button className={options.google ? "" : "primary"} onClick={() => onSignIn("email")}>Sign in with e-mail</button>
      {options.registration && <button onClick={() => onSignIn("create")}>Create an account</button>}
    </div>
    <p className="small">
      {options.password_reset
        ? <a href={forgotUrl}>Forgot your password?</a>
        : <span className="muted">Forgot your password? Password reset by e-mail isn’t available yet — contact us via <a href="https://softwareequality.com">softwareequality.com</a>.</span>}
    </p>
    <p className="small muted">
      By continuing you agree to the <a href="https://softwareequality.com/terms.html">Terms</a> and{" "}
      <a href="https://softwareequality.com/aepx-ide-privacy.html">Privacy notice</a>.
    </p>
  </div>;
}
