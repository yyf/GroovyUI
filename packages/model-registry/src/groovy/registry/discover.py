from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from groovy.registry.download import ALLOWED_HOSTS

HF_MODELS_API = "https://huggingface.co/api/models"

TASK_HF_QUERIES: dict[str, str] = {
    "denoise": "audio denoise speech enhancement",
    "stem-separation": "source separation demucs vocals stems",
    "speech-to-text": "speech recognition whisper asr",
    "text-to-speech": "text to speech tts",
    "voice-conversion": "voice conversion rvc clone",
    "speech-translation": "speech translation seamless m4t s2st localization",
    "text-translation": "machine translation nllb m2m100 madlad opus-mt",
    "timbre-transfer": "rave timbre transfer neural audio vae",
    "audio-to-midi": "audio to midi transcription",
    "music-generation": "music generation audio",
    "singing-synthesis": "singing voice synthesis",
    "video-to-audio": "video to audio synthesis Foley Diff-Foley Hunyuan",
    "deepfake-detection": "deepfake audio detection spoof",
    "watermark-embed": "audio watermark embed audioseal",
    "watermark-detect": "audio watermark detect audioseal",
    "audio-compare": "audio similarity embedding",
}

TASK_TYPES_BY_PIPELINE: dict[str, list[str]] = {
    "audio-to-audio": ["denoise"],
    "automatic-speech-recognition": ["speech-to-text"],
    "text-to-speech": ["text-to-speech"],
    "translation": ["text-translation"],
    "audio-classification": ["deepfake-detection"],
}

TASK_COMPATIBLE_NODES: dict[str, list[str]] = {
    "denoise": ["Denoise"],
    "stem-separation": ["SeparateStems"],
    "speech-to-text": ["WhisperSTT", "DiarizeTranscribe"],
    "diarization": ["DiarizeTranscribe"],
    "speaker-diarization": ["DiarizeTranscribe"],
    "text-to-speech": ["TTS"],
    "voice-conversion": ["VoiceConvert"],
    "speech-translation": ["SpeechTranslate"],
    "localization": ["SpeechTranslate", "TranslateText"],
    "text-translation": ["TranslateText"],
    "timbre-transfer": ["TimbreTransfer"],
    "neural-synthesis": ["TimbreTransfer"],
    "audio-to-midi": ["AudioToMIDI"],
    "music-generation": ["MIDIToAudio", "GenerateAudio"],
    "singing-synthesis": ["SingFromMIDI"],
    "video-to-audio": ["Video2Audio"],
    "deepfake-detection": ["DeepfakeDetect"],
    "watermark-embed": ["EmbedWatermark"],
    "watermark-detect": ["DetectWatermark"],
    "audio-compare": ["AbCompareAnalyze"],
}

TAG_TASK_HINTS: list[tuple[str, str]] = [
    ("denois", "denoise"),
    ("speech-enhancement", "denoise"),
    ("source-separation", "stem-separation"),
    ("demucs", "stem-separation"),
    ("whisper", "speech-to-text"),
    ("asr", "speech-to-text"),
    ("diariz", "diarization"),
    ("pyannote", "diarization"),
    ("tts", "text-to-speech"),
    ("kokoro", "text-to-speech"),
    ("voice-conversion", "voice-conversion"),
    ("rvc", "voice-conversion"),
    ("seamless", "speech-translation"),
    ("s2st", "speech-translation"),
    ("m2m100", "text-translation"),
    ("madlad", "text-translation"),
    ("opus-mt", "text-translation"),
    ("nllb", "text-translation"),
    ("translation", "text-translation"),
    ("rave", "timbre-transfer"),
    ("timbre", "timbre-transfer"),
    ("midi", "audio-to-midi"),
    ("musicgen", "music-generation"),
    ("diff-foley", "video-to-audio"),
    ("diff_foley", "video-to-audio"),
    ("video-to-audio", "video-to-audio"),
    ("foley", "video-to-audio"),
    ("deepfake", "deepfake-detection"),
    ("watermark", "watermark-embed"),
    ("audioseal", "watermark-detect"),
]


class DiscoverError(Exception):
    pass


def _build_search_query(query: str, task_type: str | None) -> str:
    parts: list[str] = []
    if task_type and task_type in TASK_HF_QUERIES:
        parts.append(TASK_HF_QUERIES[task_type])
    if query.strip():
        parts.append(query.strip())
    if not parts:
        return "audio"
    return " ".join(parts)


def _infer_task_types(item: dict[str, Any], task_filter: str | None) -> list[str]:
    tasks: list[str] = []
    pipeline = str(item.get("pipeline_tag") or "")
    tasks.extend(TASK_TYPES_BY_PIPELINE.get(pipeline, []))
    tags = [str(tag).lower() for tag in item.get("tags") or []]
    haystack = " ".join([pipeline, *tags, str(item.get("id", ""))])
    for needle, task in TAG_TASK_HINTS:
        if needle in haystack and task not in tasks:
            tasks.append(task)
    if task_filter and task_filter not in tasks:
        if task_filter in haystack.replace("_", "-"):
            tasks.append(task_filter)
    if not tasks and task_filter:
        tasks.append(task_filter)
    return tasks or (["denoise"] if "audio" in haystack else [])


