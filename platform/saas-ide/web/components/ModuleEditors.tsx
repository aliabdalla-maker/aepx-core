"use client";
/* Visual editors for the module files. Each one edits the open file's text, so Save, history,
   ACL and the audit trail work exactly as for code. Exports download in the browser. */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  addOperation, download, editorFor, encodeMidi, encodeWav, midiToHz, normaliseCatalog, normaliseScene,
  normaliseSession, normaliseSong, operations, parseMdTable, parseSpec, peaks, pythonClient, renderClip,
  sceneToHtml, searchAssets, serializeMdTable, shotsFrom, stateAt, toEdl, toSrt, typescriptClient,
  upsertKeyframe, type AudioClip, type EditorKind, type Scene,
} from "../lib/editors";

type Props = {
  path: string; content: string; onChange: (text: string) => void; onStatus: (m: string) => void;
  onSaveFile?: (path: string, content: string) => Promise<void>;
};

export function hasVisualEditor(path: string): boolean { return editorFor(path) !== null; }

export default function ModuleEditor(outer: Props) {
  const kind = editorFor(outer.path) as EditorKind;
  // Undo/redo for visual edits (per file, kept while the file is open).
  const past = useRef<string[]>([]), future = useRef<string[]>([]);
  const [, bump] = useState(0);
  useEffect(() => { past.current = []; future.current = []; bump(n => n + 1); }, [outer.path]);
  const props: Props = { ...outer, onChange: text => {
    if (text === outer.content) return;
    past.current = [...past.current.slice(-99), outer.content]; future.current = [];
    outer.onChange(text); bump(n => n + 1);
  } };
  const undo = () => { const prev = past.current.pop(); if (prev === undefined) return; future.current.push(outer.content); outer.onChange(prev); bump(n => n + 1); };
  const redo = () => { const next = future.current.pop(); if (next === undefined) return; past.current.push(outer.content); outer.onChange(next); bump(n => n + 1); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z" || t?.closest("input,textarea,select")) return;
      e.preventDefault(); if (e.shiftKey) redo(); else undo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const view = {
    music: <MusicEditor {...props} />, sound: <SoundEditor {...props} />,
    storyboard: <TableEditor {...props} kind="storyboard" />, calendar: <TableEditor {...props} kind="calendar" />,
    animation: <AnimationEditor {...props} />, openapi: <OpenApiEditor {...props} />, catalog: <CatalogEditor {...props} />,
  }[kind];
  return <div className="visual-editor">
    {(past.current.length > 0 || future.current.length > 0) && <div className="row undo-bar">
      {past.current.length > 0 && <button onClick={undo} title="Ctrl/⌘+Z">Undo</button>}
      {future.current.length > 0 && <button onClick={redo} title="Ctrl/⌘+Shift+Z">Redo</button>}
    </div>}
    {view}
  </div>;
}

const base = (p: string) => p.split("/").pop()!.replace(/\.[^.]+$/, "");
const json = (v: unknown) => JSON.stringify(v, null, 2) + "\n";

// ------------------------------------------------------------------ Music
function MusicEditor({ path, content, onChange, onStatus }: Props) {
  const song = useMemo(() => normaliseSong(content), [content]);
  const [playing, setPlaying] = useState(false);
  const [cursor, setCursor] = useState(-1);
  const ctx = useRef<AudioContext | null>(null);
  const timer = useRef<number | null>(null);
  const latest = useRef(content);
  latest.current = content;
  const set = (s: typeof song) => onChange(json(s));

  function stop() { if (timer.current) window.clearInterval(timer.current); timer.current = null; setPlaying(false); setCursor(-1); }
  useEffect(() => stop, []);

  function play() {
    if (playing) { stop(); return; }
    const ac = ctx.current ?? (ctx.current = new AudioContext());
    let step = 0;
    const tick = () => {
      const s = normaliseSong(latest.current);
      s.tracks.forEach(t => {
        if (!t.steps[step]) return;
        const o = ac.createOscillator(), g = ac.createGain(), now = ac.currentTime;
        o.type = t.wave; o.frequency.value = midiToHz(t.note);
        g.gain.setValueAtTime(0.25, now); g.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
        o.connect(g).connect(ac.destination); o.start(now); o.stop(now + 0.2);
      });
      setCursor(step); step = (step + 1) % s.steps;
    };
    tick();
    timer.current = window.setInterval(tick, 60_000 / song.tempo_bpm / 4);
    setPlaying(true);
  }

  return <section aria-label="Music sequencer">
    <div className="row wrap">
      <label>Title <input value={song.title} maxLength={80} onChange={e => set({ ...song, title: e.target.value })} /></label>
      <label>Tempo <input type="number" min={30} max={300} value={song.tempo_bpm} className="narrow"
        onChange={e => set({ ...song, tempo_bpm: Number(e.target.value) })} /> BPM</label>
      <label>Key <input value={song.key} maxLength={20} className="narrow" onChange={e => set({ ...song, key: e.target.value })} /></label>
      <button className="primary" onClick={play}>{playing ? "Stop" : "Play"}</button>
      <button onClick={() => { download(base(path) + ".mid", encodeMidi(song, 4), "audio/midi"); onStatus("MIDI exported (4 bars)"); }}>Export MIDI</button>
      {song.tracks.length < 16 && <button onClick={() => set({ ...song, tracks: [...song.tracks, { name: `Track ${song.tracks.length + 1}`, wave: "sine", note: 60, steps: Array(song.steps).fill(false) }] })}>Add track</button>}
    </div>
    <table className="seq">
      <tbody>{song.tracks.map((t, ti) => <tr key={ti}>
        <th scope="row"><input aria-label="Track name" value={t.name} maxLength={40}
          onChange={e => set({ ...song, tracks: song.tracks.map((x, i) => i === ti ? { ...x, name: e.target.value } : x) })} />
          <input aria-label={`${t.name} MIDI note`} type="number" min={0} max={127} value={t.note} className="narrow"
            onChange={e => set({ ...song, tracks: song.tracks.map((x, i) => i === ti ? { ...x, note: Number(e.target.value) } : x) })} />
          <button className="icon" aria-label={`Remove ${t.name}`}
            onClick={() => set({ ...song, tracks: song.tracks.filter((_, i) => i !== ti) })}>×</button></th>
        {t.steps.map((on, si) => <td key={si}><button aria-pressed={on} aria-label={`${t.name} step ${si + 1}`}
          className={"step" + (on ? " on" : "") + (si === cursor ? " now" : "") + (si % 4 === 0 ? " beat" : "")}
          onClick={() => set({ ...song, tracks: song.tracks.map((x, i) => i === ti ? { ...x, steps: x.steps.map((v, j) => j === si ? !v : v) } : x) })} /></td>)}
      </tr>)}</tbody>
    </table>
  </section>;
}

// ------------------------------------------------------------------ Sound
type Loaded = { name: string; rate: number; channels: Float32Array[] };

function SoundEditor({ content, onChange, onStatus }: Props) {
  const session = useMemo(() => normaliseSession(content), [content]);
  const [loaded, setLoaded] = useState<Record<string, Loaded>>({});
  const [selected, setSelected] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const clip = session.tracks[selected];
  const audio = clip ? loaded[clip.file] : undefined;
  const set = (tracks: AudioClip[]) => onChange(json({ ...session, tracks }));
  const update = (patch: Partial<AudioClip>) => set(session.tracks.map((t, i) => i === selected ? { ...t, ...patch } : t));

  async function addFiles(files: FileList | null) {
    if (!files?.length) return;
    const ac = new AudioContext();
    const added: AudioClip[] = [];
    for (const f of Array.from(files).slice(0, 8)) {
      try {
        const buf = await ac.decodeAudioData(await f.arrayBuffer());
        const channels = Array.from({ length: buf.numberOfChannels }, (_, c) => buf.getChannelData(c).slice());
        setLoaded(l => ({ ...l, [f.name]: { name: f.name, rate: buf.sampleRate, channels } }));
        if (!session.tracks.some(t => t.file === f.name)) added.push({ name: base(f.name), file: f.name, start: 0,
          end: Math.round(buf.duration * 100) / 100, gain_db: 0, fade_in: 0, fade_out: 0 });
      } catch { onStatus(`Could not decode ${f.name}`); }
    }
    void ac.close();
    if (added.length) { set([...session.tracks, ...added]); setSelected(session.tracks.length); }
    onStatus(`Opened ${files.length} audio file(s) in this browser; the session saves your edits, not the audio`);
  }

  useEffect(() => {
    const c = canvas.current; if (!c) return;
    const g = c.getContext("2d")!; g.clearRect(0, 0, c.width, c.height);
    if (!audio || !clip) { g.fillStyle = "#8a93a6"; g.font = "14px sans-serif"; g.fillText("Open the audio file to see its waveform", 12, 24); return; }
    const p = peaks(audio.channels[0], c.width), dur = audio.channels[0].length / audio.rate;
    g.fillStyle = "rgba(77,163,255,.15)";
    g.fillRect((clip.start / dur) * c.width, 0, ((clip.end - clip.start) / dur) * c.width, c.height);
    g.strokeStyle = "#4da3ff"; g.beginPath();
    p.forEach((v, x) => { g.moveTo(x + .5, c.height / 2 - v * c.height / 2); g.lineTo(x + .5, c.height / 2 + v * c.height / 2); });
    g.stroke();
  }, [audio, clip]);

  function render(): { channels: Float32Array[]; rate: number } | null {
    if (!audio || !clip) return null;
    return { rate: audio.rate, channels: audio.channels.map(ch => renderClip(ch, audio.rate, clip)) };
  }
  function preview() {
    const r = render(); if (!r) return;
    const ac = new AudioContext(), b = ac.createBuffer(r.channels.length, r.channels[0].length, r.rate);
    r.channels.forEach((ch, i) => b.getChannelData(i).set(ch));
    const s = ac.createBufferSource(); s.buffer = b; s.connect(ac.destination); s.start();
    s.onended = () => void ac.close();
  }

  const num = (k: keyof AudioClip, label: string, step = 0.1) => <label>{label}
    <input type="number" step={step} className="narrow" value={Number(clip?.[k] ?? 0)} onChange={e => update({ [k]: Number(e.target.value) } as Partial<AudioClip>)} /></label>;

  return <section aria-label="Sound editor">
    <div className="row wrap">
      <label className="file-btn">Open audio files…<input type="file" accept="audio/*" multiple onChange={e => void addFiles(e.target.files)} /></label>
      <label>Loudness target <input type="number" className="narrow" value={session.loudness_target_lufs}
        onChange={e => onChange(json({ ...session, loudness_target_lufs: Number(e.target.value) }))} /> LUFS</label>
    </div>
    <div className="row wrap">{session.tracks.map((t, i) => <button key={i} className={i === selected ? "chip active" : "chip"}
      onClick={() => setSelected(i)}>{t.name}{loaded[t.file] ? "" : " · reopen file"}</button>)}</div>
    <canvas ref={canvas} width={800} height={120} className="wave" aria-label="Waveform" />
    {clip && <div className="row wrap">
      {num("start", "Start s")}{num("end", "End s")}{num("gain_db", "Gain dB", 0.5)}{num("fade_in", "Fade in s")}{num("fade_out", "Fade out s")}
      {audio && <button onClick={preview}>Preview</button>}
      {audio && <button className="primary" onClick={() => { const r = render(); if (r) { download(base(clip.file) + "-edit.wav", encodeWav(r.channels, r.rate), "audio/wav"); onStatus("WAV exported"); } }}>Export WAV</button>}
      <button onClick={() => { set(session.tracks.filter((_, i) => i !== selected)); setSelected(0); }}>Remove clip</button>
    </div>}
    {!session.tracks.length && <p className="muted small">Open audio files to trim, set gain and fades, preview and export WAV.</p>}
  </section>;
}

// ------------------------------------------------------------------ Film storyboard / social calendar
const HEADERS = { storyboard: ["Shot", "Time", "Description", "Camera"], calendar: ["Date", "Platform", "Post", "Status"] };
const STATUSES = ["Draft", "In review", "Approved", "Scheduled", "Published"];

function TableEditor({ path, content, onChange, onStatus, kind }: Props & { kind: "storyboard" | "calendar" }) {
  const table = useMemo(() => parseMdTable(content, HEADERS[kind]), [content, kind]);
  const set = (rows: string[][]) => onChange(serializeMdTable({ ...table, rows }));
  const shots = kind === "storyboard" ? shotsFrom(table) : [];
  const total = shots.reduce((a, s) => a + s.duration, 0);
  const statusCol = table.headers.findIndex(h => h.toLowerCase() === "status");
  const cell = (ri: number, ci: number, v: string) => set(table.rows.map((x, i) => i === ri ? x.map((c, j) => j === ci ? v : c) : x));
  const move = (i: number, d: number) => { const r = [...table.rows]; const j = i + d; if (j < 0 || j >= r.length) return; [r[i], r[j]] = [r[j], r[i]]; set(r); };

  return <section aria-label={kind === "storyboard" ? "Storyboard" : "Content calendar"}>
    <div className="row wrap">
      <button className="primary" onClick={() => set([...table.rows, table.headers.map((h, i) =>
        i === 0 ? (kind === "storyboard" ? String(table.rows.length + 1) : new Date().toISOString().slice(0, 10))
          : h.toLowerCase() === "time" ? "3s" : h.toLowerCase() === "status" ? "Draft" : "")])}>
        Add {kind === "storyboard" ? "shot" : "post"}</button>
      {kind === "storyboard" && shots.length > 0 && <>
        <span className="muted small">{shots.length} shots · {total.toFixed(1)} s</span>
        <button onClick={() => { download(base(path) + ".srt", toSrt(shots), "text/plain"); onStatus("Subtitles exported"); }}>Export SRT</button>
        <button onClick={() => { download(base(path) + ".edl", toEdl(shots, base(path)), "text/plain"); onStatus("EDL exported"); }}>Export EDL</button>
      </>}
    </div>
    {kind === "storyboard" && total > 0 && <div className="timeline" aria-label="Timeline">
      {shots.map((s, i) => <span key={i} style={{ flexGrow: s.duration }} title={`${s.shot}: ${s.duration}s`}>{s.shot}</span>)}</div>}
    <table className="grid-edit"><thead><tr>{table.headers.map(h => <th key={h}>{h}</th>)}<th><span className="sr-only">Actions</span></th></tr></thead>
      <tbody>{table.rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci}>
        {ci === statusCol ? <select aria-label={table.headers[ci]} value={c} onChange={e => cell(ri, ci, e.target.value)}>
          {[...new Set([c, ...STATUSES])].filter(Boolean).map(s => <option key={s}>{s}</option>)}</select>
          : <input aria-label={table.headers[ci]} value={c} onChange={e => cell(ri, ci, e.target.value)} />}
      </td>)}<td className="nowrap">
        <button className="icon" aria-label="Move up" onClick={() => move(ri, -1)}>↑</button>
        <button className="icon" aria-label="Move down" onClick={() => move(ri, 1)}>↓</button>
        <button className="icon" aria-label="Delete row" onClick={() => set(table.rows.filter((_, i) => i !== ri))}>×</button></td></tr>)}</tbody></table>
  </section>;
}

