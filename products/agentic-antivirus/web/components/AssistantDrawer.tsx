"use client";
/**
 * The security assistant on every console page (playbook "assistant" 1.1.0).
 * Ask questions, or attach files, a whole folder, images or a camera photo: the control plane scans each one with
 * the detection engine, stores nothing, and only clean content reaches a model, as untrusted data.
 */
import { useEffect, useRef, useState, type DragEvent } from "react";
import { api, describeError } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { EngineChip } from "./AgentPanels";
import { Dictate, ReadAloud } from "./ui";

export const LIMITS = { files: 20, fileBytes: 10 * 1024 * 1024, totalBytes: 25 * 1024 * 1024 };

type Attachment = { file: File; path: string; preview?: string };
type FileReport = { name: string; size: number; sha256: string; type: string; verdict: string;
  detection: { title: string; severity: string } | null };
type Turn = { q: string; names: string[]; answer?: string; engine?: string; files?: FileReport[]; images?: number;
  citations?: string[]; error?: string };

/** Pure check used by the drawer and its tests: what can be added without breaking the server's limits. */
export function admit(current: Attachment[], incoming: Attachment[]): { ok: Attachment[]; rejected: string[] } {
  const ok = [...current];
  const rejected: string[] = [];
  let total = current.reduce((n, a) => n + a.file.size, 0);
  for (const a of incoming) {
    if (ok.length >= LIMITS.files) { rejected.push(`${a.path}: limit`); continue; }
    if (a.file.size > LIMITS.fileBytes) { rejected.push(`${a.path}: size`); continue; }
    if (total + a.file.size > LIMITS.totalBytes) { rejected.push(`${a.path}: total`); continue; }
    if (ok.some((x) => x.path === a.path && x.file.size === a.file.size)) continue;
    total += a.file.size;
    ok.push(a);
  }
  return { ok, rejected };
}

function toAttachments(files: FileList | File[]): Attachment[] {
  return Array.from(files).map((f) => ({
    file: f, path: (f as any).webkitRelativePath || f.name,
    preview: f.type.startsWith("image/") ? URL.createObjectURL(f) : undefined,
  }));
}

function Camera({ onShot, onClose }: { onShot: (f: File) => void; onClose: () => void }) {
  const { t } = useI18n();
  const video = useRef<HTMLVideoElement>(null);
  const fallback = useRef<HTMLInputElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live: MediaStream | null = null;
    if (!navigator.mediaDevices?.getUserMedia) { setErr(t("assistant.cameraUnavailable")); return; }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((s) => { live = s; setStream(s); if (video.current) video.current.srcObject = s; })
      .catch(() => setErr(t("assistant.cameraDenied")));
    return () => live?.getTracks().forEach((tr) => tr.stop());
  }, [t]);
  const capture = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")?.drawImage(v, 0, 0);
    c.toBlob((b) => {
      if (b) onShot(new File([b], `camera-${new Date().toISOString().replace(/[:.]/g, "-")}.jpg`, { type: "image/jpeg" }));
      stream?.getTracks().forEach((tr) => tr.stop());
      onClose();
    }, "image/jpeg", 0.85);
  };
  return (
    <div className="camera" role="group" aria-label={t("assistant.camera")}>
      {err ? <p className="banner warn" role="alert">{err}</p>
        : <video ref={video} autoPlay playsInline muted aria-label={t("assistant.cameraPreview")} />}
      <div className="row">
        {!err && <button className="primary" onClick={capture} disabled={!stream}>{t("assistant.capture")}</button>}
        {err && <>
          <input ref={fallback} type="file" accept="image/*" capture="environment" hidden
            onChange={(e) => { if (e.target.files?.[0]) onShot(e.target.files[0]); onClose(); }} />
          <button onClick={() => fallback.current?.click()}>{t("assistant.useDeviceCamera")}</button></>}
        <button onClick={onClose}>{t("common.cancel")}</button>
      </div>
    </div>);
}

