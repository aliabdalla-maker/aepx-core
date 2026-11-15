/**
 * Pure helpers behind the module editors (Sound, Music, Film, Animation, SDK, Social, Media).
 * Everything here is deterministic and unit-tested; the components only draw and play.
 */
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";

// ------------------------------------------------------------------ which editor for which file
export type EditorKind = "music" | "sound" | "storyboard" | "calendar" | "animation" | "openapi" | "catalog";

export function editorFor(path: string): EditorKind | null {
  const p = path.toLowerCase();
  if (/^music\/.+\.json$/.test(p)) return "music";
  if (/^audio\/session\.json$/.test(p)) return "sound";
  if (/^film\/storyboard\.md$/.test(p)) return "storyboard";
  if (/^social\/calendar\.md$/.test(p)) return "calendar";
  if (/^animation\/.+\.json$/.test(p)) return "animation";
  if (/(^|\/)openapi\.ya?ml$/.test(p)) return "openapi";
  if (/^(assets\/catalog|media\/manifest)\.json$/.test(p)) return "catalog";
  return null;
}

export function safeJson<T>(text: string, fallback: T): T {
  try {
    const v = JSON.parse(text);
    return v && typeof v === "object" ? { ...fallback, ...v } : fallback;
  } catch { return fallback; }
}

// ------------------------------------------------------------------ Music: step sequencer + MIDI
export type SongTrack = { name: string; wave: OscillatorType; note: number; steps: boolean[] };
export type Song = { title: string; tempo_bpm: number; key: string; steps: number; tracks: SongTrack[]; sections?: unknown[] };

export const DEFAULT_TRACKS: SongTrack[] = [
  { name: "Kick", wave: "sine", note: 36, steps: Array.from({ length: 16 }, (_, i) => i % 4 === 0) },
  { name: "Snare", wave: "triangle", note: 38, steps: Array.from({ length: 16 }, (_, i) => i % 8 === 4) },
  { name: "Hat", wave: "square", note: 42, steps: Array.from({ length: 16 }, (_, i) => i % 2 === 0) },
  { name: "Bass", wave: "sawtooth", note: 48, steps: Array.from({ length: 16 }, (_, i) => i === 0 || i === 6 || i === 10) },
  { name: "Lead", wave: "triangle", note: 72, steps: Array.from({ length: 16 }, (_, i) => i === 2 || i === 9 || i === 14) },
];

export function normaliseSong(text: string): Song {
  const s = safeJson<Song>(text, { title: "Untitled", tempo_bpm: 120, key: "C major", steps: 16, tracks: [] });
  const steps = Math.min(64, Math.max(4, Math.round(Number(s.steps) || 16)));
  const tracks = (Array.isArray(s.tracks) && s.tracks.length ? s.tracks : DEFAULT_TRACKS).slice(0, 16).map(t => ({
    name: String(t.name || "Track").slice(0, 40),
    wave: (["sine", "square", "sawtooth", "triangle"].includes(t.wave) ? t.wave : "sine") as OscillatorType,
    note: Math.min(127, Math.max(0, Math.round(Number(t.note) || 60))),
    steps: Array.from({ length: steps }, (_, i) => Boolean(t.steps?.[i])),
  }));
  return { ...s, title: String(s.title || "Untitled"), tempo_bpm: Math.min(300, Math.max(30, Number(s.tempo_bpm) || 120)), steps, tracks };
}

export const midiToHz = (note: number) => 440 * Math.pow(2, (note - 69) / 12);

function vlq(n: number): number[] {
  const out = [n & 0x7f];
  while ((n >>= 7) > 0) out.unshift((n & 0x7f) | 0x80);
  return out;
}

