"use client";
import { useEffect, useRef, useState } from "react";
import { api, apiUrl } from "../lib/api";
import { useI18n } from "../lib/i18n";

type Providers = { google: { client_id: string } | null };
type GsiWindow = Window & { google?: { accounts: { id: {
  initialize(o: { client_id: string; login_uri?: string; ux_mode?: string;
    callback?: (r: { credential: string }) => void; use_fedcm_for_prompt?: boolean }): void;
  renderButton(el: HTMLElement, o: Record<string, unknown>): void; } } } };

const GSI = "https://accounts.google.com/gsi/client";

function loadGsi(): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as GsiWindow).google?.accounts?.id) return resolve();
    const s = document.createElement("script");
    s.src = GSI; s.async = true; s.onload = () => resolve(); s.onerror = () => reject(new Error("gsi"));
    document.head.appendChild(s);
  });
}

/** "Continue with Google". Shown only when the server has a Google client ID configured. Uses the
 *  redirect flow (ux_mode=redirect) plus FedCM instead of a popup, so desktop browsers that block
 *  third-party cookies or pop-ups no longer hang on a blank Google window. Google posts the verified
 *  ID token to the server login_uri (/v1/auth/oidc/callback), which establishes the session and lands
 *  the user on the console. `organisation` is accepted for API compatibility but is not carried through
 *  the redirect; a Google-created account's organisation defaults and can be renamed in settings. */
export function GoogleSignIn({ text = "continue_with" }: { organisation?: string; text?: string }) {
  const { t, locale } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const p = await api<Providers>("/v1/auth/providers");
        if (!p.google || !live) return;
        await loadGsi();
        const g = (window as GsiWindow).google!.accounts.id;
        g.initialize({ client_id: p.google.client_id, ux_mode: "redirect",
          login_uri: `${apiUrl()}/v1/auth/oidc/callback`, use_fedcm_for_prompt: true });
        if (box.current && live) {
          g.renderButton(box.current, { type: "standard", theme: "outline", size: "large", text, shape: "pill",
            logo_alignment: "left", width: Math.max(220, Math.min(box.current.clientWidth || 320, 400)), locale });
          setReady(true);
        }
      } catch { /* Google unreachable or not configured: the password form still works */ }
    })();
    return () => { live = false; };
  }, [locale, t, text]);

  return (
    <div className="google-signin">
      <div ref={box} />
      {ready && <p className="divider"><span>{t("auth.or")}</span></p>}
    </div>);
}
