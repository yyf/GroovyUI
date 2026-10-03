import { afterEach, describe, expect, it, vi } from "vitest";
import { attachTransportVideoSync } from "./transportVideoSync";

class FakeMedia extends EventTarget {
  currentTime = 0;
  paused = true;
  ended = false;
  muted = false;
  play = vi.fn(async () => {
    this.paused = false;
  });
  pause = vi.fn(() => {
    this.paused = true;
  });
}

describe("attachTransportVideoSync", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("plays and seeks muted node videos with the transport audio clock", () => {
    const audio = new FakeMedia();
    const video = new FakeMedia();
    audio.currentTime = 1.5;

    vi.stubGlobal("document", {
      querySelector: (sel: string) => (sel === ".transport__audio" ? audio : null),
      querySelectorAll: (sel: string) =>
        sel === ".groovy-node__video-player" ? ([video] as unknown as NodeListOf<Element>) : ([] as unknown as NodeListOf<Element>),
    });
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      // Do not recurse forever in tests.
      return 0 as unknown as number;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});

    const detach = attachTransportVideoSync();

    audio.paused = false;
    audio.dispatchEvent(new Event("play"));
    expect(video.muted).toBe(true);
    expect(video.currentTime).toBe(1.5);
    expect(video.play).toHaveBeenCalled();

    audio.currentTime = 3.25;
    audio.dispatchEvent(new Event("seeked"));
    expect(video.currentTime).toBe(3.25);

    audio.paused = true;
    audio.dispatchEvent(new Event("pause"));
    expect(video.pause).toHaveBeenCalled();

    detach();
  });
});
