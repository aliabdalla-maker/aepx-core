"use client";
import { useEffect, useState } from "react";
import type { IdeApi, IdeModule, Project } from "../lib/api";
import { availableModules, plannedModules } from "../lib/modules";

type Props = { api: IdeApi; initial?: string; onCreated: (p: Project) => void; onClose: () => void; onStatus: (m: string) => void };

/** New-project dialog: pick one of the specialised IDEs (spec §2-4) that share the same platform. */
export default function ModuleLauncher({ api, initial, onCreated, onClose, onStatus }: Props) {
  const [modules, setModules] = useState<IdeModule[]>([]);
  const [choice, setChoice] = useState(initial || "software");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.modules().then(setModules).catch(e => onStatus(String((e as Error).message ?? e))); }, [api, onStatus]);

  async function create() {
    if (!name.trim()) return;
    setBusy(true);
    try { onCreated(await api.createProject(name.trim().slice(0, 120), "", choice)); }
    catch (e) { onStatus(String((e as Error).message ?? e)); }
    finally { setBusy(false); }
  }

  const available = availableModules(modules);
  useEffect(() => {
    if (modules.length && !available.some(m => m.id === choice)) setChoice("software");
  }, [modules, available, choice]);
  const planned = plannedModules(modules);
  return <div className="modal-backdrop" role="presentation" onClick={onClose}>
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="launcher-title" onClick={e => e.stopPropagation()}
      onKeyDown={e => { if (e.key === "Escape") onClose(); }}>
      <h2 id="launcher-title">New project</h2>
      <label className="field">Project name
        <input autoFocus maxLength={120} value={name} onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") void create(); }} placeholder="e.g. Launch film" />
      </label>
      <fieldset className="module-grid">
        <legend>Choose an IDE</legend>
        {available.map(m => <label key={m.id} className={"module-card" + (choice === m.id ? " active" : "")}>
          <input type="radio" name="module" value={m.id} checked={choice === m.id} onChange={() => setChoice(m.id)} />
          <strong>{m.name}</strong>
          <span className="muted small">{m.summary}</span>
          <span className="small crew">{m.crew.map(c => c.agent).join(" · ")}</span>
        </label>)}
      </fieldset>
      {planned.length > 0 && <details className="planned">
        <summary>On the roadmap ({planned.length})</summary>
        <p className="muted small">{planned.map(m => m.name).join(" · ")}</p>
      </details>}
      <div className="row end">
        <button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || !name.trim()} onClick={() => void create()}>Create project</button>
      </div>
    </div>
  </div>;
}
