from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TEMPLATE_HINTS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(hello|normalize|first)\b", re.I), "hello-groovy", "Simple normalize chain"),
    (
        re.compile(r"\b(cleanup.?and.?transcrib|denoise.+(transcrib|whisper)|clean.+(transcrib|whisper))\b", re.I),
        "cleanup-and-transcribe",
        "Cleanup then transcribe",
    ),
    (re.compile(r"\b(podcast|denoise|clean)\b", re.I), "podcast-denoise", "Podcast denoise pipeline"),
    (re.compile(r"\b(karaoke|instrumental|accompaniment)\b", re.I), "karaoke-stems", "Vocals vs instrumental"),
    (re.compile(r"\b(stem|vocals?|separate)\b", re.I), "stem-split-vocals", "Stem separation"),
    (re.compile(r"\b(diariz|speaker|meeting|who.?spoke)\b", re.I), "diarize-and-transcribe", "Speaker-labeled transcript"),
    (re.compile(r"\b(transcrib|stt|subtitle|speech.to.text)\b", re.I), "transcribe-dialogue", "Speech transcription"),
    (
        re.compile(r"\b(prompt.+(tts|speech)|modular.+(tts|prompt|control)|control.?curve.+tts|fade.+tts)\b", re.I),
        "prompt-tts-modular",
        "Prompt into TTS with control fade",
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
    (re.compile(r"\b(tts|text.to.speech|voiceover|kokoro)\b", re.I), "tts-greeting", "Text-to-speech"),
    (re.compile(r"\b(voice.?clon|f5.?tts|zero.?shot.?voice)\b", re.I), "voice-cloning", "Voice cloning"),
    (re.compile(r"\b(voice.?convert|rvc)\b", re.I), "voice-convert-demo", "Voice conversion"),
    (re.compile(r"\b(authentic|deepfake|provenance.?verify)\b", re.I), "authenticity-check", "Authenticity analysis"),
    (re.compile(r"\b(audio.?to.?midi|midi.?transcrib)\b", re.I), "transcribe-to-midi", "Audio to MIDI"),
    (re.compile(r"\b(regenerat|midi.?to.?audio|musicgen)\b", re.I), "transcribe-and-regenerate", "Transcribe and regenerate"),
    (
        re.compile(r"\b(ace.?step|lyrics.?to.?music|text.?to.?song)\b", re.I),
        "ace-step-1.5",
        "ACE-Step 1.5 text-to-music",
    ),
    (
        re.compile(r"\b(stable.?audio|stability.?ai|sfx.?generat|text.?to.?audio)\b", re.I),
        "stable-audio",
        "Stable Audio Open generation",
    ),
    (re.compile(r"\b(text.?to.?music|generate.?music|music.?from.?text)\b", re.I), "text-to-music", "Text to music generation"),
    (re.compile(r"\b(sing|vocal|diffsinger|lyrics)\b", re.I), "sing-from-midi", "Singing synthesis from MIDI"),
    (re.compile(r"\b(remix|stemforge)\b", re.I), "stem-to-remix", "Stem to remix chain"),
    (re.compile(r"\b(automation|midi.?cc)\b", re.I), "midi-automation-demo", "MIDI automation demo"),
]


def suggest_workflows(prompt: str, templates_dir: Path) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        return {"prompt": prompt, "results": [], "mode": "workflow_suggester"}

    scored: list[tuple[int, str, str]] = []
    for pattern, template_id, rationale in TEMPLATE_HINTS:
        if pattern.search(prompt):
            scored.append((10, template_id, rationale))

    for path in sorted(templates_dir.glob("*.groovy.json")):
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
        path = templates_dir / f"{template_id}.groovy.json"
        if not path.exists():
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
