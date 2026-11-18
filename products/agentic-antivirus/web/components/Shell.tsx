"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, describeError, session } from "../lib/api";
import { LOCALES, localeName, useI18n } from "../lib/i18n";
import { formatDateTime } from "../lib/format";

const NAV: [string, string][] = [["/", "nav.dashboard"], ["/approvals", "nav.actions"], ["/incidents", "nav.incidents"],
  ["/alerts", "nav.alerts"], ["/devices", "nav.devices"], ["/quarantine", "nav.quarantine"], ["/policies", "nav.policies"],
  ["/ddos", "nav.ddos"], ["/integrations", "nav.integrations"], ["/files", "nav.files"]];
const NAV2: [string, string][] = [["/settings", "nav.settings"], ["/billing", "nav.billing"], ["/audit", "nav.audit"],
  ["/help", "nav.help"], ["/privacy", "nav.privacy"]];

const THEME_KEY = "aav.theme";

export function useTheme(): [string, (t: string) => void] {
  const [theme, setTheme] = useState("system");
  useEffect(() => {
    try { setTheme(window.localStorage.getItem(THEME_KEY) ?? "system"); } catch { /* ignore */ }
  }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  return [theme, (t: string) => { setTheme(t); try { window.localStorage.setItem(THEME_KEY, t); } catch { /* ignore */ } }];
}

export type Entitlement = { state: "trial" | "paid" | "expired"; trial_days_left: number; paid_until: string | null;
  ad_rate: number; console_access: boolean; protection_enabled: boolean };

export function Shell({ children, pending }: { children: ReactNode; pending?: number }) {
  const { t, locale, setLocale } = useI18n();
  const [theme, setTheme] = useTheme();
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [ent, setEnt] = useState<Entitlement | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!session.token()) { router.replace("/login"); return; }
    api("/v1/auth/me").then((m) => {
      setMe(m);
      if (!session.tenant() && m.tenants[0]) session.setTenant(m.tenants[0].tenant_id);
      return api<Entitlement>("/v1/licence").then(setEnt);
    }).catch((e) => { setErr(describeError(e)); if ((e as any).status === 401) { session.clear(); router.replace("/login"); } });
  }, [router]);

  const logout = async () => {
    try { await api("/v1/auth/logout", { method: "POST" }); } catch { /* already gone */ }
    session.clear();
    router.replace("/login");
  };

  const link = ([href, key]: [string, string]) => (
    <Link key={href} href={href} aria-current={path === href ? "page" : undefined}>
      {t(key)}{href === "/approvals" && pending ? <span className="count" aria-label={`${pending} waiting`}>{pending}</span> : null}
    </Link>);

  return (
    <>
      <a className="skip" href="#main">{t("a11y.skip")}</a>
      <div className="frame">
        <nav className="rail" aria-label="Primary">
          <div className="brand"><img src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/icons/icon.svg`} alt="" width={28} height={28} />{t("app.name")}</div>
          {NAV.map(link)}
          <div className="group" />
          {NAV2.map(link)}
        </nav>
        <div>
          <main id="main" className="main" tabIndex={-1}>
            <div className="topbar">
              {me && me.tenants.length > 1 && (
                <label style={{ margin: 0 }}><span className="hint">Organisation</span>
                  <select value={session.tenant() ?? ""} onChange={(e) => { session.setTenant(e.target.value); location.reload(); }}>
                    {me.tenants.map((x: any) => <option key={x.tenant_id} value={x.tenant_id}>{x.name}</option>)}
                  </select></label>)}
              <label style={{ margin: 0 }}><span className="hint">{t("settings.language")}</span>
                <select value={locale} onChange={(e) => setLocale(e.target.value)}>
                  {LOCALES.map((l) => <option key={l} value={l} lang={l}>{localeName(l, l)} ({l})</option>)}
                </select></label>
              <label style={{ margin: 0 }}><span className="hint">{t("settings.theme")}</span>
                <select value={theme} onChange={(e) => setTheme(e.target.value)}>
                  <option value="system">System</option><option value="light">{t("settings.theme.light")}</option>
                  <option value="dark">{t("settings.theme.dark")}</option>
                  <option value="high_contrast">{t("settings.theme.high_contrast")}</option>
                </select></label>
              {me && <span>{me.email}</span>}
              <button onClick={logout}>{t("auth.logout")}</button>
            </div>
            {ent?.state === "trial" && <p className="banner">{t("billing.trial", { days: ent.trial_days_left })} <Link href="/billing">{t("billing.subscribe")}</Link></p>}
            {ent?.state === "paid" && ent.paid_until && <p className="banner">{t("billing.paid", { date: formatDateTime(ent.paid_until, locale) })}</p>}
            {ent?.state === "expired" && <p className="banner warn">{t("billing.expired")} <Link href="/billing">{t("billing.subscribe")}</Link></p>}
            {err && <p className="banner warn" role="alert">{err}</p>}
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
