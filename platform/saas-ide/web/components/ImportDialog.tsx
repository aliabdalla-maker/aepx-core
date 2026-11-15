"use client";
// Import files, a folder or a .zip into the open project. Files are checked in the browser, then
// saved one at a time through the normal save endpoint, so each import is audited and versioned
// and the server's role rules still apply per file.
import { useState } from "react";
import type { IdeApi } from "../lib/api";
import { planImport, readZip, summarise, type ImportPlan, type RawEntry } from "../lib/importer";

type Props = {
  api: IdeApi; project: string; existing: Set<string>; onClose: () => void; onStatus: (m: string) => void;
  onImported: (files: { path: string; content: string }[]) => void;
};

async function fromFiles(list: FileList): Promise<{ entries: RawEntry[]; zipped: boolean }> {
  const files = [...list];
  if (files.length === 1 && /\.zip$/i.test(files[0].name)) {
    return { entries: await readZip(new Uint8Array(await files[0].arrayBuffer())), zipped: true };
  }
  const entries = await Promise.all(files.map(async f => ({
    path: (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name,
    data: f.size > 1_000_000 ? new Uint8Array(1_000_001) : new Uint8Array(await f.arrayBuffer()),
  })));
  return { entries, zipped: false };
}

export default function ImportDialog({ api, project, existing, onClose, onStatus, onImported }: Props) {
  const [entries, setEntries] = useState<RawEntry[]>([]);
  const [zipped, setZipped] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [prefix, setPrefix] = useState("");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{ done: number; failed: { path: string; reason: string }[] } | null>(null);
  const [running, setRunning] = useState(false);
  const plan: ImportPlan = planImport(entries, existing, { overwrite, prefix, stripRoot: zipped });

  async function choose(list: FileList | null) {
    setError(""); setProgress(null);
    if (!list?.length) return;
    try { const r = await fromFiles(list); setEntries(r.entries); setZipped(r.zipped); }
    catch (e) { setEntries([]); setError(e instanceof Error ? e.message : String(e)); }
  }

  async function run() {
    if (!plan.files.length || running) return;
    setRunning(true);
    const failed: { path: string; reason: string }[] = [];
    const saved: { path: string; content: string }[] = [];
    for (const f of plan.files) {
      try { await api.saveFile(project, f.path, f.content); saved.push(f); }
      catch (e) { failed.push({ path: f.path, reason: e instanceof Error ? e.message : String(e) }); }
      setProgress({ done: saved.length + failed.length, failed: [...failed] });
    }
    onImported(saved);
    onStatus(`Imported ${saved.length} file${saved.length === 1 ? "" : "s"}` + (failed.length ? `, ${failed.length} failed` : ""));
    setRunning(false);
  }

  return <div className="modal-backdrop" role="presentation" onClick={e => { if (e.target === e.currentTarget && !running) onClose(); }}>
    <section className="modal import-dialog" role="dialog" aria-modal="true" aria-label="Import files">
      <h2>Import into this project</h2>
      <p className="muted small">Text files up to 1 MB each, up to 300 per import. Binary files, node_modules and .git are skipped.</p>
      <div className="import-pickers">
        <label className="button">Files…<input type="file" multiple hidden onChange={e => void choose(e.target.files)} /></label>
        <label className="button">Folder…<input type="file" hidden onChange={e => void choose(e.target.files)}
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)} /></label>
        <label className="button">.zip archive…<input type="file" accept=".zip,application/zip" hidden onChange={e => void choose(e.target.files)} /></label>
      </div>
      <label className="small">Into folder (optional) <input value={prefix} maxLength={120} placeholder="e.g. imported"
        onChange={e => setPrefix(e.target.value)} /></label>
      <label className="small"><input type="checkbox" checked={overwrite} onChange={e => setOverwrite(e.target.checked)} /> Replace existing files</label>
      {error && <p className="warn" role="alert">{error}</p>}
      {entries.length > 0 && <>
        <p role="status"><strong>{summarise(plan)}</strong>{zipped ? " (from .zip)" : ""}</p>
        <details><summary>Files ({plan.files.length})</summary>
          <ul className="import-list">{plan.files.slice(0, 200).map(f => <li key={f.path}>{f.path}</li>)}</ul></details>
        {plan.skipped.length > 0 && <details><summary>Skipped ({plan.skipped.length})</summary>
          <ul className="import-list">{plan.skipped.slice(0, 200).map(s => <li key={s.path + s.reason}>{s.path} — <span className="muted">{s.reason}</span></li>)}</ul></details>}
      </>}
      {progress && <p role="status">Saved {progress.done - progress.failed.length} of {plan.files.length}
        {progress.failed.length > 0 && <span className="warn"> · {progress.failed.length} failed: {progress.failed.slice(0, 3).map(f => `${f.path} (${f.reason})`).join("; ")}</span>}</p>}
      <div className="modal-actions">
        <button onClick={onClose} disabled={running}>{progress && !running ? "Done" : "Cancel"}</button>
        <button className="primary" disabled={!plan.files.length || running || Boolean(progress && !running)} onClick={() => void run()}>
          {running ? "Importing…" : `Import ${plan.files.length} file${plan.files.length === 1 ? "" : "s"}`}</button>
      </div>
    </section>
  </div>;
}
