from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class SocketSpec:
    name: str
    type: str
    optional: bool = False
    default: Any = None


@dataclass
class WidgetSpec:
    name: str
    type: str
    default: Any = None
    options: dict[str, Any] | None = None


class GroovyNode:
    """Base class for all GroovyUI nodes."""

    CATEGORY = "GroovyUI/Core"
    EXPORT_TIER = "EXPORTABLE"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = True
    # True when output length is fixed by input frames / DSP widgets (not model-chosen).
    # Metadata only — the executor does not gate on this flag.
    DURATION_LOCKED = True
    # Side-effecting sinks (e.g. SaveAudio) set this False so the executor never
    # serves a stale cached result — they must re-run and re-emit fresh outputs.
    CACHEABLE = True
    run_in_worker = False
    NETWORK_REQUIRED = False
    PROVENANCE_CLASS = "human_edited"
    PROVENANCE_PASSTHROUGH = False

    RETURN_TYPES: tuple[str, ...] = ()
    FUNCTION = "run"

    _ctx: Any = None

    def bind_context(self, ctx: Any) -> None:
        self._ctx = ctx

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple[Any, ...]]]:
        return {"required": {}, "optional": {}}

    @classmethod
    def OUTPUT_TYPES(cls) -> tuple[str, ...]:
        return cls.RETURN_TYPES

    @classmethod
    def describe(cls) -> dict[str, Any]:
        inputs = cls.INPUT_TYPES()
        widgets: list[dict[str, Any]] = []
        input_sockets: list[dict[str, Any]] = []

        for section in ("required", "optional"):
            for name, spec in inputs.get(section, {}).items():
                if isinstance(spec, tuple) and spec:
                    socket_type = spec[0]
                    widget_meta = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                    if socket_type == "MODEL_REF":
                        widgets.append(
                            {
                                "name": name,
                                "type": socket_type,
                                "default": widget_meta.get("default"),
                                "optional": section == "optional",
                            }
                        )
                    elif socket_type in {
                        "AUDIO",
                        "STEMS",
                        "MIDI",
                        "AUTHENTICITY",
                        "SAMPLE_CHECK",
                        "TEXT",
                        "AUTOMATION",
                        "AMBISONICS",
                        "OBA",
                        "OSC",
                    }:
                        input_sockets.append(
                            {
                                "name": name,
                                "type": socket_type,
                                "optional": section == "optional",
                            }
                        )
                    elif socket_type == "FLOAT" and section == "optional" and name in {
                        "gain_a",
                        "gain_b",
                        "value",
                    }:
                        input_sockets.append(
                            {
                                "name": name,
                                "type": socket_type,
                                "optional": True,
                            }
                        )
                    else:
                        widgets.append(
                            {
                                "name": name,
                                "type": socket_type,
                                "default": widget_meta.get("default"),
                                "optional": section == "optional",
                                **{k: v for k, v in widget_meta.items() if k != "default"},
                            }
                        )

        return {
            "type": cls.__name__,
            "category": cls.CATEGORY,
            "inputs": input_sockets,
            "outputs": [
                {"name": f"output_{i}", "type": t} for i, t in enumerate(cls.OUTPUT_TYPES())
            ],
            "widgets": widgets,
            "run_in_worker": cls.run_in_worker,
            "deterministic": cls.DETERMINISTIC,
            "sample_accurate": cls.SAMPLE_ACCURATE,
            "duration_locked": cls.DURATION_LOCKED,
            "provenance_class": cls.PROVENANCE_CLASS,
        }


NODE_REGISTRY: dict[str, type[GroovyNode]] = {}


def register_node(cls: type[GroovyNode]) -> type[GroovyNode]:
    NODE_REGISTRY[cls.__name__] = cls
    return cls


def get_node_class(node_type: str) -> type[GroovyNode]:
    if node_type not in NODE_REGISTRY:
        raise KeyError(f"Unknown node type: {node_type}")
    return NODE_REGISTRY[node_type]


def list_node_types() -> list[str]:
    return sorted(NODE_REGISTRY.keys())


class _GroovyDecorators:
    @staticmethod
    def cache(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__groovy_cache__ = True  # type: ignore[attr-defined]
        return fn

    @staticmethod
    def progress(message: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            fn.__groovy_progress__ = message  # type: ignore[attr-defined]
            return fn

        return decorator


groovy = _GroovyDecorators()
