from __future__ import annotations

import numpy as np
from groovy.executor.audio import AudioBuffer
from groovy.node import GroovyNode, register_node


def register_all() -> None:
    _ = Denoise


@register_node
class Denoise(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    COMPATIBLE_MODELS = ["deepfilternet-v3"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "deepfilternet-v3"}),
            },
            "optional": {
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer]:
        raise RuntimeError("Denoise must run in AI worker subprocess")