/** Standard MIDI file (format 1): tempo track + one track per instrument, sixteenth-note steps. */
export function encodeMidi(song: Song, bars = 1): Uint8Array {
  const ppq = 96, step = ppq / 4, len = step - 2;
  const chunk = (type: string, body: number[]) => [...type].map(c => c.charCodeAt(0))
    .concat([(body.length >>> 24) & 255, (body.length >>> 16) & 255, (body.length >>> 8) & 255, body.length & 255], body);
  const usPerBeat = Math.round(60_000_000 / song.tempo_bpm);
  const tempo = [0, 0xff, 0x51, 3, (usPerBeat >> 16) & 255, (usPerBeat >> 8) & 255, usPerBeat & 255, 0, 0xff, 0x2f, 0];
  const tracks = song.tracks.map((t, ti) => {
    const ch = t.name.toLowerCase().match(/kick|snare|hat|drum|clap/) ? 9 : ti % 9;
    const events: number[] = [];
    let last = 0;
    for (let b = 0; b < bars; b++) t.steps.forEach((on, i) => {
      if (!on) return;
      const at = (b * t.steps.length + i) * step;
      events.push(...vlq(at - last), 0x90 | ch, t.note, 100, ...vlq(len), 0x80 | ch, t.note, 0);
      last = at + len;
    });
    return chunk("MTrk", [...events, 0, 0xff, 0x2f, 0]);
  });
  const header = chunk("MThd", [0, 1, 0, tracks.length + 1, 0, ppq]);
  return new Uint8Array([...header, ...chunk("MTrk", tempo), ...tracks.flat()]);
}

// ------------------------------------------------------------------ Sound: edits, peaks, WAV
export type AudioClip = { name: string; file: string; start: number; end: number; gain_db: number; fade_in: number; fade_out: number };
export type SoundSession = { sample_rate: number; loudness_target_lufs: number; tracks: AudioClip[] };

export function normaliseSession(text: string): SoundSession {
  const s = safeJson<SoundSession>(text, { sample_rate: 48000, loudness_target_lufs: -16, tracks: [] });
  return { ...s, tracks: Array.isArray(s.tracks) ? s.tracks : [] };
}

/** Applies trim, gain and linear fades to one channel; times in seconds. */
export function renderClip(samples: Float32Array, rate: number, c: Pick<AudioClip, "start" | "end" | "gain_db" | "fade_in" | "fade_out">): Float32Array {
  const a = Math.max(0, Math.floor(c.start * rate)), b = Math.min(samples.length, Math.ceil((c.end || samples.length / rate) * rate));
  const out = samples.slice(a, Math.max(a, b));
  const g = Math.pow(10, (c.gain_db || 0) / 20), fi = Math.floor((c.fade_in || 0) * rate), fo = Math.floor((c.fade_out || 0) * rate);
  for (let i = 0; i < out.length; i++) {
    let v = out[i] * g;
    if (fi > 0 && i < fi) v *= i / fi;
    if (fo > 0 && i >= out.length - fo) v *= (out.length - 1 - i) / fo;
    out[i] = Math.max(-1, Math.min(1, v));
  }
  return out;
}

export function peaks(samples: Float32Array, buckets: number): number[] {
  const size = Math.max(1, Math.floor(samples.length / buckets));
  return Array.from({ length: buckets }, (_, i) => {
    let m = 0;
    for (let j = i * size; j < Math.min(samples.length, (i + 1) * size); j++) m = Math.max(m, Math.abs(samples[j]));
    return m;
  });
}

/** 16-bit PCM WAV from one or more channels of equal length. */
export function encodeWav(channels: Float32Array[], rate: number): Uint8Array {
  const n = channels[0]?.length ?? 0, ch = Math.max(1, channels.length), bytes = n * ch * 2;
  const buf = new DataView(new ArrayBuffer(44 + bytes));
  const str = (o: number, s: string) => [...s].forEach((c, i) => buf.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); buf.setUint32(4, 36 + bytes, true); str(8, "WAVE"); str(12, "fmt ");
  buf.setUint32(16, 16, true); buf.setUint16(20, 1, true); buf.setUint16(22, ch, true);
  buf.setUint32(24, rate, true); buf.setUint32(28, rate * ch * 2, true); buf.setUint16(32, ch * 2, true);
  buf.setUint16(34, 16, true); str(36, "data"); buf.setUint32(40, bytes, true);
  let o = 44;
  for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) {
    const v = Math.max(-1, Math.min(1, channels[c]?.[i] ?? 0));
    buf.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7fff, true); o += 2;
  }
  return new Uint8Array(buf.buffer);
}

