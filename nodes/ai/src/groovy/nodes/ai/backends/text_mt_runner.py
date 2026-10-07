"""Local text machine translation (M2M100 / MADLAD / Opus-MT)."""

from __future__ import annotations

from functools import lru_cache

# Registry id → Hugging Face model id
HF_MODEL_IDS: dict[str, str] = {
    "m2m100-418m": "facebook/m2m100_418M",
    "madlad400-3b-mt": "google/madlad400-3b-mt",
    "opus-mt-en-es": "Helsinki-NLP/opus-mt-en-es",
    "opus-mt-en-fr": "Helsinki-NLP/opus-mt-en-fr",
}

# Opus models have a fixed direction; widgets are informational for those ids.
OPUS_FIXED_PAIR: dict[str, tuple[str, str]] = {
    "opus-mt-en-es": ("en", "es"),
    "opus-mt-en-fr": ("en", "fr"),
}

_ISO2_ALIASES: dict[str, str] = {
    "eng": "en",
    "spa": "es",
    "fra": "fr",
    "deu": "de",
    "ger": "de",
    "ita": "it",
    "por": "pt",
    "rus": "ru",
    "jpn": "ja",
    "zho": "zh",
    "chi": "zh",
    "kor": "ko",
    "nld": "nl",
    "dut": "nl",
    "pol": "pl",
    "tur": "tr",
    "ara": "ar",
    "hin": "hi",
}


def normalize_lang_iso2(code: str, *, default: str = "en") -> str:
    raw = (code or default).strip().lower().replace("_", "-")
    if not raw:
        return default
    # eng_Latn / en_XX → eng / en
    primary = raw.split("-")[0]
    if primary in _ISO2_ALIASES:
        return _ISO2_ALIASES[primary]
    if len(primary) == 2:
        return primary
    if len(primary) == 3 and primary in _ISO2_ALIASES:
        return _ISO2_ALIASES[primary]
    return primary[:2] if len(primary) >= 2 else default


@lru_cache(maxsize=4)
def _load_seq2seq(hf_id: str) -> tuple[object, object, str]:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(hf_id)
    model = AutoModelForSeq2SeqLM.from_pretrained(hf_id)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return tokenizer, model, device


def translate_text(
    text: str,
    *,
    model_id: str,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> str:
    """Translate ``text`` with a registered MT model. Raises if deps/weights missing."""
    source = (text or "").strip()
    if not source:
        return ""

    hf_id = HF_MODEL_IDS.get(model_id)
    if hf_id is None:
        raise RuntimeError(f"Unsupported text MT model: {model_id}")

    src = normalize_lang_iso2(src_lang, default="en")
    tgt = normalize_lang_iso2(tgt_lang, default="zh")
    if model_id in OPUS_FIXED_PAIR:
        src, tgt = OPUS_FIXED_PAIR[model_id]

    tokenizer, model, device = _load_seq2seq(hf_id)

    if model_id.startswith("m2m100"):
        return _translate_m2m100(tokenizer, model, device, source, src=src, tgt=tgt)
    if model_id.startswith("madlad"):
        return _translate_madlad(tokenizer, model, device, source, tgt=tgt)
    if model_id.startswith("opus-mt"):
        return _translate_opus(tokenizer, model, device, source)
    raise RuntimeError(f"No runner path for text MT model: {model_id}")


def _translate_m2m100(
    tokenizer: object,
    model: object,
    device: str,
    text: str,
    *,
    src: str,
    tgt: str,
) -> str:
    import torch

    tokenizer.src_lang = src  # type: ignore[attr-defined]
    encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)  # type: ignore[operator]
    encoded = {k: v.to(device) for k, v in encoded.items()}
    lang_id = tokenizer.get_lang_id(tgt)  # type: ignore[attr-defined]
    with torch.inference_mode():
        generated = model.generate(**encoded, forced_bos_token_id=lang_id, max_new_tokens=512)  # type: ignore[operator]
    return tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()  # type: ignore[operator]


def _translate_madlad(
    tokenizer: object,
    model: object,
    device: str,
    text: str,
    *,
    tgt: str,
) -> str:
    import torch

    # MADLAD expects target language as a leading <2xx> token on the source string.
    prompted = f"<2{tgt}> {text}"
    encoded = tokenizer(prompted, return_tensors="pt", truncation=True, max_length=512)  # type: ignore[operator]
    encoded = {k: v.to(device) for k, v in encoded.items()}
    with torch.inference_mode():
        generated = model.generate(**encoded, max_new_tokens=512)  # type: ignore[operator]
    return tokenizer.decode(generated[0], skip_special_tokens=True).strip()  # type: ignore[operator]


def _translate_opus(tokenizer: object, model: object, device: str, text: str) -> str:
    import torch

    encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)  # type: ignore[operator]
    encoded = {k: v.to(device) for k, v in encoded.items()}
    with torch.inference_mode():
        generated = model.generate(**encoded, max_new_tokens=512)  # type: ignore[operator]
    return tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()  # type: ignore[operator]
