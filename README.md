# 3D Asset Auto

Local 3D asset tools for coding agents, with a Korean Three.js asset viewer.

The first implemented workflow is **static prop creation → named-part edits → Blender inspection and renders → GLB → Godot / Three.js checks**. It supports procedural recipes, TRELLIS.2 image-to-3D through trellis.cpp, and imported GLB/Blend files. Natural-language decisions belong to the included agent skill; the runtime consumes validated JSON.

## Setup

Requires Python 3.11+, uv, Node.js, and Windows/Linux x64. TRELLIS's pinned CUDA bundle requires a compatible NVIDIA GPU/driver. The initial setup downloads approximately 17 GB of F16 model weights plus portable tools; downloads and generated assets are excluded from Git.

```sh
uv sync
python scripts/bootstrap.py
```

Then run `npm ci` followed by `npm run build` in `web/`. The esbuild script supports repository paths containing `#`, including `D:/#programming/3d-asset-auto`.

```sh
uv run --no-sync python -m asset_auto.cli doctor
uv run --no-sync python -m asset_auto.cli generate examples/sword.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
uv run --no-sync python -m asset_auto.cli list
uv run --no-sync python -m asset_auto.cli serve
```

Open **http://127.0.0.1:8765/** to orbit/zoom, toggle wireframe and grid, select revisions, inspect parts and render views, and download GLBs. Refresh the library after a generation or validation completes. The viewer is local-only and serves only explicit asset files; it exposes no model-generation or arbitrary-script HTTP endpoint.

`--async` launches a separate job process. Its JSON state and logs survive the submitting agent process. Completed revisions are immutable; edit operations create a new revision with a parent link. Failed work is retained for diagnosis and excluded from the asset library.

## Agent skill

The repository skill is `.agents/skills/3d-assets/SKILL.md`. It covers provider choice, spec construction, partial-edit semantics, visual QA, Godot tests and browser checks. For use from another project, link or install this folder in your agent's personal skills directory. The wrapper resolves this repository automatically.

Example prompts:

- “Create a stylized wooden chest for the game, under 12k triangles; check it in Godot and the web viewer.”
- “Use this reference image to generate a 75 cm prop, then inspect the back and side views.”
- “Change only the grip of the existing sword to burgundy and keep the prior version.”

See the skill's `references/specs.md` for the actual request schema. `prompt` is stored as provenance; it does **not** call an image-generation API. An agent can supply a user image or invoke an available image-generation tool before submitting TRELLIS work.

## Validation

```sh
uv run --no-sync python -m asset_auto.cli inspect ASSET_ID REVISION
uv run --no-sync python -m asset_auto.cli godot ASSET_ID REVISION
uv run --no-sync python -m asset_auto.cli review ASSET_ID REVISION --result pass --notes "Specific observations after opening renders"
uv run --no-sync pytest -q
uv run --no-sync ruff check src scripts tests
```

Each revision includes editable `source.blend`, self-contained `asset.glb`, five PNG renders, numeric inspection, file hashes, and a toolchain manifest. Godot actually imports and instantiates the GLB, checks meshes/materials, and creates convex collision shapes. Three.js actually loads the GLB and draws it using WebGL. Neither substitutes for visual review or testing within the destination game's real scene.

## Optional MCP adapter

Install with `uv sync --extra mcp`. A stdio client can run `uv --directory /absolute/repository/path run --no-sync python -m asset_auto.cli mcp` with `ASSET_AUTO_ROOT` set to that repository. Tools: capability discovery, generation, edits, job status, asset listing, inspection, and Godot validation. MCP performs the same operations as the CLI; it does not own a second copy of pipeline logic.

## Current boundaries

- Static meshes only; armatures are rejected to avoid damaging rigs.
- No multi-image conditioning, auto-rigging, control rigs, animation retargeting, or animation-quality retopology yet.
- Generated meshes may have no semantic parts. Named-part edits work only for actual named objects.
- Decimation is a geometry reduction operation, not a texture rebake; inspect texture seams and silhouette afterward.
- Blender renders use CPU Cycles to leave VRAM available to generation. TRELLIS uses the GPU.
- Source and export conventions: Blender Z-up internally; GLB Y-up, meters. Existing imported hierarchies are flattened for static normalization.
- Windows integration is exercised on this machine. Linux paths are implemented, but Linux GPU/Blender end-to-end tests require a Linux host.

## Dependencies and provenance

Pinned portable tool downloads and model revision are in `scripts/bootstrap.py`; SHA256 results are saved locally under `.runtime/installed/`. Tool executables and model weights are not redistributed in this repository.

- [Blender](https://www.blender.org/) 4.5 LTS: procedural modeling, edits, inspections, render and export.
- [trellis.cpp](https://github.com/pwilkin/trellis.cpp) v0.6.0: native TRELLIS.2 inference, CUDA bundle.
- [TRELLIS.2](https://github.com/microsoft/TRELLIS.2): underlying 3D model.
- [GGUF conversion](https://huggingface.co/ilintar/trellis2-gguf): pinned F16 weights with upstream LFS hashes.
- [Godot](https://godotengine.org/): real headless engine import checks.
- [Three.js](https://threejs.org/): local browser rendering, bundled from npm.

Code, model weights and helper models have separate licenses; a parent repository's license is not a blanket license for every dependency. The GGUF pipeline includes DINOv3/BiRefNet and other components listed upstream. Review the exact pinned components for your intended distribution/use. Hunyuan is not included. No commercial clearance is claimed by this prototype.