// ------------------------------------------------------------------ Markdown tables (storyboard, calendar)
export type MdTable = { before: string; headers: string[]; rows: string[][]; after: string };

export function parseMdTable(md: string, fallbackHeaders: string[]): MdTable {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const start = lines.findIndex((l, i) => l.trim().startsWith("|") && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1] ?? ""));
  if (start < 0) return { before: md.trimEnd() + "\n\n", headers: fallbackHeaders, rows: [], after: "" };
  let end = start + 2;
  while (end < lines.length && lines[end].trim().startsWith("|")) end++;
  const cells = (l: string) => l.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "").split(/(?<!\\)\|/)
    .map(c => c.trim().replace(/\\\|/g, "|"));
  const headers = cells(lines[start]);
  const rows = lines.slice(start + 2, end).map(l => { const c = cells(l); return headers.map((_, i) => c[i] ?? ""); });
  return { before: lines.slice(0, start).join("\n") + (start ? "\n" : ""), headers, rows, after: lines.slice(end).join("\n") };
}

export function serializeMdTable(t: MdTable): string {
  const esc = (c: string) => c.replace(/\|/g, "\\|").replace(/\n/g, " ");
  const line = (cs: string[]) => "| " + cs.map(esc).join(" | ") + " |";
  const table = [line(t.headers), "|" + t.headers.map(() => "---").join("|") + "|", ...t.rows.map(line)].join("\n");
  return t.before + table + "\n" + (t.after.trim() ? t.after.replace(/^\n?/, "\n") : "");
}

/** "0:05", "5s", "00:00:05" or "5" -> seconds. */
export function parseDuration(text: string): number {
  const t = text.trim().replace(/s$/i, "");
  if (!t) return 0;
  const parts = t.split(":").map(Number);
  if (parts.some(n => !Number.isFinite(n))) return 0;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

export function timecode(seconds: number, fps = 25, sep = ":"): string {
  const f = Math.round(seconds * fps), fr = f % fps, s = Math.floor(f / fps);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}${sep}${p(fr)}`;
}

function srtTime(seconds: number): string {
  const ms = Math.round(seconds * 1000), p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`;
}

export type Shot = { shot: string; duration: number; description: string; camera: string };

export function shotsFrom(t: MdTable): Shot[] {
  const col = (name: string) => t.headers.findIndex(h => h.toLowerCase().startsWith(name));
  const [s, d, ds, c] = [col("shot"), col("time"), col("desc"), col("camera")];
  return t.rows.map((r, i) => ({ shot: r[s] || String(i + 1), duration: parseDuration(r[d] ?? "") || 3,
    description: r[ds] ?? "", camera: r[c] ?? "" }));
}

export function toSrt(shots: Shot[]): string {
  let t = 0;
  return shots.map((s, i) => {
    const a = t; t += s.duration;
    return `${i + 1}\n${srtTime(a)} --> ${srtTime(t)}\n${s.description || s.shot}\n`;
  }).join("\n");
}

/** CMX 3600 EDL: one event per shot, record timeline back to back. */
export function toEdl(shots: Shot[], title: string, fps = 25): string {
  let t = 0;
  const lines = [`TITLE: ${title.slice(0, 60)}`, "FCM: NON-DROP FRAME", ""];
  shots.forEach((s, i) => {
    const a = t; t += s.duration;
    lines.push(`${String(i + 1).padStart(3, "0")}  AX       V     C        ${timecode(0, fps)} ${timecode(s.duration, fps)} ${timecode(a, fps)} ${timecode(t, fps)}`,
      `* FROM CLIP NAME: SHOT ${s.shot}`, ...(s.description ? [`* COMMENT: ${s.description.slice(0, 120)}`] : []), "");
  });
  return lines.join("\n");
}

