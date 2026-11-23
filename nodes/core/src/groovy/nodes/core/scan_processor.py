"""Offline Rutt/Etra-style scan processor — video luma → Z terrain → raster VIDEO."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from groovy.executor.audio import AudioBuffer
from groovy.executor.control import AutomationBuffer
from groovy.executor.image import ImageClip, probe_image_dimensions
from groovy.executor.media_io import (
    probe_video_duration_seconds,
    read_video_gray_frames,
    write_rgb_frames_to_mp4,
)
from groovy.executor.video import VideoClip
from groovy.node import GroovyNode, register_node
from groovy.nodes.core.modular_synth import automation_or_const

def _load_mono(ctx, buf: AudioBuffer, frame_count: int | None = None) -> np.ndarray:
    _, pcm = ctx.cache.load_audio(buf.id)
    pcm = np.asarray(pcm, dtype=np.float64)
    if pcm.ndim == 1:
        mono = pcm
    else:
        mono = np.mean(pcm, axis=0)
    if frame_count is None:
        return mono
    if mono.size == frame_count:
        return mono
    if mono.size == 0:
        return np.zeros(frame_count, dtype=np.float64)
    x_old = np.linspace(0.0, 1.0, mono.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, frame_count, endpoint=False)
    return np.interp(x_new, x_old, mono).astype(np.float64)


def _signal_or_default(
    ctx,
    *,
    curve: AutomationBuffer | None,
    audio: AudioBuffer | None,
    frame_count: int,
    default: float,
) -> np.ndarray:
    """Prefer AUDIO (audio-rate deflection) when both are wired."""
    if audio is not None:
        return _load_mono(ctx, audio, frame_count)
    if curve is not None:
        return automation_or_const(curve, frame_count, default)
    return np.full(frame_count, float(default), dtype=np.float64)


def _load_plate_gray(path, width: int, height: int) -> np.ndarray | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            gray = img.convert("L").resize((width, height), Image.Resampling.LANCZOS)
            return np.asarray(gray, dtype=np.float64) / 255.0
    except Exception:
        return None


def _calibration_luma(width: int, height: int) -> np.ndarray:
    """Default plate when no IMAGE/VIDEO — soft bars so Z Push is visible."""
    ys = np.linspace(0.0, 1.0, height)[:, None]
    xs = np.linspace(0.0, 1.0, width)[None, :]
    bars = 0.5 + 0.5 * np.sin(xs * np.pi * 6.0)
    vignette = 0.55 + 0.45 * (1.0 - (2.0 * ys - 1.0) ** 2)
    return np.clip(bars * vignette, 0.0, 1.0)


def _shape_luma(
    luma: np.ndarray,
    *,
    threshold: float,
    contrast: float,
    gamma: float,
) -> np.ndarray:
    x = np.clip(luma, 0.0, 1.0)
    x = (x - float(threshold)) / max(1e-6, 1.0 - float(threshold))
    x = np.clip(x, 0.0, 1.0)
    mid = 0.5
    x = mid + (x - mid) * float(contrast)
    x = np.clip(x, 0.0, 1.0)
    g = max(0.2, float(gamma))
    return np.power(x, g)


def _linearity_map(u: np.ndarray, amount: float) -> np.ndarray:
    """Edge stretch (amount>0) or center stretch (amount<0). ``u`` in 0..1."""
    a = float(np.clip(amount, -1.0, 1.0))
    if abs(a) < 1e-6:
        return u
    # Smoothstep-ish warp around mid.
    t = u * 2.0 - 1.0
    if a > 0:
        t = np.sign(t) * (np.abs(t) ** (1.0 + 2.0 * a))
    else:
        t = np.sign(t) * (np.abs(t) ** (1.0 / (1.0 - 2.0 * a)))
    return np.clip(0.5 * (t + 1.0), 0.0, 1.0)


def _phosphor_rgb(hue: float, sat: float = 0.85) -> np.ndarray:
    """HSV → RGB phosphor tint. ``sat=0`` is grayscale (Vasulka Scan Studies / film-of-CRT)."""
    s = float(np.clip(sat, 0.0, 1.0))
    v = 1.0
    if s < 1e-6:
        return np.array([1.0, 1.0, 1.0], dtype=np.float64)
    h = float(hue) % 1.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return np.array([r, g, b], dtype=np.float64)


def _stamp_polyline(
    canvas: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    bright: np.ndarray,
    phosphor: np.ndarray,
) -> None:
    """Stamp densified polyline samples with a fixed 3×3 soft kernel (bloom via gaussian later)."""
    height, width, _ = canvas.shape
    # Adaptive densify: more samples on long segments so wires stay continuous under Z push.
    dx = np.diff(xs)
    dy = np.diff(ys)
    seg_len = np.hypot(dx, dy)
    # Cap total stamps per line for bake time while keeping visual continuity.
    steps = np.clip(np.ceil(seg_len).astype(np.int32), 1, 6)
    pieces_x: list[np.ndarray] = []
    pieces_y: list[np.ndarray] = []
    pieces_b: list[np.ndarray] = []
    for i, n in enumerate(steps):
        if n <= 1:
            pieces_x.append(xs[i : i + 1])
            pieces_y.append(ys[i : i + 1])
            pieces_b.append(bright[i : i + 1])
            continue
        t = np.linspace(0.0, 1.0, int(n), endpoint=False)
        pieces_x.append(xs[i] * (1 - t) + xs[i + 1] * t)
        pieces_y.append(ys[i] * (1 - t) + ys[i + 1] * t)
        pieces_b.append(bright[i] * (1 - t) + bright[i + 1] * t)
    pieces_x.append(xs[-1:])
    pieces_y.append(ys[-1:])
    pieces_b.append(bright[-1:])
    sx = np.concatenate(pieces_x)
    sy = np.concatenate(pieces_y)
    sb = np.concatenate(pieces_b)
    mask = (sb > 1e-4) & np.isfinite(sx) & np.isfinite(sy)
    if not np.any(mask):
        return
    sx = sx[mask]
    sy = sy[mask]
    sb = sb[mask]
    # Soft 3×3 kernel (center-weighted) before CRT bloom.
    offsets = (
        (0, 0, 1.0),
        (-1, 0, 0.45),
        (1, 0, 0.45),
        (0, -1, 0.45),
        (0, 1, 0.45),
        (-1, -1, 0.22),
        (-1, 1, 0.22),
        (1, -1, 0.22),
        (1, 1, 0.22),
    )
    xi0 = np.rint(sx).astype(np.int32)
    yi0 = np.rint(sy).astype(np.int32)
    for dy, dx, w in offsets:
        yy = yi0 + dy
        xx = xi0 + dx
        inside = (yy >= 0) & (yy < height) & (xx >= 0) & (xx < width)
        if not np.any(inside):
            continue
        gain = (sb[inside] * w)[:, None] * phosphor[None, :]
        np.add.at(canvas, (yy[inside], xx[inside]), gain)


def _draw_scanlines(
    canvas: np.ndarray,
    px: np.ndarray,
    py: np.ndarray,
    bright: np.ndarray,
    phosphor: np.ndarray,
) -> None:
    """``px/py/bright`` shaped ``(lines, cols)`` — continuous phosphor wires."""
    lines, _cols = px.shape
    for li in range(lines):
        _stamp_polyline(canvas, px[li], py[li], bright[li], phosphor)


def render_scan_frames(
    *,
    x: np.ndarray,
    y: np.ndarray,
    beam: np.ndarray,
    z_mod: np.ndarray,
    rot_mod: np.ndarray,
    width: int,
    height: int,
    fps: float,
    sample_rate: int,
    luma_stack: np.ndarray,
    h_position: float,
    v_position: float,
    h_size: float,
    v_size: float,
    aspect: float,
    z_push: float,
    z_bias: float,
    z_invert: bool,
    intensity: float,
    focus: float,
    rotation_deg: float,
    display_90: bool,
    h_spin_rate: float,
    v_spin_rate: float,
    luma_threshold: float,
    luma_contrast: float,
    luma_gamma: float,
    h_linearity: float,
    v_linearity: float,
    mirror_h: bool,
    mirror_v: bool,
    scan_lines: int,
    phosphor_hue: float,
    phosphor_sat: float = 0.85,
) -> np.ndarray:
    """Bake a Rutt/Etra-style scanline terrain from luma + CV."""
    frame_count = int(x.shape[0])
    n_video = max(1, int(round(frame_count / max(sample_rate, 1) * max(fps, 1.0))))
    samples_per_frame = max(1, frame_count // n_video)
    lines = max(12, min(int(scan_lines), height))
    # Visual quality: dense columns (cap for bake time).
    cols = max(64, min(width, 480))
    frames = np.zeros((n_video, height, width, 3), dtype=np.float64)
    phosphor = _phosphor_rgb(phosphor_hue, phosphor_sat)

    # Prepare / loop luma stack to n_video.
    if luma_stack.ndim != 3 or luma_stack.shape[0] < 1:
        luma_stack = np.stack([_calibration_luma(cols, lines)] * n_video, axis=0)
    else:
        # Resize each source frame to (lines, cols) sampling grid.
        resized = []
        for fi in range(luma_stack.shape[0]):
            src = luma_stack[fi]
            # Bilinear via simple index (source may already be sized).
            yy = np.linspace(0, src.shape[0] - 1, lines)
            xx = np.linspace(0, src.shape[1] - 1, cols)
            y0 = np.floor(yy).astype(np.int32)
            x0 = np.floor(xx).astype(np.int32)
            y1 = np.clip(y0 + 1, 0, src.shape[0] - 1)
            x1 = np.clip(x0 + 1, 0, src.shape[1] - 1)
            wy = (yy - y0)[:, None]
            wx = (xx - x0)[None, :]
            y0 = np.clip(y0, 0, src.shape[0] - 1)
            x0 = np.clip(x0, 0, src.shape[1] - 1)
            top = src[y0[:, None], x0[None, :]] * (1 - wx) + src[y0[:, None], x1[None, :]] * wx
            bot = src[y1[:, None], x0[None, :]] * (1 - wx) + src[y1[:, None], x1[None, :]] * wx
            resized.append(top * (1 - wy) + bot * wy)
        luma_stack = np.stack(resized, axis=0)
        if luma_stack.shape[0] < n_video:
            reps = int(np.ceil(n_video / luma_stack.shape[0]))
            luma_stack = np.tile(luma_stack, (reps, 1, 1))[:n_video]
        else:
            luma_stack = luma_stack[:n_video]

    if mirror_h:
        luma_stack = luma_stack[:, :, ::-1]
    if mirror_v:
        luma_stack = luma_stack[:, ::-1, :]

    cx = (width - 1) * 0.5
    cy = (height - 1) * 0.5
    duration_sec = frame_count / max(sample_rate, 1)

    for fi in range(n_video):
        start = fi * samples_per_frame
        stop = min(frame_count, start + samples_per_frame)
        chunk_x = x[start:stop]
        chunk_y = y[start:stop]
        chunk_b = beam[start:stop]
        chunk_z = z_mod[start:stop]
        chunk_r = rot_mod[start:stop]
        if chunk_x.size < 2:
            chunk_x = np.pad(chunk_x, (0, max(0, 2 - chunk_x.size)), mode="edge")
            chunk_y = np.pad(chunk_y, (0, max(0, 2 - chunk_y.size)), mode="edge")
            chunk_b = np.pad(chunk_b, (0, max(0, 2 - chunk_b.size)), mode="edge")
            chunk_z = np.pad(chunk_z, (0, max(0, 2 - chunk_z.size)), mode="edge")
            chunk_r = np.pad(chunk_r, (0, max(0, 2 - chunk_r.size)), mode="edge")

        u = np.linspace(0.0, 1.0, cols, endpoint=True)
        t = np.linspace(0.0, 1.0, chunk_x.size, endpoint=True)
        sx = np.interp(u, t, chunk_x)
        sy = np.interp(u, t, chunk_y)
        sb = np.interp(u, t, chunk_b)
        sz = float(np.mean(chunk_z))
        sr = float(np.mean(chunk_r))

        luma = _shape_luma(
            luma_stack[fi],
            threshold=luma_threshold,
            contrast=luma_contrast,
            gamma=luma_gamma,
        )
        if z_invert:
            luma = 1.0 - luma

        u_lin = _linearity_map(u, h_linearity)
        v = np.linspace(0.0, 1.0, lines, endpoint=True)
        v_lin = _linearity_map(v, v_linearity)

        # Normalized mesh coords before size/position (−1..1).
        mesh_x = (u_lin * 2.0 - 1.0)[None, :]  # (1, cols)
        mesh_y = (v_lin * 2.0 - 1.0)[:, None]  # (lines, 1)
        z = float(z_bias) + (float(z_push) + sz) * luma  # (lines, cols)

        # Screen mapping (Z lifts the scanline — classic Rutt/Etra terrain).
        world_x = mesh_x * float(h_size) * float(aspect)
        world_y = mesh_y * float(v_size)
        # Mild perspective foreshortening from depth.
        persp = 1.0 / (1.0 + 0.35 * np.clip(z, -2.0, 4.0))
        px = cx + (width * 0.42) * (
            world_x * persp + float(h_position) + float(h_size) * 0.15 * sx[None, :]
        )
        py = cy + (height * 0.42) * (
            world_y * persp
            - z * 0.55
            + float(v_position)
            + float(v_size) * 0.12 * sy[None, :]
        )
        if px.shape != (lines, cols):
            px = np.broadcast_to(px, (lines, cols)).copy()
        if py.shape != (lines, cols):
            py = np.broadcast_to(py, (lines, cols)).copy()

        # Rotation (display 90° + continuous + spin + CV).
        t_sec = (fi + 0.5) / max(fps, 1.0)
        angle = np.deg2rad(float(rotation_deg) + sr * 45.0)
        angle += float(h_spin_rate) * t_sec
        angle += float(v_spin_rate) * t_sec * 0.7
        if display_90:
            angle += 0.5 * np.pi
        cos_a = float(np.cos(angle))
        sin_a = float(np.sin(angle))
        rx = px - cx
        ry = py - cy
        px = cx + cos_a * rx - sin_a * ry
        py = cy + sin_a * rx + cos_a * ry

        bright = np.clip(
            float(intensity)
            * (0.2 + 0.8 * luma)
            * (0.65 + 0.35 * (0.5 + 0.5 * sb[None, :])),
            0.0,
            2.0,
        )
        if bright.shape != (lines, cols):
            bright = np.broadcast_to(bright, (lines, cols)).copy()

        canvas = frames[fi]
        _draw_scanlines(canvas, px, py, bright, phosphor)

        # Soft CRT bloom from focus (primary softness — stamp stays sharp underneath).
        sigma = 0.25 + 2.0 * float(focus)
        if sigma > 0.35:
            for c in range(3):
                canvas[:, :, c] = gaussian_filter(canvas[:, :, c], sigma=sigma * 0.55)

        # Specular sheen on hot phosphors (shiny look / high intensity×focus).
        sheen = float(np.clip(float(intensity) * float(focus) - 0.55, 0.0, 1.0))
        if sheen > 0.05:
            hot = np.clip(canvas - 0.55, 0.0, 1.0)
            glow = gaussian_filter(np.max(hot, axis=2), sigma=1.2 + 2.5 * sheen)
            canvas += (glow[:, :, None] * phosphor[None, None, :]) * (0.55 * sheen)

        peak = float(np.max(canvas)) or 1.0
        if peak > 1.0:
            canvas *= 1.0 / peak
        np.clip(canvas, 0.0, 1.0, out=canvas)

    _ = duration_sec  # reserved for future blanking sync
    return (frames * 255.0).astype(np.uint8)


@register_node
class ScanProcessor(GroovyNode):
    """Rutt/Etra-style offline scan processor — video/image luma → Z terrain VIDEO."""

    CATEGORY = "GroovyUI/Modular"
    EXPORT_TIER = "STUDIO_ONLY"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = True
    CACHEABLE = True
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("VIDEO",)
    OUTPUT_NAMES = ("video",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                # Deflection / mod CV
                "x": ("AUTOMATION",),
                "y": ("AUTOMATION",),
                "beam": ("AUTOMATION",),
                "z_push_cv": ("AUTOMATION",),
                "rotation_cv": ("AUTOMATION",),
                "x_audio": ("AUDIO",),
                "y_audio": ("AUDIO",),
                "beam_audio": ("AUDIO",),
                # Picture (luma → Z)
                "video": ("VIDEO",),
                "image": ("IMAGE",),
                # Look presets (Inspector applies matching DCU values when changed)
                "look": (
                    "STRING",
                    {
                        "default": "Scan Studies",
                        "choices": [
                            "Classic 1974",
                            "Phosphor Green",
                            "Amber Terminal",
                            "Wireframe",
                            "Heavy Bloom",
                            "Burn-In",
                            "Noise Terrain",
                            "Lissajous Spin",
                            "Worley Cells",
                            "Display 90",
                            "Scan Studies",
                        ],
                        "description": (
                            "Factory looks inspired by Rutt/Etra Web + Vasulka Scan Processor "
                            "Studies (Scan Studies = grayscale). Picking a look loads DCU values."
                        ),
                    },
                ),
                # Position & size (bipolar size mirrors when negative)
                "h_position": ("FLOAT", {"default": 0.0, "min": -1.5, "max": 1.5}),
                "v_position": ("FLOAT", {"default": 0.0, "min": -1.5, "max": 1.5}),
                "h_size": ("FLOAT", {"default": 1.0, "min": -2.0, "max": 2.0}),
                "v_size": ("FLOAT", {"default": 1.0, "min": -2.0, "max": 2.0}),
                "aspect": ("FLOAT", {"default": 1.333, "min": 0.4, "max": 2.5}),
                # Depth
                "z_push": ("FLOAT", {"default": 1.25, "min": -5.0, "max": 5.0}),
                "z_bias": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0}),
                "z_invert": ("BOOLEAN", {"default": False}),
                # Beam
                "intensity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0}),
                "focus": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0}),
                "phosphor_hue": ("FLOAT", {"default": 0.33, "min": 0.0, "max": 1.0}),
                "phosphor_sat": (
                    "FLOAT",
                    {
                        "default": 0.85,
                        "min": 0.0,
                        "max": 1.0,
                        "description": "0 = grayscale (Vasulka Scan Studies); ~0.85 = phosphor tint.",
                    },
                ),
                # Rotation
                "rotation_deg": ("FLOAT", {"default": -18.0, "min": -180.0, "max": 180.0}),
                "display_90": ("BOOLEAN", {"default": False}),
                "h_spin_rate": ("FLOAT", {"default": 0.0, "min": -3.0, "max": 3.0}),
                "v_spin_rate": ("FLOAT", {"default": 0.0, "min": -3.0, "max": 3.0}),
                # Luminance
                "luma_threshold": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.95}),
                "luma_contrast": ("FLOAT", {"default": 1.35, "min": 0.2, "max": 4.0}),
                "luma_gamma": ("FLOAT", {"default": 0.9, "min": 0.3, "max": 2.5}),
                # Linearity / mirrors
                "h_linearity": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0}),
                "v_linearity": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0}),
                "mirror_h": ("BOOLEAN", {"default": False}),
                "mirror_v": ("BOOLEAN", {"default": True}),
                # Scan
                "scan_lines": ("INT", {"default": 120, "min": 16, "max": 360}),
                "scan_rate": ("FLOAT", {"default": 1.0, "min": 0.25, "max": 3.0}),
                # Output
                "width": ("INT", {"default": 640, "min": 160, "max": 1280}),
                "height": ("INT", {"default": 480, "min": 120, "max": 720}),
                "fps": ("FLOAT", {"default": 24.0, "min": 6.0, "max": 60.0}),
                "duration_sec": ("FLOAT", {"default": 4.0, "min": 0.25, "max": 30.0}),
                "sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 96000}),
            },
        }

    def run(self, **kwargs) -> tuple[VideoClip]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")

        sample_rate = int(np.clip(int(kwargs.get("sample_rate", 48000)), 8000, 96000))
        duration_sec = float(np.clip(float(kwargs.get("duration_sec", 4.0)), 0.25, 30.0))
        fps = float(np.clip(float(kwargs.get("fps", 24.0)), 6.0, 60.0))

        drivers: list[int] = []
        for key in ("x", "y", "beam", "z_push_cv", "rotation_cv"):
            curve = kwargs.get(key)
            if isinstance(curve, AutomationBuffer):
                drivers.append(int(curve.frame_count))
        for key in ("x_audio", "y_audio", "beam_audio"):
            audio = kwargs.get(key)
            if isinstance(audio, AudioBuffer):
                _, pcm = self._ctx.cache.load_audio(audio.id)
                drivers.append(max(1, int(pcm.shape[-1])))

        video_in = kwargs.get("video")
        video_duration = None
        video_path = None
        if isinstance(video_in, VideoClip) and str(video_in.path or "").strip():
            video_path = self._ctx.cache.resolve_project_path(video_in.path)
            if video_path.is_file():
                video_duration = probe_video_duration_seconds(video_path)

        if drivers:
            frame_count = max(drivers)
        elif video_duration and video_duration > 0:
            frame_count = max(1, int(round(min(duration_sec, video_duration) * sample_rate)))
        else:
            frame_count = max(1, int(round(duration_sec * sample_rate)))

        x = _signal_or_default(
            self._ctx,
            curve=kwargs.get("x") if isinstance(kwargs.get("x"), AutomationBuffer) else None,
            audio=kwargs.get("x_audio") if isinstance(kwargs.get("x_audio"), AudioBuffer) else None,
            frame_count=frame_count,
            default=0.0,
        )
        y = _signal_or_default(
            self._ctx,
            curve=kwargs.get("y") if isinstance(kwargs.get("y"), AutomationBuffer) else None,
            audio=kwargs.get("y_audio") if isinstance(kwargs.get("y_audio"), AudioBuffer) else None,
            frame_count=frame_count,
            default=0.0,
        )
        beam = _signal_or_default(
            self._ctx,
            curve=kwargs.get("beam") if isinstance(kwargs.get("beam"), AutomationBuffer) else None,
            audio=kwargs.get("beam_audio") if isinstance(kwargs.get("beam_audio"), AudioBuffer) else None,
            frame_count=frame_count,
            default=0.0,
        )
        z_mod = _signal_or_default(
            self._ctx,
            curve=kwargs.get("z_push_cv") if isinstance(kwargs.get("z_push_cv"), AutomationBuffer) else None,
            audio=None,
            frame_count=frame_count,
            default=0.0,
        )
        rot_mod = _signal_or_default(
            self._ctx,
            curve=kwargs.get("rotation_cv") if isinstance(kwargs.get("rotation_cv"), AutomationBuffer) else None,
            audio=None,
            frame_count=frame_count,
            default=0.0,
        )

        width = int(kwargs.get("width", 640))
        height = int(kwargs.get("height", 480))
        width -= width % 2
        height -= height % 2
        width = int(np.clip(width, 160, 1280))
        height = int(np.clip(height, 120, 720))

        n_video = max(1, int(round(frame_count / max(sample_rate, 1) * max(fps, 1.0))))
        scan_rate = float(np.clip(float(kwargs.get("scan_rate", 1.0)), 0.25, 3.0))
        scan_lines = int(np.clip(int(round(int(kwargs.get("scan_lines", 120)) * scan_rate)), 16, 360))

        # Luma source priority: VIDEO → IMAGE → calibration pattern.
        luma_stack: np.ndarray | None = None
        if video_path is not None and video_path.is_file():
            # Decode at mesh resolution for quality; scale happens inside renderer too.
            decode_w = min(width, 640)
            decode_h = min(height, 480)
            luma_stack = read_video_gray_frames(
                video_path,
                width=decode_w,
                height=decode_h,
                max_frames=n_video,
                fps=fps,
            )
        else:
            image = kwargs.get("image")
            if isinstance(image, ImageClip) and str(image.path or "").strip():
                resolved = self._ctx.cache.resolve_project_path(image.path)
                if resolved.is_file():
                    plate = _load_plate_gray(resolved, width, height)
                    if plate is not None:
                        luma_stack = np.stack([plate] * n_video, axis=0)
                        dims = probe_image_dimensions(resolved)
                        if dims and image.width is None:
                            image.width, image.height = dims
        if luma_stack is None:
            plate = _calibration_luma(width, height)
            luma_stack = np.stack([plate] * n_video, axis=0)

        rgb = render_scan_frames(
            x=x,
            y=y,
            beam=beam,
            z_mod=z_mod,
            rot_mod=rot_mod,
            width=width,
            height=height,
            fps=fps,
            sample_rate=sample_rate,
            luma_stack=luma_stack,
            h_position=float(kwargs.get("h_position", 0.0)),
            v_position=float(kwargs.get("v_position", 0.0)),
            h_size=float(kwargs.get("h_size", 1.0)),
            v_size=float(kwargs.get("v_size", 1.0)),
            aspect=float(kwargs.get("aspect", 1.333)),
            z_push=float(kwargs.get("z_push", 1.25)),
            z_bias=float(kwargs.get("z_bias", 0.0)),
            z_invert=bool(kwargs.get("z_invert", False)),
            intensity=float(kwargs.get("intensity", 1.0)),
            focus=float(kwargs.get("focus", 0.35)),
            rotation_deg=float(kwargs.get("rotation_deg", -18.0)),
            display_90=bool(kwargs.get("display_90", False)),
            h_spin_rate=float(kwargs.get("h_spin_rate", 0.0)),
            v_spin_rate=float(kwargs.get("v_spin_rate", 0.0)),
            luma_threshold=float(kwargs.get("luma_threshold", 0.08)),
            luma_contrast=float(kwargs.get("luma_contrast", 1.35)),
            luma_gamma=float(kwargs.get("luma_gamma", 0.9)),
            h_linearity=float(kwargs.get("h_linearity", 0.0)),
            v_linearity=float(kwargs.get("v_linearity", 0.0)),
            mirror_h=bool(kwargs.get("mirror_h", False)),
            mirror_v=bool(kwargs.get("mirror_v", True)),
            scan_lines=scan_lines,
            phosphor_hue=float(kwargs.get("phosphor_hue", 0.33)),
            phosphor_sat=float(kwargs.get("phosphor_sat", 0.85)),
        )

        clip = VideoClip.create(
            "",
            source_node_type="ScanProcessor",
            width=width,
            height=height,
            source_video_path=(
                str(video_in.source_video_path or video_in.path)
                if isinstance(video_in, VideoClip)
                else None
            ),
        )
        dest = self._ctx.cache.cache_dir / f"{clip.id}.mp4"
        write_rgb_frames_to_mp4(rgb, dest, fps=fps)
        rel = str(dest.relative_to(self._ctx.cache.project_dir)).replace("\\", "/")
        clip.path = rel
        self._ctx.cache.write_video(clip)
        return (clip,)