// ------------------------------------------------------------------ Animation
function AnimationEditor({ path, content, onChange, onStatus }: Props) {
  const scene = useMemo(() => normaliseScene(content), [content]);
  const [frame, setFrame] = useState(0);
  const [selected, setSelected] = useState("");
  const [playing, setPlaying] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const set = (s: Scene) => onChange(json(s));
  const obj = scene.objects.find(o => o.id === selected) ?? scene.objects[0];
  const cur = obj ? stateAt(scene, obj.id, frame) : null;

  useEffect(() => {
    if (!playing) return;
    const t = window.setInterval(() => setFrame(f => (f + 1) % scene.frames), 1000 / scene.fps);
    return () => window.clearInterval(t);
  }, [playing, scene.fps, scene.frames]);

  useEffect(() => {
    const c = canvas.current; if (!c) return;
    const g = c.getContext("2d")!; g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
    scene.objects.forEach(o => {
      const s = stateAt(scene, o.id, frame);
      g.save(); g.globalAlpha = s.opacity; g.translate(s.x, s.y); g.rotate(s.rotation * Math.PI / 180); g.scale(s.scale, s.scale);
      g.fillStyle = o.color;
      if (o.shape === "circle") { g.beginPath(); g.arc(0, 0, 30, 0, 7); g.fill(); }
      else if (o.shape === "text") { g.font = "32px sans-serif"; g.textAlign = "center"; g.fillText(o.label || o.id, 0, 10); }
      else g.fillRect(-30, -30, 60, 60);
      if (o.id === obj?.id) { g.strokeStyle = "#4da3ff"; g.lineWidth = 2 / Math.max(0.1, s.scale); g.strokeRect(-36, -36, 72, 72); }
      g.restore();
    });
  }, [scene, frame, obj]);

  function key(patch: Partial<NonNullable<typeof cur>>) {
    if (!obj || !cur) return;
    set(upsertKeyframe(scene, { object: obj.id, frame, ...cur, ...patch }));
  }
  const field = (k: "x" | "y" | "scale" | "rotation" | "opacity", step = 1) => <label>{k}
    <input type="number" step={step} className="narrow" value={Number((cur?.[k] ?? 0).toFixed(2))} onChange={e => key({ [k]: Number(e.target.value) })} /></label>;
  const marks = obj ? scene.keyframes.filter(k => k.object === obj.id).map(k => k.frame) : [];

  return <section aria-label="Animation editor">
    <div className="row wrap">
      <button className="primary" onClick={() => setPlaying(p => !p)}>{playing ? "Pause" : "Play"}</button>
      <label>Frame <input type="range" min={0} max={scene.frames - 1} value={frame} onChange={e => setFrame(Number(e.target.value))} /> {frame}/{scene.frames - 1}</label>
      <label>FPS <input type="number" min={1} max={120} value={scene.fps} className="narrow" onChange={e => set({ ...scene, fps: Number(e.target.value) })} /></label>
      <label>Frames <input type="number" min={1} value={scene.frames} className="narrow" onChange={e => set({ ...scene, frames: Number(e.target.value) })} /></label>
      {(["rect", "circle", "text"] as const).map(shape => <button key={shape} onClick={() => {
        const id = `${shape}-${scene.objects.length + 1}`;
        set(upsertKeyframe({ ...scene, objects: [...scene.objects, { id, shape, color: "#1d4ed8", label: shape === "text" ? "Title" : undefined }] },
          { object: id, frame: 0, x: 320, y: 180, scale: 1, rotation: 0, opacity: 1 }));
        setSelected(id);
      }}>+ {shape}</button>)}
      <button onClick={() => { download(base(path) + ".html", sceneToHtml(scene, base(path)), "text/html"); onStatus("Animation exported as a self-playing HTML page"); }}>Export HTML</button>
    </div>
    <canvas ref={canvas} width={scene.width} height={scene.height} className="stage" aria-label="Stage preview" />
    <div className="row wrap">
      {scene.objects.map(o => <button key={o.id} className={o.id === obj?.id ? "chip active" : "chip"} onClick={() => setSelected(o.id)}>{o.id}</button>)}
      {!scene.objects.length && <span className="muted small">Add a shape, then change its values at different frames to animate it.</span>}
    </div>
    {obj && cur && <div className="row wrap">
      <label>Colour <input type="color" value={obj.color} onChange={e => set({ ...scene, objects: scene.objects.map(o => o.id === obj.id ? { ...o, color: e.target.value } : o) })} /></label>
      {obj.shape === "text" && <label>Text <input value={obj.label ?? ""} maxLength={60}
        onChange={e => set({ ...scene, objects: scene.objects.map(o => o.id === obj.id ? { ...o, label: e.target.value } : o) })} /></label>}
      {field("x")}{field("y")}{field("scale", 0.1)}{field("rotation")}{field("opacity", 0.1)}
      <span className="muted small">Changing a value sets a keyframe at frame {frame}. Keyframes: {marks.join(", ") || "none"}</span>
      <button onClick={() => set({ ...scene, objects: scene.objects.filter(o => o.id !== obj.id), keyframes: scene.keyframes.filter(k => k.object !== obj.id) })}>Remove object</button>
    </div>}
  </section>;
}