def _compatible_nodes(task_types: list[str]) -> list[str]:
    nodes: list[str] = []
    for task in task_types:
        for node in TASK_COMPATIBLE_NODES.get(task, []):
            if node not in nodes:
                nodes.append(node)
    return nodes


def _license_from_item(item: dict[str, Any]) -> dict[str, Any]:
    card = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
    raw = card.get("license") or item.get("license")
    if isinstance(raw, str) and raw.strip():
        spdx = raw.strip()
        commercial_ok = "nc" not in spdx.lower()
        return {"spdx": spdx, "commercial_ok": commercial_ok, "confidence": 0.6}
    return {"spdx": "UNKNOWN", "commercial_ok": None, "confidence": 0.0}


def _display_name(model_id: str) -> str:
    return model_id.split("/")[-1].replace("-", " ").strip() or model_id


# Bytes per parameter for safetensors dtype names Hugging Face publishes.
_DTYPE_BYTES: dict[str, float] = {
    "F64": 8,
    "F32": 4,
    "F16": 2,
    "BF16": 2,
    "I64": 8,
    "I32": 4,
    "I16": 2,
    "I8": 1,
    "U8": 1,
    "I4": 0.5,
    "U4": 0.5,
    "Q8": 1,
    "Q6": 0.75,
    "Q5": 0.625,
    "Q4": 0.5,
}


def weight_bytes_from_safetensors(safetensors: Any) -> int | None:
    """Published weight footprint. Unknown dtypes assume fp16 (2 bytes)."""
    if not isinstance(safetensors, dict):
        return None
    parameters = safetensors.get("parameters")
    if isinstance(parameters, dict) and parameters:
        total = 0.0
        for dtype, count in parameters.items():
            try:
                n = float(count)
            except (TypeError, ValueError):
                continue
            total += n * _DTYPE_BYTES.get(str(dtype).upper(), 2.0)
        return int(total) if total > 0 else None
    total = safetensors.get("total")
    try:
        params = int(total)
    except (TypeError, ValueError):
        return None
    if params <= 0:
        return None
    return params * 2


def compute_from_hf_tags(
    tags: list[str],
    library_name: str | None,
    *,
    vram_gb: float | None,
) -> dict[str, Any]:
    """Coarse hardware hint from Hub tags. Empty presets means unknown — keep the card."""
    blob = " ".join([library_name or "", *tags]).lower()
    runtimes: list[str] = []

    def add(name: str) -> None:
        if name not in runtimes:
            runtimes.append(name)

    if any(token in blob for token in ("mlx", "coreml", "whisperkit")):
        add("mlx")
    if any(token in blob for token in ("gguf", "onnx", "ctranslate2", "openvino")):
        add("cpu")
    if any(token in blob for token in ("pytorch", "transformers", "jax", "tensorflow", "safetensors")):
        add("cuda")
        add("cpu")
    if "mlx" in runtimes and "cpu" not in runtimes:
        add("cpu")

    requires_cuda = "cuda" in runtimes and "cpu" not in runtimes and "mlx" not in runtimes
    presets: list[str] = []
    if "mlx" in runtimes:
        presets.append("apple")
    elif "cpu" in runtimes and not requires_cuda:
        presets.append("apple")
    if "cuda" in runtimes or requires_cuda:
        presets.append("cuda")
    if "cpu" in runtimes and not requires_cuda:
        presets.append("cpu")

    if vram_gb and vram_gb > 0:
        label = f"~{vram_gb:g} GB est. weights"
    elif presets:
        label = " / ".join(presets)
    else:
        label = "Hardware unknown"
    return {
        "runtimes": runtimes,
        "requires_cuda": requires_cuda,
        "presets": presets,
        "label": label,
        "vram_gb_estimate": vram_gb,
        "memory_note": (
            "Estimated from published safetensors dtypes, weights only."
            if vram_gb
            else None
        ),
    }


