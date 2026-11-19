"use client";
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
  const [state, setState] = useState<AgentResult | null>(null);
  const [busy, setBusy] = useState<"" | "enrol" | "quick" | "full">("");
  const [msg, setMsg] = useState("");
  const agent = desktop()?.agent;

  useEffect(() => { if (agent) agent({ op: "status" }).then(setState).catch(() => setState({ available: false })); }, [agent]);
  if (!agent || !state?.available) return null;

  const protect = async () => {
    setBusy("enrol"); setMsg("");
    try {
      const t = await api<{ token: string }>("/v1/enrollment-tokens", { body: { max_uses: 1, expires_hours: 1 } });
      const r = await agent({ op: "enrol", url: apiUrl(), token: t.token });
      if (!r.ok) throw new Error(r.error || "enrolment failed");
      setState(await agent({ op: "status" }));
      setMsg("This computer is protected. Real-time scanning runs while Agentic Antivirus is open.");
      onChange?.();
    } catch (e) { setMsg(`Could not protect this computer: ${(e as Error).message}`); }
    finally { setBusy(""); }
  };
  const scan = async (type: "quick" | "full") => {
    setBusy(type); setMsg(type === "full" ? "Scanning every drive. This can take a long time." : "Scanning Downloads, Desktop and temporary files…");
    const r = await agent({ op: "scan", type });
    setBusy("");
    if (!r.ok) { setMsg(`The scan did not finish: ${r.result?.reason || r.error || "unknown error"}`); return; }
    const x = r.result!;
    setMsg(x.detections
      ? `${x.detections} threat${x.detections > 1 ? "s" : ""} found in ${x.scanned} files. See Alerts and Approvals to review them.`
      : `No new threats found in ${x.scanned} files.${x.errors ? ` ${x.errors} files could not be read.` : ""}`);
    onChange?.();
  };

  return (
    <section className="banner" aria-labelledby="this-computer">
      <h2 id="this-computer" style={{ marginTop: 0 }}>This computer</h2>
      {state.enrolled ? (
        <div className="row">
          <button className="primary" disabled={!!busy} onClick={() => scan("quick")}>{busy === "quick" ? "Scanning…" : "Scan this computer"}</button>
          <button disabled={!!busy} onClick={() => scan("full")}>{busy === "full" ? "Scanning…" : "Full scan"}</button>
        </div>
      ) : (
        <>
          <p>Turn on protection to scan files on this computer and watch for ransomware and credential theft.</p>
          <button className="primary" disabled={!!busy} onClick={protect}>{busy === "enrol" ? "Turning on…" : "Protect this computer"}</button>
        </>
      )}
      {msg && <p role="status">{msg}</p>}
    </section>);
}
