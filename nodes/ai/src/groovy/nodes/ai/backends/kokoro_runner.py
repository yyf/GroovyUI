"""Optional Kokoro TTS backend (hexgrad/Kokoro-82M)."""

from __future__ import annotations

import numpy as np

# ISO 639-1 (and a few aliases) → Kokoro lang_code + default voice.
# Mandarin needs misaki[zh]; Japanese needs misaki[ja].
_KOKORO_LANG: dict[str, tuple[str, str]] = {
    "en": ("a", "af_heart"),
    "a": ("a", "af_heart"),
    "eng": ("a", "af_heart"),
    "b": ("b", "bf_emma"),
    "es": ("e", "ef_dora"),
    "e": ("e", "ef_dora"),
    "spa": ("e", "ef_dora"),
    "fr": ("f", "ff_siwis"),
    "f": ("f", "ff_siwis"),
    "fra": ("f", "ff_siwis"),
    "hi": ("h", "hf_alpha"),
    "h": ("h", "hf_alpha"),
    "it": ("i", "if_sara"),
    "i": ("i", "if_sara"),
    "ja": ("j", "jf_alpha"),
    "j": ("j", "jf_alpha"),
    "jpn": ("j", "jf_alpha"),
    "pt": ("p", "pf_dora"),
    "p": ("p", "pf_dora"),
    "zh": ("z", "zf_xiaobei"),
    "z": ("z", "zf_xiaobei"),
    "zho": ("z", "zf_xiaobei"),
    "cmn": ("z", "zf_xiaobei"),
    "cn": ("z", "zf_xiaobei"),
}


def resolve_kokoro_voice(language: str, voice: str | None = None) -> tuple[str, str]:
    """Return (lang_code, voice_id) for Kokoro."""
    raw = (language or "en").strip().lower().replace("_", "-")
    primary = raw.split("-")[0] if raw else "en"
    lang_code, default_voice = _KOKORO_LANG.get(primary, ("a", "af_heart"))
    chosen = (voice or "").strip() or default_voice
    return lang_code, chosen


def synthesize_pcm(
    text: str,
    *,
    sample_rate: int = 48000,
    language: str = "en",
    voice: str | None = None,
) -> np.ndarray:
    """Synthesize mono speech; raises if kokoro package is unavailable."""
    try:
        from kokoro import KPipeline  # type: ignore
    except ImportError as exc:
        raise RuntimeError("kokoro package is not installed") from exc

    lang_code, voice_id = resolve_kokoro_voice(language, voice)
    if lang_code == "z":
        try:
            from misaki import zh as _misaki_zh  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "Mandarin Kokoro needs misaki[zh] extras (ordered-set, jieba, pypinyin…). "
                "Reinstall kokoro-82m from Model Browser (Cmd+K), or: "
                "uv pip install 'misaki[zh]'."
            ) from exc
    elif lang_code == "j":
        try:
            from misaki import ja as _misaki_ja  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "Japanese Kokoro needs misaki[ja]. "
                "Install with: uv pip install 'misaki[ja]'."
            ) from exc
    try:
        pipeline = KPipeline(lang_code=lang_code)
    except Exception as exc:
        hint = ""
        if lang_code == "z":
            hint = " Reinstall kokoro-82m from Model Browser, or: uv pip install 'misaki[zh]'."
        elif lang_code == "j":
            hint = " Install with: uv pip install 'misaki[ja]'."
        raise RuntimeError(
            f"Kokoro failed to init lang_code={lang_code!r} (language={language!r}).{hint}"
        ) from exc

    chunks: list[np.ndarray] = []
    native_sr = 24000
    for _gs, _ps, audio in pipeline(text, voice=voice_id):
        chunks.append(np.asarray(audio, dtype=np.float64))
    if not chunks:
        raise RuntimeError("Kokoro returned empty audio")
    mono = np.concatenate(chunks)
    if sample_rate != native_sr:
        from scipy import signal

        mono = signal.resample(mono, int(len(mono) * sample_rate / native_sr))
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 1e-8:
        mono = mono / peak * 0.9
    return mono.reshape(1, -1)