export function AssistantDrawer() {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [att, setAtt] = useState<Attachment[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [camera, setCamera] = useState(false);
  const [drag, setDrag] = useState(false);
  const filesIn = useRef<HTMLInputElement>(null);
  const folderIn = useRef<HTMLInputElement>(null);
  const imagesIn = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (open) panel.current?.querySelector<HTMLElement>("textarea")?.focus(); }, [open]);
  useEffect(() => () => att.forEach((a) => a.preview && URL.revokeObjectURL(a.preview)), [att]);

  const add = (incoming: Attachment[]) => {
    const { ok, rejected } = admit(att, incoming);
    setAtt(ok);
    setNotes(rejected.length ? [t("assistant.rejected", { n: rejected.length, files: LIMITS.files,
      mb: LIMITS.fileBytes / 1048576, total: LIMITS.totalBytes / 1048576 })] : []);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault(); setDrag(false);
    if (e.dataTransfer.files.length) add(toAttachments(e.dataTransfer.files));
  };
  const close = () => { setOpen(false); setCamera(false); opener.current?.focus(); };

  const send = async () => {
    const question = q.trim();
    if (!question && !att.length) return;
    const turn: Turn = { q: question || t("assistant.defaultQuestion"), names: att.map((a) => a.path) };
    setBusy(true);
    try {
      if (att.length) {
        const form = new FormData();
        form.append("question", question);
        form.append("language", locale);
        att.forEach((a) => { form.append("files", a.file, a.file.name); form.append("paths", a.path); });
        const r = await api("/v1/assistant/ask-with-files", { form });
        Object.assign(turn, { answer: r.answer, engine: r.engine, files: r.files, images: r.images_sent_to_model });
      } else {
        const r = await api("/v1/assistant/ask", { body: { question, language: locale } });
        Object.assign(turn, { answer: r.answer, engine: r.engine, citations: r.citations });
      }
      setQ(""); setAtt([]); setNotes([]);
    } catch (e) { turn.error = describeError(e); }
    finally { setTurns((ts) => [...ts, turn]); setBusy(false); }
  };

  return (
    <>
      <button ref={opener} className="assistant-fab primary" aria-expanded={open} aria-controls="assistant-panel"
        onClick={() => (open ? close() : setOpen(true))}>{t("ai.assistant")}</button>
      {open && (
        <aside id="assistant-panel" ref={panel} className={`assistant-panel${drag ? " drag" : ""}`} aria-labelledby="assistant-title"
          onKeyDown={(e) => { if (e.key === "Escape") close(); }}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}>
          <header className="row">
            <h2 id="assistant-title">{t("ai.assistant")}</h2>
            <button onClick={close} aria-label={t("assistant.close")}>×</button>
          </header>
          <p className="hint">{t("assistant.hint")}</p>
          <ol className="assistant-log" aria-live="polite">
            {turns.map((x, i) => (
              <li key={i}>
                <p className="q">{x.q}{x.names.length > 0 && <span className="hint"> · {t("assistant.attachedCount", { n: x.names.length })}</span>}</p>
                {x.error && <p className="banner bad" role="alert">{x.error}</p>}
                {x.answer && <p>{x.answer} {x.engine && <EngineChip engine={x.engine} />}</p>}
                {x.answer && <ReadAloud text={x.answer} />}
                {!!x.images && <p className="hint">{t("assistant.imagesSent", { n: x.images })}</p>}
                {x.files && x.files.length > 0 && (
                  <table><caption className="hint">{t("assistant.scanReport")}</caption>
                    <thead><tr><th>{t("assistant.file")}</th><th>{t("assistant.type")}</th><th>{t("assistant.verdict")}</th></tr></thead>
                    <tbody>{x.files.map((f) => (
                      <tr key={f.sha256 + f.name}><td title={f.sha256}>{f.name}</td><td>{f.type}</td>
                        <td className={f.verdict === "malicious" ? "bad" : undefined}>
                          {t(`assistant.verdict.${f.verdict}`)}{f.detection ? `: ${f.detection.title}` : ""}</td></tr>))}
                    </tbody></table>)}
                {x.citations && x.citations.length > 0 && <p className="hint">{t("ai.citations")}: {x.citations.join(", ")}</p>}
              </li>))}
          </ol>
          {camera && <Camera onShot={(f) => add(toAttachments([f]))} onClose={() => setCamera(false)} />}
          {att.length > 0 && (
            <ul className="attachments" aria-label={t("assistant.attachments")}>
              {att.map((a) => (
                <li key={a.path + a.file.size}>
                  {a.preview ? <img src={a.preview} alt="" width={40} height={40} /> : null}
                  <span>{a.path}</span>
                  <button aria-label={t("assistant.remove", { name: a.path })}
                    onClick={() => setAtt(att.filter((x) => x !== a))}>×</button>
                </li>))}
            </ul>)}
          {notes.map((n, i) => <p key={i} className="banner warn" role="status">{n}</p>)}
          <div className="row">
            <input ref={filesIn} type="file" multiple hidden onChange={(e) => { if (e.target.files) add(toAttachments(e.target.files)); e.target.value = ""; }} />
            <input ref={folderIn} type="file" multiple hidden {...{ webkitdirectory: "", directory: "" } as any}
              onChange={(e) => { if (e.target.files) add(toAttachments(e.target.files)); e.target.value = ""; }} />
            <input ref={imagesIn} type="file" accept="image/*" multiple hidden
              onChange={(e) => { if (e.target.files) add(toAttachments(e.target.files)); e.target.value = ""; }} />
            <button onClick={() => filesIn.current?.click()}>{t("assistant.addFiles")}</button>
            <button onClick={() => folderIn.current?.click()}>{t("assistant.addFolder")}</button>
            <button onClick={() => imagesIn.current?.click()}>{t("assistant.addImages")}</button>
            <button onClick={() => setCamera(true)} aria-pressed={camera}>{t("assistant.camera")}</button>
          </div>
          <label htmlFor="assistant-q" className="hint">{t("ai.question")}</label>
          <textarea id="assistant-q" rows={3} value={q} placeholder={t("assistant.placeholder")} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} />
          <div className="row">
            <Dictate onText={(s) => setQ(s)} />
            <button className="primary" disabled={busy || (!q.trim() && !att.length)} onClick={send}>
              {busy ? t("common.working") : att.length ? t("assistant.scanAndAsk") : t("ai.ask")}</button>
          </div>
          <p className="hint">{t("assistant.privacy")}</p>
        </aside>)}
    </>);
}
