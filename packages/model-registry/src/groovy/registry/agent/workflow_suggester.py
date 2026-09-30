from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TEMPLATE_HINTS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(hello|first.?run|onboard)\b", re.I), "hello-groovy", "Hello GroovyUI Prompt → TTS"),
    (re.compile(r"\b(granulat)\b", re.I), "prompt-modular-synth", "Prompt Modular Synth grain cloud"),
    (
        re.compile(
            r"\b(generat(ive)?.?sequenc|clock.+(quantiz|sample.?and.?hold)|modular.?sequenc|random.?sequenc|systems.?not.?notes|probability.?gat)\b",
            re.I,
        ),
        "modular-generative-rack",
        "Modular Generative Rack",
    ),
    (
        re.compile(
            r"\b(neural.?modular|mix.?rack|probability.?saw|half.?time.?ace)\b",
            re.I,
        ),
        "neural-modular-rack",
        "Neural Modular Rack",
    ),
    (
        re.compile(
            r"\b(neural.?rack|self.?playing|ai.?oscillator|automation.?to.?midi|ace.+rave|rave.+modular)\b",
            re.I,
        ),
        "self-playing-neural-rack",
        "Self-Playing Neural Rack",
    ),
    (re.compile(r"\b(normalize|load.?audio.?chain)\b", re.I), "hello-groovy", "Hello GroovyUI starter chain"),
    (
        re.compile(r"\b(cleanup.?and.?transcrib|denoise.+(transcrib|whisper)|clean.+(transcrib|whisper))\b", re.I),
        "cleanup-and-transcribe",
        "Cleanup then transcribe",
    ),
    (re.compile(r"\b(podcast|denoise|clean)\b", re.I), "podcast-denoise", "Podcast denoise pipeline"),
    (re.compile(r"\b(karaoke|instrumental|accompaniment)\b", re.I), "karaoke-stems", "Vocals vs instrumental"),
    (re.compile(r"\b(stem|vocals?|separate)\b", re.I), "stem-separation", "Stem separation"),
    (re.compile(r"\b(diariz|speaker|meeting|who.?spoke)\b", re.I), "transcribe-and-diarize", "Speaker-labeled transcript"),
    (re.compile(r"\b(transcrib|stt|subtitle|speech.to.text)\b", re.I), "transcribe-dialogue", "Speech transcription"),
    (
        re.compile(r"\b(prompt.+(tts|speech)|modular.+(tts|prompt|control)|control.?curve.+tts|fade.+tts)\b", re.I),
        "hello-groovy",
        "Hello GroovyUI Prompt → TTS with control fade",
    ),
    (
        re.compile(
            r"\b(fm.?synth|simple.?fm|signal.?generat|oscillator|modular.?synth|phase.?mod)\b",
            re.I,
        ),
        "simple-fm-synth",
        "FM patched from oscillators + control curves",
    ),
    (re.compile(r"\b(modular|automation.?apply|control.?curve)\b", re.I), "simple-fm-synth", "Modular FM synth patch"),
    (re.compile(r"\b(tts|text.to.speech|voiceover|kokoro|greeting)\b", re.I), "hello-groovy", "Hello GroovyUI Prompt → TTS"),
    (re.compile(r"\b(voice.?clon|f5.?tts|zero.?shot.?voice)\b", re.I), "voice-cloning", "Voice cloning"),
    (re.compile(r"\b(voice.?convert|rvc)\b", re.I), "voice-convert-demo", "Voice conversion"),
    (
        re.compile(r"\b(rave|timbre.?transfer|variational.?autoencoder|neural.?resynth)\b", re.I),
        "rave-timbre-transfer",
        "RAVE Timbre Transfer",
    ),
    (re.compile(r"\b(authentic|deepfake|provenance.?verify)\b", re.I), "authenticity-check", "Authenticity analysis"),
    (re.compile(r"\b(watermark|audioseal)\b", re.I), "watermark-embed-detect", "AudioSeal embed + detect"),
    (re.compile(r"\b(audio.?to.?midi|midi.?transcrib)\b", re.I), "transcribe-to-midi", "Audio to MIDI"),
    (re.compile(r"\b(regenerat|midi.?to.?audio|musicgen)\b", re.I), "transcribe-and-regenerate", "Transcribe and regenerate"),
    (
        re.compile(r"\b(ace.?step|lyrics.?to.?music|text.?to.?song)\b", re.I),
        "ace-step-1.5",
        "Text to Music- ACE Step 1.5",
    ),
    (
        re.compile(r"\b(stable.?audio|stability.?ai|sfx.?generat|text.?to.?audio)\b", re.I),
        "stable-audio",
        "Text to Music- Stable Audio",
    ),
    (re.compile(r"\b(text.?to.?music|generate.?music|music.?from.?text)\b", re.I), "text-to-music", "Text to Music- MusicGen"),
    (re.compile(r"\b(sing|vocal|diffsinger|lyrics)\b", re.I), "sing-from-midi", "Singing synthesis from MIDI"),
    (re.compile(r"\b(remix|stemforge)\b", re.I), "stem-to-remix", "Stem to remix chain"),
    (re.compile(r"\b(automation|midi.?cc)\b", re.I), "midi-automation-demo", "MIDI automation demo"),
]


def suggest_workflows(prompt: str, templates_dir: Path) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        return {"prompt": prompt, "results": [], "mode": "workflow_suggester"}

    template_dirs = [templates_dir]
    dev_dir = templates_dir.parent / "docs" / "internal" / "templates"
    if dev_dir.is_dir() and dev_dir.resolve() != templates_dir.resolve():
        template_dirs.append(dev_dir)

    def _find(template_id: str) -> Path | None:
        name = f"{template_id}.groovy.json"
        for directory in template_dirs:
            path = directory / name
            if path.is_file():
                return path
        return None

    scored: list[tuple[int, str, str]] = []
    for pattern, template_id, rationale in TEMPLATE_HINTS:
        if pattern.search(prompt):
            scored.append((20, template_id, rationale))

    for directory in template_dirs:
        for path in sorted(directory.glob("*.groovy.json")):
            template_id = path.name.removesuffix(".groovy.json")
            if any(tid == template_id for _, tid, _ in scored):
                continue
            data = json.loads(path.read_text())
            meta = data.get("metadata", {})
            haystack = " ".join(
                [
                    template_id,
                    str(meta.get("title", "")),
                    str(meta.get("description", "")),
                    " ".join(meta.get("tags", [])),
                ]
            ).lower()
            tokens = [t for t in prompt.lower().split() if len(t) > 2]
            score = sum(2 for token in tokens if token in haystack)
            if score > 0:
                scored.append((score, template_id, str(meta.get("title", template_id))))

    scored.sort(key=lambda item: (-item[0], item[1]))
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, template_id, rationale in scored[:5]:
        if template_id in seen:
            continue
        seen.add(template_id)
        path = _find(template_id)
        if path is None:
            continue
        data = json.loads(path.read_text())
        meta = data.get("metadata", {})
        results.append(
            {
                "template_id": template_id,
                "title": meta.get("title", template_id),
                "description": meta.get("description", ""),
                "rationale": rationale,
                "score": score,
                "workflow": data,
            }
        )

    return {
        "prompt": prompt,
        "mode": "workflow_suggester",
        "results": results,
    }
