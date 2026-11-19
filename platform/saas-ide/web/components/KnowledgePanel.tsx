"use client";
import { useState } from "react";
import type { IdeApi } from "../lib/api";

type Props = { api: IdeApi | null; project: string; onStatus: (m: string) => void };
type Match = { key: string; title: string; excerpt: string; score: number };

export default function KnowledgePanel({ api, project, onStatus }: Props) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"lexical" | "vector">("lexical");
  const [matches, setMatches] = useState<Match[]>([]);
  const [busy, setBusy] = useState(false);

  if (!project) return <p className="muted">Open a project to manage its knowledge base.</p>;

  async function add() {
    if (!api || !title.trim() || !content.trim()) return;
    setBusy(true);
    try {
      const doc = await api.addKnowledge(project, title.trim(), content);
      let note = "";
      try { note = ` · ${(await api.indexKnowledge(project, doc.id)).chunks_indexed} chunks embedded`; }
      catch { note = " · vector indexing unavailable (lexical search still works)"; }
      setTitle(""); setContent(""); onStatus(`Added “${doc.title}”${note}`);
    } catch (e) { onStatus(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }

  async function search() {
    if (!api || query.trim().length < 2) return;
    setBusy(true);
    try {
      if (mode === "lexical") {
        const r = await api.searchKnowledge(project, query.trim());
        setMatches(r.matches.map(m => ({ key: m.id, title: m.title, excerpt: m.excerpt, score: m.score })));
      } else {
        const r = await api.vectorSearch(project, query.trim());
        setMatches(r.matches.map((m, i) => ({ key: m.document_id + i, title: m.document_id, excerpt: m.excerpt, score: m.score })));
      }
    } catch (e) { onStatus(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }

  return <div className="knowledge">
    <h4>Search project knowledge</h4>
    <div className="row">
      <input aria-label="Knowledge query" placeholder="e.g. tenant isolation" maxLength={200} value={query}
        onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === "Enter") void search(); }} />
      <select aria-label="Search mode" value={mode} onChange={e => setMode(e.target.value as "lexical" | "vector")}>
        <option value="lexical">Keyword</option><option value="vector">Semantic</option>
      </select>
      <button disabled={busy || query.trim().length < 2} onClick={() => void search()}>Search</button>
    </div>
    <ul className="matches">{matches.map(m => <li key={m.key}>
      <strong>{m.title}</strong> <span className="muted small">score {m.score.toFixed(3)}</span>
      <p>{m.excerpt}</p>
    </li>)}</ul>
    <details>
      <summary>Add a document</summary>
      <input aria-label="Document title" placeholder="Title" maxLength={160} value={title} onChange={e => setTitle(e.target.value)} />
      <textarea aria-label="Document content" rows={5} maxLength={20000} value={content}
        placeholder="Specs, ADRs, runbooks… (max 20,000 characters)" onChange={e => setContent(e.target.value)} />
      <button disabled={busy || !title.trim() || !content.trim()} onClick={() => void add()}>Add and index</button>
    </details>
  </div>;
}