// ------------------------------------------------------------------ SDK / OpenAPI
function OpenApiEditor({ content, onChange, onStatus, onSaveFile }: Props) {
  const { spec, error } = useMemo(() => parseSpec(content), [content]);
  const ops = useMemo(() => operations(spec), [spec]);
  const [op, setOp] = useState({ method: "GET", path: "/items", summary: "" });

  async function generate(lang: "ts" | "py") {
    const code = lang === "ts" ? typescriptClient(spec) : pythonClient(spec);
    const file = lang === "ts" ? "sdk/typescript/client.ts" : "sdk/python/client.py";
    try {
      if (onSaveFile) { await onSaveFile(file, code); onStatus(`Generated ${file}`); }
      else download(file.split("/").pop()!, code, "text/plain");
    } catch (e) { onStatus((e as Error).message); }
  }

  return <section aria-label="OpenAPI designer">
    {error ? <p className="error" role="alert">YAML error: {error}</p>
      : <p className="muted small">{spec.info?.title ?? "API"} {spec.info?.version ?? ""} · {ops.length} operations</p>}
    {ops.length > 0 && <table className="grid-edit"><thead><tr><th>Method</th><th>Path</th><th>Operation</th><th>Summary</th></tr></thead>
      <tbody>{ops.map(o => <tr key={o.method + o.path}><td><span className="badge">{o.method}</span></td>
        <td><code>{o.path}</code></td><td><code>{o.operationId}</code></td><td>{o.summary}</td></tr>)}</tbody></table>}
    {!error && <div className="row wrap">
      <select aria-label="Method" value={op.method} onChange={e => setOp({ ...op, method: e.target.value })}>
        {["GET", "POST", "PUT", "PATCH", "DELETE"].map(m => <option key={m}>{m}</option>)}</select>
      <input aria-label="Path" value={op.path} onChange={e => setOp({ ...op, path: e.target.value })} />
      <input aria-label="Summary" placeholder="Summary" value={op.summary} onChange={e => setOp({ ...op, summary: e.target.value })} />
      <button onClick={() => { try { onChange(addOperation(content, op)); onStatus(`Added ${op.method} ${op.path}`); } catch (e) { onStatus((e as Error).message); } }}>Add operation</button>
    </div>}
    {!error && ops.length > 0 && <div className="row wrap">
      <button className="primary" onClick={() => void generate("ts")}>Generate TypeScript client</button>
      <button onClick={() => void generate("py")}>Generate Python client</button>
    </div>}
  </section>;
}

