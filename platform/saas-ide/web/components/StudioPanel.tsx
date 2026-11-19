"use client";
import { useCallback, useEffect, useState } from "react";
import type { Requester } from "../lib/api";
import {
  canApprove, canEdit, charsLeft, formatPence, mediaApi, providersFor, runtime,
  type MediaCapabilities, type MediaJob, type MediaKind, type Platform, type SocialPost, type Storyboard,
} from "../lib/media";

type Props = {
  request: Requester; fetchAsset: (url: string) => Promise<{ objectUrl: string; type: string }>;
  project: string; role: string | undefined; onStatus: (m: string) => void;
};
type Section = "templates" | "generate" | "film" | "social";
const KINDS: MediaKind[] = ["image", "video", "music", "voice", "script"];
const PLATFORMS: Platform[] = ["linkedin", "x", "mastodon", "youtube", "tiktok", "instagram", "mock"];
const SECTIONS: [Section, string][] = [["templates", "Templates"], ["generate", "Generate"], ["film", "Film"], ["social", "Social"]];

/**
 * Media Studio: agentic music, voice, image, video and script generation, the film pipeline and social
 * publishing. Every paid generation and every public post needs an owner/admin approval.
 */
export default function StudioPanel({ request, fetchAsset, project, role, onStatus }: Props) {
  const [section, setSection] = useState<Section>("generate");
  const [caps, setCaps] = useState<MediaCapabilities | null>(null);
  const [jobs, setJobs] = useState<MediaJob[]>([]);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [previews, setPreviews] = useState<Record<string, { url: string; type: string }>>({});
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState<MediaKind>("image");
  const [provider, setProvider] = useState("");
  const [prompt, setPrompt] = useState("");
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const [postBody, setPostBody] = useState("");
  const [attach, setAttach] = useState("");
  const api = mediaApi(request);

  const fail = useCallback((e: unknown) => onStatus(e instanceof Error ? e.message : String(e)), [onStatus]);

  const reload = useCallback(async () => {
    if (!project) return;
    const client = mediaApi(request);
    try {
      const [c, j, p] = await Promise.all([client.capabilities(), client.jobs(project), client.posts(project)]);
      setCaps(c); setJobs(j); setPosts(p);
    } catch (e) { fail(e); }
  }, [project, request, fail]);

  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => () => Object.values(previews).forEach(p => URL.revokeObjectURL(p.url)), [previews]);
  useEffect(() => { setProvider(providersFor(caps, kind)[0] ?? ""); }, [caps, kind]);

  if (!project) return <p className="muted">Open a project to use the Media Studio.</p>;

  async function act<T>(label: string, fn: () => Promise<T>) {
    setBusy(true);
    try { await fn(); onStatus(label); await reload(); } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function preview(job: MediaJob) {
    try {
      const blob = await fetchAsset(`/api/v1/media-jobs/${encodeURIComponent(job.id)}/asset`);
      setPreviews(p => ({ ...p, [job.id]: { url: blob.objectUrl, type: blob.type } }));
    } catch (e) { fail(e); }
  }

  async function download(format: "edl" | "ffmpeg") {
    try {
      const b = await fetchAsset(`/api/v1/projects/${encodeURIComponent(project)}/storyboard/export?format=${format}`);
      const a = Object.assign(document.createElement("a"), { href: b.objectUrl, download: format === "edl" ? "film.edl" : "render.sh" });
      a.click();
      setTimeout(() => URL.revokeObjectURL(b.objectUrl), 1000);
    } catch (e) { fail(e); }
  }

  const editor = canEdit(role), approver = canApprove(role);
  const finished = jobs.filter(j => j.state === "succeeded");
  const left = charsLeft(caps, platform, postBody);
  const providers = providersFor(caps, kind);

  return <div className="studio">
    <div className="row" role="group" aria-label="Studio sections">
      {SECTIONS.map(([id, label]) => <button key={id} aria-pressed={section === id}
        className={section === id ? "active" : ""} onClick={() => setSection(id)}>{label}</button>)}
    </div>
    {caps && <p className="muted small">Nothing is generated or posted until an owner/admin approves it
      {caps.four_eyes ? " (and the approver must be someone else)" : ""}.</p>}

    {section === "templates" && <ul className="cards">
      {caps?.templates.map(t => <li key={t.id}>
        <strong>{t.title}</strong><p className="small">{t.description}</p>
        <button disabled={!editor || busy} onClick={() => void act(`Template “${t.title}” added`,
          () => api.applyTemplate(project, t.id))}>Add to project</button>
      </li>)}
    </ul>}

    {section === "generate" && <>
      <div className="row">
        <select aria-label="Media type" value={kind} onChange={e => setKind(e.target.value as MediaKind)}>
          {KINDS.map(k => <option key={k} value={k}>{k}</option>)}
        </select>
        <select aria-label="Provider" value={provider} onChange={e => setProvider(e.target.value)}>
          {providers.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
      {!providers.length && <p className="muted small">No provider is enabled for {kind}. An administrator can enable one (or “mock” for free demos).</p>}
      {kind === "video" && <select aria-label="Starting frame" value={attach} onChange={e => setAttach(e.target.value)}>
        <option value="">Starting frame (image job)…</option>
        {finished.filter(j => j.kind === "image").map(j => <option key={j.id} value={j.id}>{j.prompt.slice(0, 40)}</option>)}
      </select>}
      <textarea aria-label="Prompt" rows={3} maxLength={4000} placeholder={`Describe the ${kind}…`}
        value={prompt} onChange={e => setPrompt(e.target.value)} />
      <button className="primary" disabled={!editor || busy || !provider || !prompt.trim()} onClick={() => void act(
        "Proposed: waiting for approval", async () => {
          await api.createJob(project, kind, provider, prompt.trim(), kind === "video" && attach ? { image_job_id: attach } : {});
          setPrompt("");
        })}>Propose job</button>
      <ul className="jobs" aria-label="Media jobs">{jobs.map(j => <li key={j.id}>
        <div><span className={"badge " + j.state}>{j.state}</span> <strong>{j.kind}</strong> · {j.provider} · {formatPence(j.estimate_pence)}</div>
        <p className="small">{j.prompt}</p>
        {j.error && <p className="error small">{j.error}</p>}
        {j.result_text && <pre className="small">{j.result_text}</pre>}
        {j.result_url && <a href={j.result_url} target="_blank" rel="noopener noreferrer">Open result</a>}
        {previews[j.id]?.type.startsWith("image/") && <img src={previews[j.id].url} alt={`Generated: ${j.prompt}`} />}
        {previews[j.id]?.type.startsWith("audio/") && <audio controls src={previews[j.id].url} />}
        <div className="row">
          {j.state === "proposed" && approver && <>
            <button disabled={busy} onClick={() => void act("Approved", () => api.decideJob(j.id, true))}>Approve ({formatPence(j.estimate_pence)})</button>
            <button disabled={busy} onClick={() => void act("Rejected", () => api.decideJob(j.id, false))}>Reject</button></>}
          {j.state === "approved" && editor && <button className="primary" disabled={busy}
            onClick={() => void act("Generation finished", () => api.runJob(j.id))}>Run</button>}
          {j.state === "running" && <button disabled={busy} onClick={() => void act("Status refreshed", () => api.refreshJob(j.id))}>Check status</button>}
          {j.has_asset && !previews[j.id] && <button onClick={() => void preview(j)}>Preview</button>}
        </div>
      </li>)}</ul>
    </>}

    {section === "film" && <>
      <button disabled={busy} onClick={() => void api.storyboard(project).then(setBoard).catch(fail)}>Load storyboard</button>
      {board && <div className="storyboard">
        <h4>{board.title} <span className="muted small">· {board.scenes.length} scenes · {runtime(board)}</span></h4>
        <p className="small">{board.logline}</p>
        <ol>{board.scenes.map(sc => <li key={sc.id}><strong>{sc.title}</strong>
          <ul>{sc.shots.map(sh => <li key={sh.id} className="small">{sh.id}: {sh.description} ({sh.duration_s}s){" "}
            {editor && <button disabled={busy} onClick={() => { setSection("generate"); setKind("image"); setPrompt(sh.description); }}>
              Make key frame</button>}</li>)}</ul></li>)}</ol>
        <div className="row">
          <button onClick={() => void download("edl")}>Export EDL</button>
          <button onClick={() => void download("ffmpeg")}>Export ffmpeg script</button>
        </div>
      </div>}
      <p className="muted small">Edit <code>media/storyboard.json</code> in the editor, or add the “Film / video pipeline” template.</p>
    </>}

    {section === "social" && <>
      <div className="row">
        <select aria-label="Platform" value={platform} onChange={e => setPlatform(e.target.value as Platform)}>
          {PLATFORMS.map(p => <option key={p} value={p}>{p}{caps?.platforms[p]?.mode === "export" ? " (upload package)" : ""}
            {caps && !caps.platforms[p]?.configured ? " · not enabled" : ""}</option>)}
        </select>
        <select aria-label="Attach media" value={attach} onChange={e => setAttach(e.target.value)}>
          <option value="">No media</option>
          {finished.map(j => <option key={j.id} value={j.id}>{j.kind}: {j.prompt.slice(0, 30)}</option>)}
        </select>
      </div>
      <textarea aria-label="Post text" rows={4} value={postBody} onChange={e => setPostBody(e.target.value)} />
      <p className={"small " + (left < 0 ? "error" : "muted")} aria-live="polite">{left} characters left</p>
      <button className="primary" disabled={!editor || busy || !postBody.trim() || left < 0} onClick={() => void act(
        "Draft saved: waiting for approval", async () => {
          await api.createPost(project, platform, postBody.trim(), attach ? [attach] : []); setPostBody("");
        })}>Save draft</button>
      <ul className="jobs" aria-label="Social posts">{posts.map(p => <li key={p.id}>
        <div><span className={"badge " + p.state}>{p.state}</span> <strong>{p.platform}</strong>{p.mode === "export" ? " · upload package" : ""}</div>
        <p className="small">{p.body}</p>
        {p.error && <p className="error small">{p.error}</p>}
        {p.external_url && <a href={p.external_url} target="_blank" rel="noopener noreferrer">View post</a>}
        <div className="row">
          {p.state === "draft" && approver && <>
            <button disabled={busy} onClick={() => void act("Post approved", () => api.decidePost(p.id, true))}>Approve</button>
            <button disabled={busy} onClick={() => void act("Post rejected", () => api.decidePost(p.id, false))}>Reject</button></>}
          {p.state === "approved" && editor && <button className="primary" disabled={busy}
            onClick={() => void act(p.mode === "export" ? "Upload package ready" : "Published", () => api.publishPost(p.id))}>
            {p.mode === "export" ? "Create upload package" : "Publish now"}</button>}
        </div>
      </li>)}</ul>
    </>}
  </div>;
}
