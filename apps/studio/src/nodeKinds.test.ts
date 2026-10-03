import { describe, expect, it } from "vitest";
import { canvasNodeKind, isAiNodeType } from "./nodeKinds";

describe("nodeKinds", () => {
  it("classifies AI category schemas as AI", () => {
    expect(isAiNodeType("CustomThing", "GroovyUI/AI")).toBe(true);
    expect(canvasNodeKind("CustomThing", "GroovyUI/AI")).toBe("ai");
  });

  it("classifies known AI types without schema", () => {
    expect(isAiNodeType("GenerateAudio")).toBe(true);
    expect(isAiNodeType("Video2Audio")).toBe(true);
    expect(isAiNodeType("Denoise")).toBe(true);
    expect(isAiNodeType("WhisperSTT")).toBe(true);
    expect(canvasNodeKind("TTS")).toBe("ai");
  });

  it("classifies core DSP as core", () => {
    expect(isAiNodeType("LoadAudio", "GroovyUI/Core")).toBe(false);
    expect(isAiNodeType("Normalize")).toBe(false);
    expect(isAiNodeType("Granulate", "GroovyUI/Core")).toBe(false);
    expect(canvasNodeKind("Mix")).toBe("core");
  });

  it("does not treat authenticity core nodes as AI without AI category", () => {
    expect(isAiNodeType("VerifyProvenance", "GroovyUI/Core")).toBe(false);
    expect(isAiNodeType("DeepfakeDetect", "GroovyUI/AI")).toBe(true);
  });
});