def _normalize_hf_item(item: dict[str, Any], *, task_filter: str | None) -> dict[str, Any]:
    model_id = str(item.get("id") or "")
    if not model_id:
        raise ValueError("Missing model id")
    task_types = _infer_task_types(item, task_filter)
    author = model_id.split("/")[0] if "/" in model_id else str(item.get("author") or "")
    card = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
    description = str(card.get("description") or item.get("description") or "").strip()
    if not description:
        description = f"Hugging Face model {model_id}"
    description = re.sub(r"\s+", " ", description)[:280]
    tags = [str(tag) for tag in (item.get("tags") or [])[:12]]
    nbytes = weight_bytes_from_safetensors(item.get("safetensors"))
    try:
        storage_bytes = int(item.get("usedStorage") or 0)
    except (TypeError, ValueError):
        storage_bytes = 0
    if storage_bytes < 0:
        storage_bytes = 0
    if nbytes:
        vram_gb = round(nbytes / (1024**3), 2)
    elif storage_bytes > 0:
        vram_gb = round(storage_bytes / (1024**3), 2)
    else:
        vram_gb = None
    download_mb = round(storage_bytes / (1024**2), 1) if storage_bytes > 0 else None
    library = item.get("library_name")
    library_name = str(library) if isinstance(library, str) else None
    return {
        "external_id": f"hf:{model_id}",
        "name": _display_name(model_id),
        "author": author,
        "description": description,
        "task_types": task_types,
        "tags": tags[:8],
        "license": _license_from_item(item),
        "updated_at": item.get("lastModified") or item.get("createdAt"),
        "downloads": int(item.get("downloads") or 0),
        "likes": int(item.get("likes") or 0),
        "source_url": f"https://huggingface.co/{model_id}",
        "suggested_compatible_nodes": _compatible_nodes(task_types),
        "trust": "external",
        "vram_gb_estimate": vram_gb,
        "download_mb_estimate": download_mb,
        "compute_resolved": compute_from_hf_tags(
            tags,
            library_name,
            vram_gb=vram_gb,
        ),
    }


def _fetch_hf_json(
    url: str,
    *,
    hf_token: str | None,
    fetch_json: Any | None,
) -> Any:
    if fetch_json is not None:
        return fetch_json(url)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    if hf_token:
        request.add_header("Authorization", f"Bearer {hf_token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise DiscoverError(f"Hugging Face search failed ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise DiscoverError(f"Hugging Face search unavailable: {exc.reason}") from exc


def _merge_safetensors(payload: Any, search_url: str, *, hf_token: str | None) -> None:
    """Second Hub call: `expand=safetensors` drops other fields, so merge by id."""
    if not isinstance(payload, list):
        return
    joiner = "&" if "?" in search_url else "?"
    try:
        extra = _fetch_hf_json(
            f"{search_url}{joiner}expand=safetensors",
            hf_token=hf_token,
            fetch_json=None,
        )
    except DiscoverError:
        return
    if not isinstance(extra, list):
        return
    by_id = {
        str(item.get("id")): item.get("safetensors")
        for item in extra
        if isinstance(item, dict) and item.get("id") and item.get("safetensors")
    }
    for item in payload:
        if not isinstance(item, dict) or item.get("safetensors"):
            continue
        found = by_id.get(str(item.get("id") or ""))
        if found:
            item["safetensors"] = found


def _merge_used_storage(payload: Any, *, hf_token: str | None) -> None:
    """Repo byte size lives on the model endpoint, not the search list."""
    if not isinstance(payload, list):
        return
    ids = [
        str(item.get("id"))
        for item in payload
        if isinstance(item, dict) and item.get("id") and not item.get("usedStorage")
    ]
    if not ids:
        return
    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(model_id: str) -> tuple[str, int | None]:
        quoted = urllib.parse.quote(model_id, safe="/")
        try:
            data = _fetch_hf_json(
                f"{HF_MODELS_API}/{quoted}",
                hf_token=hf_token,
                fetch_json=None,
            )
        except DiscoverError:
            return model_id, None
        if not isinstance(data, dict):
            return model_id, None
        try:
            value = int(data.get("usedStorage") or 0)
        except (TypeError, ValueError):
            return model_id, None
        return model_id, value if value > 0 else None

    with ThreadPoolExecutor(max_workers=8) as pool:
        found = dict(pool.map(fetch_one, ids))
    for item in payload:
        if not isinstance(item, dict):
            continue
        value = found.get(str(item.get("id") or ""))
        if value:
            item["usedStorage"] = value


def discover_models(
    query: str = "",
    *,
    task_type: str | None = None,
    limit: int = 20,
    hf_token: str | None = None,
    fetch_json: Any | None = None,
) -> list[dict[str, Any]]:
    """Search Hugging Face for recent audio-related models (read-only discovery)."""
    limit = max(1, min(int(limit), 50))
    search_query = _build_search_query(query, task_type)
    params = urllib.parse.urlencode(
        {
            "search": search_query,
            "limit": str(limit),
            "sort": "lastModified",
            "direction": "-1",
        }
    )
    url = f"{HF_MODELS_API}?{params}"
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise DiscoverError(f"Discover host not allowlisted: {host}")

    payload = _fetch_hf_json(url, hf_token=hf_token, fetch_json=fetch_json)
    if fetch_json is None:
        _merge_safetensors(payload, url, hf_token=hf_token)
        _merge_used_storage(payload, hf_token=hf_token)

    if not isinstance(payload, list):
        raise DiscoverError("Unexpected Hugging Face response")

    results: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            normalized = _normalize_hf_item(item, task_filter=task_type)
        except ValueError:
            continue
        if task_type and task_type not in normalized["task_types"]:
            # Keep loosely related results when HF metadata is sparse.
            if task_type not in search_query.lower():
                continue
        results.append(normalized)
    return results[:limit]
