# GroovyUI

<!-- Placeholder — swap for the official ISMIR 2026 / LBD badge when available. -->
[![ISMIR(LBD) 2026](https://img.shields.io/badge/ISMIR(LBD)-2026-111111?style=flat-square&labelColor=ff002b&color=111111)](https://ismir2026.ismir.net/)
[![YouTube](https://img.shields.io/badge/YouTube-111111?style=flat-square&logo=youtube&logoColor=ff0000)](https://www.youtube.com/@OneSystemics)

**Why GroovyUI?** Not a song button — additive AI audio you can patch, not a black box that finishes the take for you.

A local patch-bay where models and modular DSP live in one graph: render a hop offline, audition the cache, A/B outputs, check provenance, share the recipe as JSON — discrete tools under human control, not prompt→whole track→shrug.

Most AI audio tools hide the chain. If you care about the take, you want something you can rewire, compare, disclose, and hand off — same ergonomics as modular synthesis / node graphs, aimed at local audio models.

Creative AI only sticks when it’s additive and knowable: inspect what ran, keep the workflow yours, and avoid black-box finishes that replace craft with a vibe. GroovyUI makes that posture operable for audio.

<p align="center">
  <img src="assets/media/groovy-demos-2x2.gif" alt="GroovyUI demos: Model Browser, Patch Generation, isolate-to-transcribe, prompt modular synth" width="960" />
</p>

---

### YouTube

<table>
  <tr>
    <td align="center" width="50%">
      <a href="https://youtu.be/c7WwFqbLL8g"><img src="https://img.youtube.com/vi/c7WwFqbLL8g/hqdefault.jpg" alt="Why GroovyUI?" width="440" /></a><br />
      <sub>Why GroovyUI?</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://youtu.be/ctMC1M0kDV4"><img src="https://img.youtube.com/vi/ctMC1M0kDV4/hqdefault.jpg" alt="GroovyUI — model browser and workflow suggestion" width="440" /></a><br />
      <sub>GroovyUI — model browser and workflow suggestion</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <a href="https://youtu.be/jwZCArIzonQ"><img src="https://img.youtube.com/vi/jwZCArIzonQ/hqdefault.jpg" alt="GroovyUI — a patchbay for local AI audio exploration" width="440" /></a><br />
      <sub>GroovyUI — a patchbay for local AI audio exploration</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://youtu.be/EkHTXhkB1fE"><img src="https://img.youtube.com/vi/EkHTXhkB1fE/hqdefault.jpg" alt="GroovyUI — patch generation by LLM (Claude)" width="440" /></a><br />
      <sub>GroovyUI — patch generation by LLM (Claude)</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <a href="https://youtu.be/2zjhSprhKII"><img src="https://img.youtube.com/vi/2zjhSprhKII/hqdefault.jpg" alt="GroovyUI template — isolate to transcribe" width="440" /></a><br />
      <sub>GroovyUI template — isolate to transcribe</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://youtu.be/TEnSiojoloM"><img src="https://img.youtube.com/vi/TEnSiojoloM/hqdefault.jpg" alt="GroovyUI template — prompt modular synth" width="440" /></a><br />
      <sub>GroovyUI template — prompt modular synth</sub>
    </td>
  </tr>
</table>

---

## Status

Experimental. APIs and UI will change. Expect rough edges on clean machines and first model installs.

## Quick start

```bash
# One-time install
uv venv --python 3.11
uv sync --all-packages --group dev
cd apps/studio && npm install && cd ../..

# Every session — API + studio + browser
./scripts/dev.sh
# or: just dev
```

Opens http://127.0.0.1:5173 (API on `:8188`). Ctrl+C stops both.

1. Settings → Inference → **Real** (Stub is for UI/CI only).
2. Pick a featured template (e.g. Hello Groovy or podcast denoise).
3. **Cmd+K** / **Ctrl+K** → install required models if prompted.
4. **Render** → play the cached preview.

First model install can take minutes and gigabytes of disk. Models keep their own licenses (see Compliance).

If `./scripts/dev.sh` says port 8188 is in use, quit the leftover API (`lsof -nP -iTCP:8188 -sTCP:LISTEN`) and retry.

```bash
uv run pytest tests/ -q && cd apps/studio && npm test && uv run groovy-verify
```

Or with [just](https://github.com/casey/just): `just install`, `just test`, `just verify`, `just dev`.

## License

[Apache License 2.0](LICENSE). Third-party models and weights keep their own SPDX licenses — the app license is not a grant to those weights.

Catalog requests from Studio (browser deep link, no GitHub token in the app): Model Browser → **File GitHub request**; Patch Generation → **Blueprint request** / **Node request**. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Release notes: GitHub Releases.