// ------------------------------------------------------------------ Animation: keyframes
export type SceneObject = { id: string; shape: "rect" | "circle" | "text"; color: string; label?: string };
export type Keyframe = { object: string; frame: number; x: number; y: number; scale: number; rotation: number; opacity: number };
export type Scene = { fps: number; frames: number; width?: number; height?: number; objects: SceneObject[]; keyframes: Keyframe[] };

export function normaliseScene(text: string): Scene {
  const s = safeJson<Scene>(text, { fps: 24, frames: 240, objects: [], keyframes: [] });
  return { ...s, fps: Math.min(120, Math.max(1, Number(s.fps) || 24)), frames: Math.min(100000, Math.max(1, Number(s.frames) || 240)),
    width: s.width || 640, height: s.height || 360,
    objects: Array.isArray(s.objects) ? s.objects : [], keyframes: Array.isArray(s.keyframes) ? s.keyframes : [] };
}

const BASE: Omit<Keyframe, "object" | "frame"> = { x: 320, y: 180, scale: 1, rotation: 0, opacity: 1 };
const ease = (t: number) => t * t * (3 - 2 * t);

/** Eased interpolation between the keyframes around `frame`; holds before the first and after the last. */
export function stateAt(scene: Scene, object: string, frame: number): Omit<Keyframe, "object" | "frame"> {
  const ks = scene.keyframes.filter(k => k.object === object).sort((a, b) => a.frame - b.frame);
  if (!ks.length) return { ...BASE };
  if (frame <= ks[0].frame) return { ...BASE, ...ks[0] };
  const last = ks[ks.length - 1];
  if (frame >= last.frame) return { ...BASE, ...last };
  const i = ks.findIndex(k => k.frame > frame), a = { ...BASE, ...ks[i - 1] }, b = { ...BASE, ...ks[i] };
  const t = ease((frame - a.frame) / (b.frame - a.frame));
  const mix = (p: number, q: number) => p + (q - p) * t;
  return { x: mix(a.x, b.x), y: mix(a.y, b.y), scale: mix(a.scale, b.scale), rotation: mix(a.rotation, b.rotation), opacity: mix(a.opacity, b.opacity) };
}

export function upsertKeyframe(scene: Scene, k: Keyframe): Scene {
  return { ...scene, keyframes: [...scene.keyframes.filter(x => !(x.object === k.object && x.frame === k.frame)), k]
    .sort((a, b) => a.object.localeCompare(b.object) || a.frame - b.frame) };
}

