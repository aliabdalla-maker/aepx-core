"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, session } from "../lib/api";
import { useI18n } from "../lib/i18n";

type Providers = { google: { client_id: string } | null };
type GsiWindow = Window & { google?: { accounts: { id: {
  initialize(o: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: string }): void;
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

/** "Continue with Google". Shown only when the server has a Google client ID configured. Google confirms the
 *  email address, so no verification email is needed. `organisation` names a new account's organisation. */
export function GoogleSignIn({ organisation = "", text = "continue_with" }: { organisation?: string; text?: string }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);
  const org = useRef(organisation);
  org.current = organisation;
  const [err, setErr] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const p = await api<Providers>("/v1/auth/providers");
        if (!p.google || !live) return;
        await loadGsi();
        const g = (window as GsiWindow).google!.accounts.id;
        g.initialize({ client_id: p.google.client_id, callback: async ({ credential }) => {
          setErr("");
          try {
            const r = await api<{ access_token: string }>("/v1/auth/oidc",
              { body: { id_token: credential, organisation: org.current, locale } });
            session.set(r.access_token);
            const me = await api("/v1/auth/me");
            if (me.tenants[0]) session.setTenant(me.tenants[0].tenant_id);
            router.replace("/");
          } catch { setErr(t("auth.google_failed")); }
        } });
        if (box.current && live) {
          g.renderButton(box.current, { type: "standard", theme: "outline", size: "large", text, shape: "pill",
            logo_alignment: "left", width: Math.max(220, Math.min(box.current.clientWidth || 320, 400)), locale });
          setReady(true);
        }
      } catch { /* Google unreachable or not configured: the password form still works */ }
    })();
    return () => { live = false; };
  }, [locale, router, t, text]);

  return (
    <div className="google-signin">
      <div ref={box} />
      {err && <p className="error" role="alert">{err}</p>}
      {ready && <p className="divider"><span>{t("auth.or")}</span></p>}
    </div>);
}
