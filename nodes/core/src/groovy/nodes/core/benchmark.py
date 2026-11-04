"""Generic Benchmark node — offline text metrics (WER / CER), expandable later."""

from __future__ import annotations

from groovy.executor.text_metrics import (
    compute_text_metric,
    format_metric_report,
    supported_text_metrics,
)
from groovy.node import GroovyNode, register_node


@register_node
class Benchmark(GroovyNode):
    """Compare hypothesis TEXT to reference TEXT with a selectable offline metric.

    v1 metrics: ``wer``, ``cer``, ``wer_cer`` (both). Future metrics (BLEU, SI-SDR, …)
    can extend ``groovy.executor.text_metrics`` / sibling modules without a new node
    type — or add specialized Benchmark* nodes that share this pattern.
    """

    CATEGORY = "GroovyUI/Core"
    EXPORT_TIER = "EXPORTABLE"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = True
    DURATION_LOCKED = True
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("TEXT",)

    @classmethod
    def INPUT_TYPES(cls):
        metrics = list(supported_text_metrics())
        return {
            "required": {
                "hypothesis": ("TEXT",),
                "reference": ("TEXT",),
            },
            "optional": {
                "metric": (
                    "STRING",
                    {
                        "default": "wer_cer",
                        "description": (
                            "Text metric id: " + ", ".join(metrics) + ". Default reports WER and CER."
                        ),
                    },
                ),
                "normalize": (
                    "BOOL",
                    {
                        "default": True,
                        "description": "Lowercase, strip punctuation, collapse whitespace before scoring.",
                    },
                ),
                "label": (
                    "STRING",
                    {
                        "default": "",
                        "description": "Optional header line in the report (e.g. model id).",
                    },
                ),
            },
        }

    def run(self, **kwargs) -> tuple[str]:
        hypothesis = str(kwargs.get("hypothesis") or "")
        reference = str(kwargs.get("reference") or "")
        metric = str(kwargs.get("metric") or "wer_cer")
        normalize = bool(kwargs.get("normalize", True))
        label = str(kwargs.get("label") or "")
        results = compute_text_metric(
            metric,
            reference,
            hypothesis,
            normalize=normalize,
        )
        report = format_metric_report(results, label=label)
        return (report,)
