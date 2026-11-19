import { describe, expect, it } from "vitest";
import { admit, LIMITS } from "../components/AssistantDrawer";

const att = (path: string, size: number) => ({ path, file: { size, name: path } as unknown as File });

describe("assistant attachments mirror the server limits", () => {
  it("accepts files, folders and camera photos within the limits", () => {
    const { ok, rejected } = admit([], [att("a.txt", 10), att("folder/b/c.png", 2_000), att("camera-1.jpg", 900_000)]);
    expect(ok.map((a) => a.path)).toEqual(["a.txt", "folder/b/c.png", "camera-1.jpg"]);
    expect(rejected).toEqual([]);
  });
  it("rejects oversized files, too many files and too much in total", () => {
    expect(admit([], [att("big.iso", LIMITS.fileBytes + 1)]).rejected).toEqual(["big.iso: size"]);
    const many = Array.from({ length: LIMITS.files + 2 }, (_, i) => att(`f${i}`, 1));
    expect(admit([], many).ok.length).toBe(LIMITS.files);
    const three = [att("x", 9 * 1048576), att("y", 9 * 1048576), att("z", 9 * 1048576)];
    expect(admit([], three).rejected).toEqual(["z: total"]);
  });
  it("does not add the same file twice", () => {
    const first = admit([], [att("a.txt", 5)]).ok;
    expect(admit(first, [att("a.txt", 5)]).ok.length).toBe(1);
  });
});
