"""MIDI-LLM (slseanwu/MIDI-LLM_Llama-3.2-1B) — text → SMF on CUDA / MPS / CPU."""

from __future__ import annotations

from pathlib import Path

HF_MODEL_ID = "slseanwu/MIDI-LLM_Llama-3.2-1B"
AMT_GPT2_BOS_ID = 55026
LLAMA_VOCAB_SIZE = 128256
SYSTEM_PROMPT = (
    "You are a world-class composer. Please compose some music according to "
    "the following description: "
)


def _pick_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def generate_midi_bytes(
    prompt: str,
    *,
    dest: Path,
    max_tokens: int = 1024,
    temperature: float = 1.0,
    top_p: float = 0.98,
    seed: int | None = None,
    model_id: str = HF_MODEL_ID,
    cache_dir: Path | None = None,
) -> Path:
    """Generate a single SMF from a text prompt. Writes ``dest`` and returns it."""
    import torch
    from anticipation.convert import events_to_midi
    from transformers import AutoModelForCausalLM, AutoTokenizer

    text = (prompt or "").strip() or "a short melodic phrase"
    device = _pick_device()
    # MPS/CPU prefer float16/float32; BF16 is CUDA-first for the HF card.
    dtype = torch.float16 if device.type in {"cuda", "mps"} else torch.float32
    if device.type == "cuda" and torch.cuda.is_bf16_supported():
        dtype = torch.bfloat16

    load_kwargs: dict = {"trust_remote_code": True, "torch_dtype": dtype}
    if cache_dir is not None:
        load_kwargs["cache_dir"] = str(cache_dir)

    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        pad_token="<|eot_id|>",
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    model = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs).to(device)
    model.eval()

    if seed is not None and seed >= 0:
        torch.manual_seed(int(seed))
        if device.type == "cuda":
            torch.cuda.manual_seed_all(int(seed))

    full_prompt = SYSTEM_PROMPT + text + " "
    llama_input = tokenizer(full_prompt, return_tensors="pt", padding=False)
    input_ids = llama_input["input_ids"]
    midi_bos = torch.tensor([[AMT_GPT2_BOS_ID + LLAMA_VOCAB_SIZE]], dtype=input_ids.dtype)
    input_ids = torch.cat([input_ids, midi_bos], dim=1).to(device)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids,
            do_sample=True,
            max_new_tokens=max(64, int(max_tokens)),
            temperature=max(0.01, float(temperature)),
            top_p=min(1.0, max(0.01, float(top_p))),
            num_return_sequences=1,
            pad_token_id=tokenizer.pad_token_id,
        )

    prompt_len = input_ids.shape[1]
    midi_tokens = (outputs[0, prompt_len:] - LLAMA_VOCAB_SIZE).detach().cpu().tolist()
    midi_tokens = [int(t) for t in midi_tokens if int(t) >= 0]
    if not midi_tokens:
        raise RuntimeError("MIDI-LLM returned no MIDI tokens for this prompt.")

    midi_obj = events_to_midi(midi_tokens)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    midi_obj.save(str(dest))
    if not dest.is_file() or dest.stat().st_size < 16:
        raise RuntimeError(f"MIDI-LLM failed to write SMF at {dest}")
    return dest
