import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { aiAvailability, buildAiTask, loadHelp, parseHelp, searchHelp, suggestedTopics } from "./assistant";

const HELP = readFileSync(join(__dirname, "..", "public", "help", "aepx-help.md"), "utf8");
const MODULES = ["general", "software", "sound", "music", "film", "animation", "sdk", "social", "multimedia", "media"];

describe("help file", () => {
  const topics = parseHelp(HELP);
  it("has help for every IDE module and no empty topics", () => {
    expect(new Set(topics.map(t => t.module))).toEqual(new Set(MODULES));
    expect(topics.every(t => t.title && t.body.length > 20)).toBe(true);
  });
  it("answers common questions with the right topic", () => {
    expect(searchHelp(topics, "how do I reset my password?")[0].title).toBe("Forgot password");
    expect(searchHelp(topics, "what are the password rules")[0].title).toBe("Password rules");
    expect(searchHelp(topics, "import a zip of my repository")[0].title).toBe("Importing files");
    expect(searchHelp(topics, "export MIDI", "music")[0].module).toBe("music");
    expect(searchHelp(topics, "subtitles SRT", "film")[0].title).toBe("Storyboard editor");
  });
  it("prefers the current module and returns nothing for empty questions", () => {
    expect(searchHelp(topics, "how does the editor work", "sound")[0].module).toBe("sound");
    expect(searchHelp(topics, "how does the editor work", "sdk")[0].module).toBe("sdk");
    expect(searchHelp(topics, "the and of")).toEqual([]);
    expect(suggestedTopics(topics, "sdk")[0].module).toBe("sdk");
  });
  it("loads the help file and degrades to no topics offline", async () => {
    expect((await loadHelp(vi.fn().mockResolvedValue(new Response(HELP)))).length).toBe(topics.length);
    expect(await loadHelp(vi.fn().mockRejectedValue(new Error("offline")))).toEqual([]);
  });
});

describe("AI requests", () => {
  const topics = parseHelp(HELP);
  it("puts the question first and stays within the API's 4000-character task limit", () => {
    const task = buildAiTask({ question: "How do I add a CI pipeline?", moduleName: "Software IDE", file: "README.md",
      excerpts: topics.slice(0, 40) });
    expect(task.startsWith("Question from a user of the AEP-X Software IDE: How do I add a CI pipeline?")).toBe(true);
    expect(task).toContain("Open file: README.md");
    expect(task.length).toBeLessThanOrEqual(4000);
    expect(buildAiTask({ question: "x".repeat(9000), moduleName: "Music IDE", excerpts: [] }).length).toBeLessThanOrEqual(4000);
  });
  it("explains why AI is unavailable", () => {
    expect(aiAvailability({ signedIn: false, project: "", agentsLive: true }).reason).toMatch(/Sign in/);
    expect(aiAvailability({ signedIn: true, project: "", agentsLive: true }).reason).toMatch(/Open a project/);
    expect(aiAvailability({ signedIn: true, project: "p", agentsLive: true, readOnly: true }).reason).toMatch(/read-only/);
    expect(aiAvailability({ signedIn: true, project: "p", agentsLive: false }).reason).toMatch(/not switched on/);
    expect(aiAvailability({ signedIn: true, project: "p", agentsLive: true })).toEqual({ ok: true, reason: "" });
  });
});
