// Text-to-speech read-aloud and optional speech-to-text using the browser's Web Speech API.
// Voices are whatever the user's device provides; availability is detected per locale and
// reported, never assumed (VOC-03, VOC-10). Audio is not recorded or uploaded (VOC-09).
// Audio download is not offered: speechSynthesis output cannot be captured as a file and
// device voices carry their own licences (VOC-07).

export type VoiceInfo = { name: string; lang: string; local: boolean; uri: string };

export function voicesFor(locale: string, all: Pick<SpeechSynthesisVoice, "name" | "lang" | "localService" | "voiceURI">[]): VoiceInfo[] {
  const base = locale.toLowerCase().split("-")[0];
  const alias: Record<string, string[]> = { fil: ["fil", "tl"], tl: ["tl", "fil"], no: ["no", "nb", "nn"], "zh-hans": ["zh"] };
  const wanted = alias[locale.toLowerCase()] ?? alias[base] ?? [base];
  return all
    .filter((v) => wanted.includes(v.lang.toLowerCase().split(/[-_]/)[0]) || v.lang.toLowerCase() === locale.toLowerCase())
    .map((v) => ({ name: v.name, lang: v.lang, local: v.localService, uri: v.voiceURI }));
}

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

export function sttSupported(): boolean {
  return typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
}

export function speak(text: string, opts: { lang: string; voiceUri?: string; rate: number; pitch: number;
  onEnd?: () => void }): SpeechSynthesisUtterance | null {
  if (!ttsSupported()) return null;
  const synth = window.speechSynthesis;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = opts.lang;
  u.rate = Math.min(2, Math.max(0.5, opts.rate));
  u.pitch = Math.min(2, Math.max(0, opts.pitch));
  const v = synth.getVoices().find((x) => x.voiceURI === opts.voiceUri);
  if (v) u.voice = v;
  if (opts.onEnd) u.onend = opts.onEnd;
  synth.speak(u);
  return u;
}

// Output-device selection: browsers route speechSynthesis to the system default device; there
// is no web API to redirect it. Capability is reported so the UI can say so (VOC-06).
export async function outputDevices(): Promise<{ supported: boolean; devices: MediaDeviceInfo[] }> {
  const supported = typeof HTMLMediaElement !== "undefined" && "setSinkId" in HTMLMediaElement.prototype;
  try {
    const all = await navigator.mediaDevices?.enumerateDevices?.();
    return { supported, devices: (all ?? []).filter((d) => d.kind === "audiooutput") };
  } catch {
    return { supported, devices: [] };
  }
}

export function startDictation(lang: string, onText: (t: string, final: boolean) => void, onEnd: () => void): (() => void) | null {
  const Ctor: any = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = lang;
  rec.interimResults = true;
  rec.continuous = false;
  rec.onresult = (e: any) => {
    const r = e.results[e.results.length - 1];
    onText(r[0].transcript, r.isFinal);
  };
  rec.onend = onEnd;
  rec.onerror = onEnd;
  rec.start();
  return () => rec.stop();
}