/** Self-contained HTML page that plays the scene (no external scripts). */
export function sceneToHtml(scene: Scene, title: string): string {
  const data = JSON.stringify(scene).replace(/</g, "\\u003c");
  return `<!doctype html><html><head><meta charset="utf-8"><title>${title.replace(/[<&>"]/g, "")}</title></head>
<body style="margin:0;background:#111;display:grid;place-items:center;height:100vh"><canvas id="c" width="${scene.width}" height="${scene.height}" style="background:#fff;max-width:100%"></canvas>
<script>const S=${data};const B={x:320,y:180,scale:1,rotation:0,opacity:1};const e=t=>t*t*(3-2*t);
function at(o,f){const k=S.keyframes.filter(k=>k.object===o).sort((a,b)=>a.frame-b.frame);if(!k.length)return B;if(f<=k[0].frame)return{...B,...k[0]};const l=k[k.length-1];if(f>=l.frame)return{...B,...l};const i=k.findIndex(x=>x.frame>f),a={...B,...k[i-1]},b={...B,...k[i]},t=e((f-a.frame)/(b.frame-a.frame)),m=(p,q)=>p+(q-p)*t;return{x:m(a.x,b.x),y:m(a.y,b.y),scale:m(a.scale,b.scale),rotation:m(a.rotation,b.rotation),opacity:m(a.opacity,b.opacity)}}
const c=document.getElementById("c").getContext("2d");let f=0;function draw(){c.clearRect(0,0,S.width,S.height);for(const o of S.objects){const s=at(o.id,f);c.save();c.globalAlpha=s.opacity;c.translate(s.x,s.y);c.rotate(s.rotation*Math.PI/180);c.scale(s.scale,s.scale);c.fillStyle=o.color;if(o.shape==="circle"){c.beginPath();c.arc(0,0,30,0,7);c.fill()}else if(o.shape==="text"){c.font="32px sans-serif";c.textAlign="center";c.fillText(o.label||o.id,0,10)}else c.fillRect(-30,-30,60,60);c.restore()}f=(f+1)%S.frames;setTimeout(()=>requestAnimationFrame(draw),1000/S.fps)}draw();</script></body></html>`;
}

// ------------------------------------------------------------------ SDK: OpenAPI operations + clients
export type Operation = { method: string; path: string; operationId: string; summary: string };
type Spec = { info?: { title?: string; version?: string }; paths?: Record<string, Record<string, { operationId?: string; summary?: string }>> };
const METHODS = ["get", "post", "put", "patch", "delete"];

export function parseSpec(text: string): { spec: Spec; error: string | null } {
  try {
    const spec = parseYaml(text) as Spec;
    if (!spec || typeof spec !== "object") return { spec: {}, error: "Not an OpenAPI document" };
    return { spec, error: null };
  } catch (e) { return { spec: {}, error: (e as Error).message.split("\n")[0] }; }
}

const camel = (s: string) => s.replace(/[^A-Za-z0-9]+(.)?/g, (_, c) => (c ? c.toUpperCase() : "")).replace(/^./, c => c.toLowerCase());

export function operations(spec: Spec): Operation[] {
  return Object.entries(spec.paths ?? {}).flatMap(([path, item]) => METHODS.filter(m => item && item[m]).map(m => ({
    method: m.toUpperCase(), path, summary: item[m].summary ?? "",
    operationId: item[m].operationId || camel(`${m} ${path.replace(/[{}]/g, "")}`),
  })));
}

export function addOperation(text: string, op: { method: string; path: string; summary: string }): string {
  const { spec, error } = parseSpec(text);
  if (error) throw new Error(error);
  const m = op.method.toLowerCase();
  if (!METHODS.includes(m) || !op.path.startsWith("/")) throw new Error("Method or path not valid");
  spec.paths = spec.paths ?? {};
  spec.paths[op.path] = { ...(spec.paths[op.path] ?? {}),
    [m]: { operationId: camel(`${m} ${op.path.replace(/[{}]/g, "")}`), summary: op.summary || `${op.method} ${op.path}`,
      responses: { "200": { description: "OK" } } } as never };
  return stringifyYaml(spec);
}

const params = (path: string) => [...path.matchAll(/\{([A-Za-z0-9_]+)\}/g)].map(m => m[1]);

