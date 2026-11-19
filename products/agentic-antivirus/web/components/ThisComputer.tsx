"use client";
import { useI18n } from "../lib/i18n";
import { useEffect, useState } from "react";
import { api, apiUrl } from "../lib/api";

type AgentResult = { available: boolean; enrolled?: boolean; ok?: boolean; error?: string | null;
  result?: { scanned: number; detections: number; errors: number; reason?: string } };
type Desktop = { agent?: (req: Record<string, unknown>) => Promise<AgentResult> };

function desktop(): Desktop | undefined {
  return typeof window === "undefined" ? undefined : (window as unknown as { aavDesktop?: Desktop }).aavDesktop;
}

/** In the desktop app: protect and scan this computer with the bundled agent, no command line needed. */
export function ThisComputer({ onChange }: { onChange?: () => void }) {
  const { t } = useI18n();
  const [state, setState] = useState<AgentResult | null>(null);
  const [busy, setBusy] = useState<"" | "enrol" | "quick" | "full">("");
  const [msg, setMsg] = useState("");
  const agent = desktop()?.agent;

  useEffect(() => { if (agent) agent({ op: "status" }).then(setState).catch(() => setState({ available: false })); }, [agent]);
  if (!agent || !state?.available) return null;

  const protect = async () => {
    setBusy("enrol"); setMsg("");
    try {
      const tok = await api<{ token: string }>("/v1/enrollment-tokens", { body: { max_uses: 1, expires_hours: 1 } });
      const r = await agent({ op: "enrol", url: apiUrl(), token: tok.token });
      if (!r.ok) throw new Error(r.error || "enrolment failed");
      setState(await agent({ op: "status" }));
      setMsg(t("thisComputer.protected"));
      onChange?.();
    } catch (e) { setMsg(t("thisComputer.protectFailed", { error: (e as Error).message })); }
    finally { setBusy(""); }
  };
  const scan = async (type: "quick" | "full") => {
    setBusy(type); setMsg(type === "full" ? t("thisComputer.scanningFull") : t("thisComputer.scanningQuick"));
    const r = await agent({ op: "scan", type });
    setBusy("");
    if (!r.ok) { setMsg(t("thisComputer.scanFailed", { error: r.result?.reason || r.error || t("common.unknown") })); return; }
    const x = r.result!;
    setMsg(x.detections
      ? t("thisComputer.found", { n: x.detections, files: x.scanned })
      : t("thisComputer.clean", { files: x.scanned }) + (x.errors ? " " + t("thisComputer.unreadable", { n: x.errors }) : ""));
    onChange?.();
  };

  return (
    <section className="banner" aria-labelledby="this-computer">
      <h2 id="this-computer" style={{ marginTop: 0 }}>{t("ui.this_computer")}</h2>
      {state.enrolled ? (
        <div className="row">
          <button className="primary" disabled={!!busy} onClick={() => scan("quick")}>{busy === "quick" ? "Scanning…" : "Scan this computer"}</button>
          <button disabled={!!busy} onClick={() => scan("full")}>{busy === "full" ? t("thisComputer.scanning") : t("thisComputer.fullScan")}</button>
        </div>
      ) : (
        <>
          <p>{t("ui.turn_on_protection_to_scan_files")}</p>
          <button className="primary" disabled={!!busy} onClick={protect}>{busy === "enrol" ? "Turning on…" : "Protect this computer"}</button>
        </>
      )}
      {msg && <p role="status">{msg}</p>}
    </section>);
}
