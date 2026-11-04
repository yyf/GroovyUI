from __future__ import annotations

import pytest
from groovy.executor.eval_manifest import EvalItem, dump_eval_manifest, load_eval_manifest
from groovy.executor.text_metrics import compute_cer, compute_text_metric, compute_wer, normalize_text
from groovy.nodes.core.benchmark import Benchmark


def test_normalize_text_strips_punct_and_case() -> None:
    assert normalize_text("Hello, WORLD!") == "hello world"


def test_wer_perfect_and_substitution() -> None:
    perfect = compute_wer("the cat sat", "the cat sat")
    assert perfect.percent == 0.0
    sub = compute_wer("the cat sat", "the dog sat")
    assert sub.counts.substitutions == 1
    assert sub.percent == pytest.approx(100.0 / 3.0, rel=1e-3)


def test_cer_counts_characters() -> None:
    result = compute_cer("cat", "car")
    assert result.counts.reference_len == 3
    assert result.counts.substitutions == 1
    assert result.percent == pytest.approx(100.0 / 3.0, rel=1e-3)


def test_wer_cer_combo() -> None:
    results = compute_text_metric("wer_cer", "one two", "one two")
    assert [item.metric for item in results] == ["wer", "cer"]
    assert all(item.percent == 0.0 for item in results)


def test_benchmark_node_report() -> None:
    node = Benchmark()
    (report,) = node.run(
        hypothesis="The cat sat on the mat.",
        reference="The cat sat on the mat!",
        metric="wer_cer",
        normalize=True,
        label="demo",
    )
    assert "demo" in report
    assert "WER 0.00%" in report
    assert "CER 0.00%" in report


def test_eval_manifest_roundtrip(tmp_path) -> None:
    path = tmp_path / "fixtures.jsonl"
    dump_eval_manifest(
        [
            EvalItem(
                id="utt1",
                reference_text="hello world",
                audio="assets/samples/podcast_denoise_demo.wav",
                tags=["en"],
            )
        ],
        path,
    )
    loaded = load_eval_manifest(path)
    assert len(loaded) == 1
    assert loaded[0].id == "utt1"
    assert loaded[0].reference_text == "hello world"