export function typescriptClient(spec: Spec): string {
  const ops = operations(spec);
  const body = ops.map(o => {
    const ps = params(o.path), hasBody = ["POST", "PUT", "PATCH"].includes(o.method);
    const args = [...ps.map(p => `${p}: string`), ...(hasBody ? ["body?: unknown"] : [])].join(", ");
    const url = o.path.replace(/\{([A-Za-z0-9_]+)\}/g, "${encodeURIComponent($1)}");
    return `  /** ${o.summary || `${o.method} ${o.path}`} */\n  ${o.operationId}(${args}) {\n    return this.request("${o.method}", \`${url}\`${hasBody ? ", body" : ""});\n  }`;
  }).join("\n\n");
  return `// Generated by AEP-X SDK IDE from ${spec.info?.title ?? "openapi.yaml"} ${spec.info?.version ?? ""}\n` +
`export class ApiClient {\n  constructor(private baseUrl: string, private token?: string) {}\n\n` +
`  private async request(method: string, path: string, body?: unknown) {\n` +
`    const res = await fetch(this.baseUrl.replace(/\\/$/, "") + path, {\n      method,\n` +
`      headers: { "Content-Type": "application/json", ...(this.token ? { Authorization: "Bearer " + this.token } : {}) },\n` +
`      body: body === undefined ? undefined : JSON.stringify(body),\n    });\n` +
`    if (!res.ok) throw new Error(\`\${method} \${path} failed: \${res.status}\`);\n` +
`    return res.status === 204 ? undefined : res.json();\n  }\n\n${body}\n}\n`;
}

export function pythonClient(spec: Spec): string {
  const snake = (s: string) => s.replace(/([A-Z])/g, "_$1").toLowerCase();
  const ops = operations(spec).map(o => {
    const ps = params(o.path), hasBody = ["POST", "PUT", "PATCH"].includes(o.method);
    const args = ["self", ...ps, ...(hasBody ? ["body=None"] : [])].join(", ");
    const url = o.path.replace(/\{([A-Za-z0-9_]+)\}/g, "{quote(str($1), safe='')}");
    return `    def ${snake(o.operationId)}(${args}):\n        """${(o.summary || `${o.method} ${o.path}`).replace(/"/g, "'")}"""\n` +
      `        return self._request("${o.method}", f"${url}"${hasBody ? ", body" : ""})\n`;
  }).join("\n");
  return `"""Generated by AEP-X SDK IDE from ${spec.info?.title ?? "openapi.yaml"} ${spec.info?.version ?? ""}."""\n` +
`import json\nimport urllib.request\nfrom urllib.parse import quote\n\n\nclass ApiClient:\n` +
`    def __init__(self, base_url, token=None):\n        self.base_url = base_url.rstrip("/")\n        self.token = token\n\n` +
`    def _request(self, method, path, body=None):\n        data = None if body is None else json.dumps(body).encode()\n` +
`        req = urllib.request.Request(self.base_url + path, data=data, method=method)\n` +
`        req.add_header("Content-Type", "application/json")\n        if self.token:\n            req.add_header("Authorization", "Bearer " + self.token)\n` +
`        with urllib.request.urlopen(req) as res:\n            raw = res.read()\n            return json.loads(raw) if raw else None\n\n${ops}`;
}

// ------------------------------------------------------------------ Media: asset catalogue
export type Asset = { id: string; title: string; type: string; tags: string[]; license: string; source: string };

export function normaliseCatalog(text: string): { assets: Asset[]; rest: Record<string, unknown> } {
  const v = safeJson<Record<string, unknown>>(text, {});
  const list = Array.isArray(v.assets) ? v.assets as Partial<Asset>[] : [];
  const { assets: _drop, ...rest } = v;
  void _drop;
  return { rest, assets: list.map((a, i) => ({ id: String(a.id ?? `asset-${i + 1}`), title: String(a.title ?? ""),
    type: String(a.type ?? "image"), tags: Array.isArray(a.tags) ? a.tags.map(String) : [],
    license: String(a.license ?? ""), source: String(a.source ?? "") })) };
}

export function searchAssets(assets: Asset[], query: string): Asset[] {
  const q = query.trim().toLowerCase();
  if (!q) return assets;
  return assets.filter(a => [a.id, a.title, a.type, a.license, a.source, ...a.tags].some(f => f.toLowerCase().includes(q)));
}

export function download(name: string, data: string | Uint8Array, type: string): void {
  const blob = new Blob([typeof data === "string" ? data : data.slice().buffer as ArrayBuffer], { type });
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
