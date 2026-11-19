import { isSafeRelativePath } from "./api";

/** A piece of an agent's answer: prose, or a fenced code block (optionally naming a file). */
export type ResultBlock =
  | { kind: "text"; text: string }
  | { kind: "code"; lang: string; code: string; file?: string };

const FILE_HINT = /^(?:#+\s*|\*\*|\/\/\s*|file(?:name)?:\s*)?`?([\w.\-/]+\.[\w]+)`?(?:\*\*)?:?\s*$/i;

function fileFromInfo(info: string): string | undefined {
  // ```python src/app.py   or   ```src/app.py   or   ```ts title="web/x.ts"
  const titled = info.match(/title=["']?([^"'\s]+)/);
  const candidates = [titled?.[1], ...info.split(/\s+/)];
  return candidates.find(c => c && /\.[A-Za-z0-9]+$/.test(c) && isSafeRelativePath(c)) ?? undefined;
}

/** Split a model answer into prose and code blocks, attaching a file path where one is named. */
export function splitResult(answer: string): ResultBlock[] {
  const blocks: ResultBlock[] = [];
  const lines = answer.replace(/\r\n/g, "\n").split("\n");
  let prose: string[] = [];
  const flush = () => {
    const text = prose.join("\n").trim();
    if (text) blocks.push({ kind: "text", text });
    prose = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const open = lines[i].match(/^\s*```(.*)$/);
    if (!open) { prose.push(lines[i]); continue; }
    const info = open[1].trim();
    const code: string[] = [];
    let j = i + 1;
    while (j < lines.length && !/^\s*```\s*$/.test(lines[j])) code.push(lines[j++]);
    // A file named on the line just before the fence ("`src/app.py`:" or "**src/app.py**").
    let file = fileFromInfo(info);
    const previous = prose.length ? prose[prose.length - 1].trim() : "";
    const hint = previous.match(FILE_HINT)?.[1];
    if (!file && hint && isSafeRelativePath(hint)) { file = hint; prose.pop(); }
    flush();
    const lang = info.split(/\s+/)[0] ?? "";
    blocks.push({ kind: "code", lang: lang === file ? "" : lang, code: code.join("\n"), ...(file ? { file } : {}) });
    i = j;
  }
  flush();
  return blocks;
}

/** Percentage bar width for an allowance, clamped to 0–100. */
export function usageWidth(percent: number): string {
  return `${Math.max(0, Math.min(100, Math.round(Number.isFinite(percent) ? percent : 0)))}%`;
}

/** Starter tasks shown as one-tap chips: software, sound, music, video, film and social. */
export const QUICK_TASKS: { label: string; task: string }[] = [
  { label: "REST API", task: "Build a FastAPI REST API for a todo app with SQLite, input validation and pytest tests. Give every file with its path." },
  { label: "React page", task: "Create a responsive React + TypeScript landing page component with a hero, features grid and signup form. Give every file with its path." },
  { label: "Fix & test", task: "Review my project for bugs and security issues, then write unit tests for the riskiest functions." },
  { label: "Soundtrack", task: "Write a music brief for a 30-second upbeat electronic soundtrack: tempo, key, instruments, structure by second, and a generation prompt." },
  { label: "Podcast intro", task: "Write a 20-second podcast intro voice-over script with sound-effect cues and music bed directions." },
  { label: "Film storyboard", task: "Storyboard a 60-second product film: shot list with timings, camera moves, on-screen text and a key-frame prompt per shot." },
  { label: "Video edit", task: "Plan the edit for a 45-second promo video: timeline, transitions, captions, and an ffmpeg command to assemble the clips." },
  { label: "Social campaign", task: "Draft a one-week launch campaign: TikTok, YouTube Shorts, Instagram and LinkedIn posts with captions, hashtags and posting times." },
];