// ------------------------------------------------------------------ Media catalogue
function CatalogEditor({ content, onChange }: Props) {
  const { assets, rest } = useMemo(() => normaliseCatalog(content), [content]);
  const [q, setQ] = useState("");
  const shown = searchAssets(assets, q);
  const set = (list: typeof assets) => onChange(json({ ...rest, assets: list }));
  const edit = (id: string, patch: Partial<(typeof assets)[number]>) => set(assets.map(a => a.id === id ? { ...a, ...patch } : a));
  const nextId = () => { let n = assets.length + 1; while (assets.some(a => a.id === `asset-${n}`)) n++; return `asset-${n}`; };

  return <section aria-label="Asset catalogue">
    <div className="row wrap">
      <input aria-label="Search assets" placeholder="Search title, tag, licence…" value={q} onChange={e => setQ(e.target.value)} />
      <span className="muted small">{shown.length} of {assets.length}</span>
      <button className="primary" onClick={() => set([...assets, { id: nextId(), title: "", type: "image", tags: [], license: "", source: "" }])}>Add asset</button>
    </div>
    {assets.length > 0 && <table className="grid-edit"><thead><tr><th>ID</th><th>Title</th><th>Type</th><th>Tags</th><th>Licence</th><th>Source</th><th><span className="sr-only">Actions</span></th></tr></thead>
      <tbody>{shown.map(a => <tr key={a.id}>
        <td><code>{a.id}</code></td>
        <td><input aria-label="Title" value={a.title} onChange={e => edit(a.id, { title: e.target.value })} /></td>
        <td><select aria-label="Type" value={a.type} onChange={e => edit(a.id, { type: e.target.value })}>
          {[...new Set([a.type, "image", "video", "audio", "music", "document", "3d", "font"])].map(t => <option key={t}>{t}</option>)}</select></td>
        <td><input aria-label="Tags" value={a.tags.join(", ")} onChange={e => edit(a.id, { tags: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })} /></td>
        <td><input aria-label="Licence" value={a.license} onChange={e => edit(a.id, { license: e.target.value })} /></td>
        <td><input aria-label="Source" value={a.source} onChange={e => edit(a.id, { source: e.target.value })} /></td>
        <td><button className="icon" aria-label="Delete asset" onClick={() => set(assets.filter(x => x.id !== a.id))}>×</button></td>
      </tr>)}</tbody></table>}
  </section>;
}
