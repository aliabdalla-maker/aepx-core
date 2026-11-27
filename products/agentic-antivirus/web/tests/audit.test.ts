import { describe, expect, it } from "vitest";
import { describeValidation } from "../lib/api";
import { formatBytes } from "../lib/format";

describe("audit 27 Nov 2026 fixes", () => {
  it("turns pydantic validation errors into sentences, never JSON", () => {
    const msg = describeValidation([
      { type: "string_too_short", loc: ["body", "artefact_digest"], msg: "x", ctx: { min_length: 7 } },
      { type: "too_short", loc: ["body", "device_ids"], msg: "x", ctx: { min_length: 1 } }]);
    expect(msg).toBe("Version or digest: enter at least 7 characters. Devices: choose at least 1.");
    expect(msg).not.toContain("{");
  });
  it("formats file sizes for people", () => {
    expect(formatBytes(70267, "en")).toBe("68.6 kB");
    expect(formatBytes(512, "en")).toBe("512 byte");
  });
});
