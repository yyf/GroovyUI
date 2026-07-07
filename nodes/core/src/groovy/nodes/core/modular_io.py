from __future__ import annotations

from groovy.executor.audio import AudioBuffer
from groovy.node import GroovyNode, register_node


def register_modular_io() -> None:
    _ = (ModuleInlet, ModuleOutlet)


@register_node
class ModuleInlet(GroovyNode):
    """Subgraph input boundary — forwards an external signal into a reusable module."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"signal": ("AUDIO",)},
            "optional": {
                "name": ("STRING", {"default": "in"}),
                "socket_type": ("STRING", {"default": "AUDIO"}),
            },
        }

    def run(self, signal: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        return (signal,)


@register_node
class ModuleOutlet(GroovyNode):
    """Subgraph output boundary — marks the module's exported result."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"signal": ("AUDIO",)},
            "optional": {"name": ("STRING", {"default": "out"})},
        }

    def run(self, signal: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        return (signal,)
