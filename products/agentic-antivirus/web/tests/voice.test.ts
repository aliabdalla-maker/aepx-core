// VOC-01..08: behaviour of the Web Speech wrapper against a scripted speechSynthesis / SpeechRecognition.
// Device voices themselves are not verified here (VOC-10); see docs/matrices/voice-coverage.md.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { outputDevices, speak, startDictation, sttSupported, ttsSupported, voicesFor } from "../lib/voice";

class FakeUtterance { text: string; lang = ""; rate = 1; pitch = 1; voice: unknown = null; onend: (() => void) | null = null;
  constructor(t: string) { this.text = t; } }

const voices = [
  { name: "Daniel", lang: "en-GB", localService: true, voiceURI: "daniel" },
  { name: "Amira", lang: "ar-SA", localService: false, voiceURI: "amira" },
];

function install() {
  const synth = { spoken: [] as FakeUtterance[], paused: false, cancel: vi.fn(), getVoices: () => voices,
    speak(u: FakeUtterance) { this.spoken.push(u); }, pause() { this.paused = true; }, resume() { this.paused = false; } };
  const g = globalThis as any;
  g.window = { speechSynthesis: synth, SpeechSynthesisUtterance: FakeUtterance };
  g.SpeechSynthesisUtterance = FakeUtterance;
  return synth;
}

afterEach(() => { const g = globalThis as any; delete g.window; delete g.SpeechSynthesisUtterance; });

describe("text to speech (VOC-01, 03, 04, 05)", () => {
  let synth: ReturnType<typeof install>;
  beforeEach(() => { synth = install(); });

  it("reads text aloud in the selected language and voice", () => {
    expect(ttsSupported()).toBe(true);
    const u = speak("Threat quarantined", { lang: "en-GB", voiceUri: "daniel", rate: 1, pitch: 1 }) as any;
    expect(synth.spoken).toHaveLength(1);
    expect(u.text).toBe("Threat quarantined");
    expect(u.lang).toBe("en-GB");
    expect(u.voice.name).toBe("Daniel");
    expect(synth.cancel).toHaveBeenCalled(); // a new read-aloud replaces the previous one
  });

  it("clamps speed and pitch to supported ranges", () => {
    const fast = speak("x", { lang: "en", rate: 9, pitch: -3 }) as any;
    expect(fast.rate).toBe(2);
    expect(fast.pitch).toBe(0);
    const slow = speak("x", { lang: "en", rate: 0.1, pitch: 1.5 }) as any;
    expect(slow.rate).toBe(0.5);
    expect(slow.pitch).toBe(1.5);
  });

  it("supports pause and resume through the platform synthesiser and signals the end", () => {
    const done = vi.fn();
    const u = speak("long text", { lang: "en", rate: 1, pitch: 1, onEnd: done }) as any;
    window.speechSynthesis.pause();
    expect(synth.paused).toBe(true);
    window.speechSynthesis.resume();
    expect(synth.paused).toBe(false);
    u.onend();
    expect(done).toHaveBeenCalledOnce();
  });

  it("lists only voices for the chosen locale and reports when none exist", () => {
    expect(voicesFor("ar", voices).map((v) => v.name)).toEqual(["Amira"]);
    expect(voicesFor("ja", voices)).toEqual([]);
  });
});

describe("unsupported devices degrade honestly (VOC-08, VOC-10)", () => {
  it("returns null instead of pretending to speak or listen", () => {
    expect(ttsSupported()).toBe(false);
    expect(sttSupported()).toBe(false);
    expect(speak("x", { lang: "en", rate: 1, pitch: 1 })).toBeNull();
  });
});

describe("speech to text (VOC-02)", () => {
  it("starts only on request, returns final text and can be stopped", () => {
    const started: any[] = [];
    class FakeRec { lang = ""; interimResults = false; continuous = true; onresult: any; onend: any; onerror: any;
      stopped = false; start() { started.push(this); } stop() { this.stopped = true; } }
    (globalThis as any).window = { webkitSpeechRecognition: FakeRec };
    expect(sttSupported()).toBe(true);
    expect(started).toHaveLength(0); // nothing listens until the user asks
    const got: [string, boolean][] = [];
    const end = vi.fn();
    const stop = startDictation("fr-FR", (t, f) => got.push([t, f]), end)!;
    const rec = started[0];
    expect(rec.lang).toBe("fr-FR");
    expect(rec.continuous).toBe(false);
    rec.onresult({ results: [Object.assign([{ transcript: "analyse" }], { isFinal: true })] });
    expect(got).toEqual([["analyse", true]]);
    stop();
    expect(rec.stopped).toBe(true);
    rec.onerror();
    expect(end).toHaveBeenCalled();
  });
});

describe("audio output and export (VOC-06, VOC-07)", () => {
  it("reports output-device capability rather than claiming routing", async () => {
    const g = globalThis as any;
    const nav = g.navigator;
    Object.defineProperty(g, "navigator", { configurable: true, value: { mediaDevices: { enumerateDevices: async () => [
      { kind: "audiooutput", deviceId: "spk", label: "Speakers" }, { kind: "audioinput", deviceId: "mic", label: "Mic" }] } } });
    const r = await outputDevices();
    expect(r.devices.map((d) => d.deviceId)).toEqual(["spk"]);
    expect(typeof r.supported).toBe("boolean");
    Object.defineProperty(g, "navigator", { configurable: true, value: nav });
  });

  it("offers no audio download (device voices are not exportable)", async () => {
    const mod = await import("../lib/voice");
    expect(Object.keys(mod).some((k) => /download|export|record/i.test(k))).toBe(false);
  });
});
