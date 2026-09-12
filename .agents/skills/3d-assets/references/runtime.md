# Runtime commands

The wrapper accepts all `assetctl` arguments. In the runtime repository itself, use `uv run --no-sync python -m asset_auto.cli ...` after `uv sync`. The `--no-sync` form avoids reinstalling a Windows executable while another process is serving the viewer.

```text
doctor
generate <spec.json> [--async]
edit <changes.json> [--async]
job <job_id>
list
inspect <asset_id> <revision>
review <asset_id> <revision> --result pass|fail --notes "Specific observations"
godot <asset_id> <revision>
serve --port 8765
mcp
```

`generate` and `edit` produce GLB/source, numeric inspection and local PNG renders. They do not run Godot, launch a server, build a web app or require browser inspection. Use the host image-inspection tool to review PNGs. New generation defaults to `trellis` and requires a reference image; procedural creation is an explicit user-authorized alternative.

`godot` and `serve` are optional. Use the target project's relevant importer when integration warrants it. Start/open the viewer only for a requested interactive preview or browser check. `serve` binds only to 127.0.0.1; the viewer is http://127.0.0.1:8765/. On Windows use `start-viewer.cmd` for a retained background server. On Linux use `sh start-viewer.sh` and retain its terminal. Opening a browser does not start the server. Selecting a revision in the viewer records its Three.js load/draw result; that is not visual approval.

For first installation, personal-skill links or MCP client setup, read the repository's [INSTALL.md](../../../../INSTALL.md). This wrapper requires the shared checkout and its `.venv`; copying only the skill folder is insufficient.

Each completed revision lives in `<runtime-root>/.assets/<asset_id>/<revision>/`:

- `source.blend`: editable source; named parts survive procedural generation.
- `asset.glb`: self-contained Y-up, meter-scale engine/web export.
- `front.png`, `back.png`, `left.png`, `right.png`, `perspective.png`: actual Blender renders.
- `inspection.json`: measured geometry, per-part dimensions (Blender Z-up), materials and warnings.
- `manifest.json`: immutable generation/edit metadata, parent revision, source/tool versions, file hashes.
- `review.json`: explicit agent/human visual observations, when recorded.
- `godot.json`: real Godot import/instantiation/material/convex-collision check, when run.
- `three.json`: browser-reported GLTFLoader + WebGL draw check, when viewed.
- Worker requests/logs and, for TRELLIS, the copied input reference and raw generated GLB.

An incomplete revision has no manifest and is excluded from the library. Jobs retain success/failure and results under `.assets/jobs/`. Inspect failure logs before retrying; a failure never replaces the previous completed revision.

The runtime configuration is optional, local, and ignored by Git: `asset-system.local.json` with `blender`, `trellis`, `godot`, `models` path overrides. Environment overrides: `ASSET_AUTO_ROOT`, `ASSET_AUTO_BLENDER`, `ASSET_AUTO_TRELLIS`, `ASSET_AUTO_GODOT`, `ASSET_AUTO_MODELS`. Relative tool/model paths resolve against the runtime root.
