import { describe, expect, it } from "vitest";
import { looksLikeExternalModelRef, sanitizePlanWorkflowModels, shortCanvasIssueLabel } from "./planModelSanitize";
import type { NodeSchema, Workflow } from "./types";

describe("planModelSanitize", () => {
  it("detects HF-style refs", () => {
    expect(looksLikeExternalModelRef("coqui/XTTS-v2")).toBe(true);
    expect(looksLikeExternalModelRef("kokoro-82m")).toBe(false);
  });

  it("remaps external model widgets to schema defaults on apply", () => {
    const workflow: Workflow = {
      schema_version: "1.0.0",
      groovy_version: "0.1.0",
      id: "w1",
      metadata: { title: "plan" },
      nodes: [
        { id: "n3", type: "TTS", widgets: { model: "coqui/XTTS-v2" } },
        { id: "n4", type: "Preview", widgets: {} },
      ],
      links: [],
    };
    const schemas: Record<string, NodeSchema> = {
      TTS: {
        type: "TTS",
        category: "GroovyUI/AI",
        inputs: [],
        outputs: [{ name: "audio", type: "AUDIO" }],
        widgets: [{ name: "model", type: "MODEL_REF", default: "kokoro-82m" }],
      },
    };
    const next = sanitizePlanWorkflowModels(workflow, schemas);
    expect(next.nodes[0].widgets.model).toBe("kokoro-82m");
    expect(next.nodes[1]).toEqual(workflow.nodes[1]);
  });

  it("fills empty LoadAudio paths with the demo sample", () => {
    const workflow: Workflow = {
      schema_version: "1.0.0",
      groovy_version: "0.1.0",
      id: "w1",
      metadata: { title: "plan" },
      nodes: [{ id: "n1", type: "LoadAudio", widgets: {} }],
      links: [],
    };
    const next = sanitizePlanWorkflowModels(workflow, {});
    expect(next.nodes[0].widgets.path).toBe("assets/samples/podcast_denoise_demo.wav");
  });

  it("shortens canvas issue labels", () => {
    expect(shortCanvasIssueLabel("FILE_NOT_FOUND: (empty path)")).toBe("Missing audio file");
    expect(shortCanvasIssueLabel("Render failed FILE_NOT_FOUND: (empty path)")).toBe(
      "Missing audio file",
    );
  });
});
