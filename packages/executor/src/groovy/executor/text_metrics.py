"""Offline text metrics for Benchmark nodes (WER / CER first; expandable).

Pure stdlib — no jiwer / evaluate dependency. Normalization is a light
Whisper-style pass (case, punct, whitespace) so Mac demos stay comparable.
"""

from __future__ import annotations

import re
import string
from dataclasses import asdict, dataclass
from typing import Any, Literal

TextMetricId = Literal["wer", "cer", "wer_cer"]

_SUPPORTED_METRICS: tuple[str, ...] = ("wer", "cer", "wer_cer")


@dataclass(frozen=True)
class EditCounts:
    substitutions: int
    deletions: int
    insertions: int
    hits: int
    reference_len: int

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def rate(self) -> float:
        if self.reference_len <= 0:
            return 0.0 if self.errors == 0 else 1.0
        return self.errors / float(self.reference_len)


@dataclass(frozen=True)
class MetricResult:
    metric: str
    rate: float
    percent: float
    counts: EditCounts
    reference_normalized: str
    hypothesis_normalized: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["counts"] = asdict(self.counts)
        return payload


def supported_text_metrics() -> tuple[str, ...]:
    return _SUPPORTED_METRICS


def normalize_text(text: str, *, enabled: bool = True) -> str:
    """Light ASR-eval normalization (not a full WhisperNormalizer port)."""
    value = str(text or "")
    if not enabled:
        return " ".join(value.split())
    value = value.lower()
    # Strip punctuation but keep apostroples inside tokens lightly by removing all punct.
    table = str.maketrans({ch: " " for ch in string.punctuation})
    value = value.translate(table)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokenize_words(text: str) -> list[str]:
    return [tok for tok in text.split(" ") if tok]


def _tokenize_chars(text: str) -> list[str]:
    # CER over characters excluding spaces (common for mixed-script demos).
    return [ch for ch in text if not ch.isspace()]


def _levenshtein_counts(reference: list[str], hypothesis: list[str]) -> EditCounts:
    n = len(reference)
    m = len(hypothesis)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    back: list[list[str]] = [[""] * (m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        cost[0][j] = j
        back[0][j] = "I"
    for i in range(1, n + 1):
        cost[i][0] = i
        back[i][0] = "D"
        for j in range(1, m + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                cost[i][j] = cost[i - 1][j - 1]
                back[i][j] = "H"
            else:
                sub = cost[i - 1][j - 1] + 1
                dele = cost[i - 1][j] + 1
                ins = cost[i][j - 1] + 1
                best = min(sub, dele, ins)
                cost[i][j] = best
                if best == sub:
                    back[i][j] = "S"
                elif best == dele:
                    back[i][j] = "D"
                else:
                    back[i][j] = "I"

    i, j = n, m
    substitutions = deletions = insertions = hits = 0
    while i > 0 or j > 0:
        op = back[i][j]
        if op == "H":
            hits += 1
            i -= 1
            j -= 1
        elif op == "S":
            substitutions += 1
            i -= 1
            j -= 1
        elif op == "D":
            deletions += 1
            i -= 1
        elif op == "I":
            insertions += 1
            j -= 1
        else:
            break

    return EditCounts(
        substitutions=substitutions,
        deletions=deletions,
        insertions=insertions,
        hits=hits,
        reference_len=n,
    )


def compute_wer(reference: str, hypothesis: str, *, normalize: bool = True) -> MetricResult:
    ref_n = normalize_text(reference, enabled=normalize)
    hyp_n = normalize_text(hypothesis, enabled=normalize)
    counts = _levenshtein_counts(_tokenize_words(ref_n), _tokenize_words(hyp_n))
    rate = counts.rate
    return MetricResult(
        metric="wer",
        rate=rate,
        percent=round(rate * 100.0, 2),
        counts=counts,
        reference_normalized=ref_n,
        hypothesis_normalized=hyp_n,
    )


def compute_cer(reference: str, hypothesis: str, *, normalize: bool = True) -> MetricResult:
    ref_n = normalize_text(reference, enabled=normalize)
    hyp_n = normalize_text(hypothesis, enabled=normalize)
    counts = _levenshtein_counts(_tokenize_chars(ref_n), _tokenize_chars(hyp_n))
    rate = counts.rate
    return MetricResult(
        metric="cer",
        rate=rate,
        percent=round(rate * 100.0, 2),
        counts=counts,
        reference_normalized=ref_n,
        hypothesis_normalized=hyp_n,
    )


def compute_text_metric(
    metric: str,
    reference: str,
    hypothesis: str,
    *,
    normalize: bool = True,
) -> list[MetricResult]:
    key = str(metric or "wer").strip().lower()
    if key not in _SUPPORTED_METRICS:
        supported = ", ".join(_SUPPORTED_METRICS)
        raise ValueError(f"Unsupported text metric {metric!r}. Supported: {supported}")
    if key == "wer":
        return [compute_wer(reference, hypothesis, normalize=normalize)]
    if key == "cer":
        return [compute_cer(reference, hypothesis, normalize=normalize)]
    return [
        compute_wer(reference, hypothesis, normalize=normalize),
        compute_cer(reference, hypothesis, normalize=normalize),
    ]


def format_metric_report(
    results: list[MetricResult],
    *,
    label: str = "",
) -> str:
    """Human-readable TEXT for Preview / Node Helper."""
    lines: list[str] = []
    if label.strip():
        lines.append(label.strip())
    for result in results:
        c = result.counts
        lines.append(
            f"{result.metric.upper()} {result.percent:.2f}% "
            f"(S={c.substitutions} D={c.deletions} I={c.insertions} "
            f"N={c.reference_len})"
        )
    if results:
        lines.append(f"ref: {results[0].reference_normalized}")
        lines.append(f"hyp: {results[0].hypothesis_normalized}")
    return "\n".join(lines)
