from __future__ import annotations

from groovy.executor.ambisonics import (
    AmbisonicBuffer,
    decode_foa_to_stereo,
    encode_foa_from_audio,
    rotate_foa_yaw,
)
from groovy.executor.audio import AudioBuffer
from groovy.executor.oba import (
    ObjectScene,
    apply_object_animation,
    merge_object_scenes,
    object_scene_from_audio,
    render_object_scene,
)
from groovy.node import GroovyNode, register_node


def register_immersive() -> None:
    _ = (
        AmbisonicEncode,
        AmbisonicDecode,
        AmbisonicRotate,
        ObjectFromAudio,
        RenderObjectScene,
        ObjectPlacement,
        ObjectMerge,
        ObjectAnimate,
    )


@register_node
class AmbisonicEncode(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AMBISONICS",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {"order": ("INT", {"default": 1})},
        }

    def run(self, audio: AudioBuffer, order: int = 1, **kwargs) -> tuple[AmbisonicBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        order = int(kwargs.get("order", order))
        if order != 1:
            raise ValueError("Only first-order (FOA) ambisonic encode is supported in Phase 2")
        _, pcm = self._ctx.cache.load_audio(audio.id)
        encoded = encode_foa_from_audio(pcm)
        buffer = AmbisonicBuffer.from_pcm(
            encoded,
            audio.sample_rate,
            layout_order=1,
            source_node_type="AmbisonicEncode",
            spatial_meta={
                "channel_ordering": "ACN",
                "normalization": "SN3D",
                "source_layout": audio.channel_layout,
            },
        )
        self._ctx.cache.write_ambisonics(buffer, encoded)
        return (buffer,)


@register_node
class AmbisonicDecode(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"ambisonics": ("AMBISONICS",)},
            "optional": {"layout": ("STRING", {"default": "stereo"})},
        }

    def run(self, ambisonics: AmbisonicBuffer, layout: str = "stereo", **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        layout = str(kwargs.get("layout", layout))
        if layout != "stereo":
            raise ValueError(f"AmbisonicDecode supports stereo output in Phase 2, not {layout}")
        _, pcm = self._ctx.cache.load_ambisonics(ambisonics.id)
        if ambisonics.layout_order != 1:
            raise ValueError("Only FOA decode is supported in Phase 2")
        decoded = decode_foa_to_stereo(pcm)
        buffer = AudioBuffer.from_planar(
            decoded,
            ambisonics.sample_rate,
            source_node_type="AmbisonicDecode",
            channel_layout="stereo",
        )
        buffer.encoding_scheme = "FOA AmbiX → stereo decode"
        buffer.spatial_meta = {**ambisonics.spatial_meta, "decoded_from": "ambisonics"}
        self._ctx.cache.write_audio(buffer, decoded)
        return (buffer,)


@register_node
class AmbisonicRotate(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AMBISONICS",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"ambisonics": ("AMBISONICS",)},
            "optional": {"yaw": ("FLOAT", {"default": 0.0})},
        }

    def run(self, ambisonics: AmbisonicBuffer, yaw: float = 0.0, **kwargs) -> tuple[AmbisonicBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        yaw = float(kwargs.get("yaw", yaw))
        _, pcm = self._ctx.cache.load_ambisonics(ambisonics.id)
        rotated = rotate_foa_yaw(pcm, yaw)
        buffer = AmbisonicBuffer.from_pcm(
            rotated,
            ambisonics.sample_rate,
            layout_order=ambisonics.layout_order,
            source_node_type="AmbisonicRotate",
            spatial_meta={**ambisonics.spatial_meta, "yaw_deg": yaw},
        )
        self._ctx.cache.write_ambisonics(buffer, rotated)
        return (buffer,)


@register_node
class ObjectFromAudio(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    RETURN_TYPES = ("OBA",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "name": ("STRING", {"default": "Object"}),
                "azimuth": ("FLOAT", {"default": 0.0}),
                "elevation": ("FLOAT", {"default": 0.0}),
            },
        }

    def run(
        self,
        audio: AudioBuffer,
        name: str = "Object",
        azimuth: float = 0.0,
        elevation: float = 0.0,
        **kwargs,
    ) -> tuple[ObjectScene]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        scene = object_scene_from_audio(
            audio,
            self._ctx.cache,
            name=str(kwargs.get("name", name)),
            azimuth=float(kwargs.get("azimuth", azimuth)),
            elevation=float(kwargs.get("elevation", elevation)),
        )
        self._ctx.cache.write_object_scene(scene)
        return (scene,)


@register_node
class RenderObjectScene(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"scene": ("OBA",)},
            "optional": {"output": ("STRING", {"default": "stereo"})},
        }

    def run(self, scene: ObjectScene, output: str = "stereo", **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        output = str(kwargs.get("output", output))
        rendered = render_object_scene(scene, self._ctx.cache, output_layout=output)
        layout = "5.1" if output == "5.1" else "stereo"
        buffer = AudioBuffer.from_planar(
            rendered,
            scene.sample_rate,
            source_node_type="RenderObjectScene",
            channel_layout=layout,
        )
        buffer.encoding_scheme = f"Object scene render ({layout} pan)"
        buffer.spatial_meta = {"object_count": len(scene.objects), "bed_count": len(scene.beds)}
        self._ctx.cache.write_audio(buffer, rendered)
        return (buffer,)


@register_node
class ObjectPlacement(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    RETURN_TYPES = ("OBA",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"scene": ("OBA",)},
            "optional": {
                "model": ("MODEL_REF", {"default": "object-placement-heuristic"}),
                "spread_deg": ("FLOAT", {"default": 90.0}),
            },
        }

    def run(
        self,
        scene: ObjectScene,
        model: str = "object-placement-heuristic",
        spread_deg: float = 90.0,
        **kwargs,
    ) -> tuple[ObjectScene]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        spread_deg = float(kwargs.get("spread_deg", spread_deg))
        loaded = self._ctx.cache.load_object_scene(scene.id)
        objects = loaded.objects
        if len(objects) > 1:
            step = spread_deg / (len(objects) - 1)
            start = -spread_deg / 2
            for index, obj in enumerate(objects):
                obj.setdefault("position", {})
                obj["position"]["azimuth"] = start + step * index
        loaded.source_node_type = "ObjectPlacement"
        for obj in loaded.objects:
            obj.setdefault("metadata", {})["placement_model"] = str(kwargs.get("model", model))
        self._ctx.cache.write_object_scene(loaded)
        return (loaded,)


@register_node
class ObjectMerge(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    RETURN_TYPES = ("OBA",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scene_a": ("OBA",),
                "scene_b": ("OBA",),
            },
        }

    def run(self, scene_a: ObjectScene, scene_b: ObjectScene, **kwargs) -> tuple[ObjectScene]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        loaded_a = self._ctx.cache.load_object_scene(scene_a.id)
        loaded_b = self._ctx.cache.load_object_scene(scene_b.id)
        merged = merge_object_scenes(loaded_a, loaded_b)
        self._ctx.cache.write_object_scene(merged)
        return (merged,)


@register_node
class ObjectAnimate(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    RETURN_TYPES = ("OBA",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"scene": ("OBA",)},
            "optional": {
                "object_id": ("STRING", {"default": ""}),
                "azimuth_start": ("FLOAT", {"default": -45.0}),
                "azimuth_end": ("FLOAT", {"default": 45.0}),
                "gain_start_db": ("FLOAT", {"default": 0.0}),
                "gain_end_db": ("FLOAT", {"default": 0.0}),
            },
        }

    def run(
        self,
        scene: ObjectScene,
        object_id: str = "",
        azimuth_start: float = -45.0,
        azimuth_end: float = 45.0,
        gain_start_db: float = 0.0,
        gain_end_db: float = 0.0,
        **kwargs,
    ) -> tuple[ObjectScene]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        loaded = self._ctx.cache.load_object_scene(scene.id)
        target = str(kwargs.get("object_id", object_id)).strip() or None
        animated = apply_object_animation(
            loaded,
            azimuth_start=float(kwargs.get("azimuth_start", azimuth_start)),
            azimuth_end=float(kwargs.get("azimuth_end", azimuth_end)),
            gain_start_db=float(kwargs.get("gain_start_db", gain_start_db)),
            gain_end_db=float(kwargs.get("gain_end_db", gain_end_db)),
            object_id=target,
        )
        self._ctx.cache.write_object_scene(animated)
        return (animated,)
