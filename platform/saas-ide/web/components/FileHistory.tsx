"use client";
import { useCallback, useEffect, useState } from "react";
import type { FileVersion, IdeApi } from "../lib/api";
import { ago } from "../lib/modules";

type Props = {
  api: IdeApi; project: string; path: string;
  onRestored: (path: string, content: string) => void; onStatus: (m: string) => void; onClose: () => void;
};

/** Version history for one file (spec §6): every save, delete and restore, with one-click restore. */
export default function FileHistory({ api, project, path, onRestored, onStatus, onClose }: Props) {
  const [versions, setVersions] = useState<FileVersion[]>([]);
  const load = useCallback(() => {
    api.history(project, path).then(setVersions).catch(e => onStatus(String((e as Error).message ?? e)));
  }, [api, project, path, onStatus]);
  useEffect(load, [load]);

  async function restore(v: number) {
    if (!window.confirm(`Restore ${path} to version ${v}? The current content stays in history.`)) return;
    try {
      const r = await api.restoreFile(project, path, v);
      onRestored(r.path, r.content); onStatus(`Restored ${path} (now version ${r.version})`); load();
    } catch (e) { onStatus(String((e as Error).message ?? e)); }
  }

  return <section className="history" aria-label={`History of ${path}`}>
    <header className="row"><strong className="small">History · {path}</strong><span className="spacer" />
      <button className="icon" aria-label="Close history" onClick={onClose}>×</button></header>
    {versions.length === 0 && <p className="muted small">No saved versions yet.</p>}
    <ol>{versions.map(v => <li key={v.version} className="row">
      <span className={"badge " + v.op}>v{v.version} {v.op}</span>
      <span className="muted small" title={v.created_at}>{ago(v.created_at)} · {v.author.slice(0, 18)} · {v.size} B</span>
      <span className="spacer" />
      {v.op !== "delete" && <button className="small" onClick={() => void restore(v.version)}>Restore</button>}
    </li>)}</ol>
  </section>;
}
