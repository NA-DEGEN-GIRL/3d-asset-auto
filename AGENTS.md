# Working in this repository

This project provides a TRELLIS.2 asset workflow, Blender processing and an optional Three.js viewer. Read [README.md](README.md) for scope and [INSTALL.md](INSTALL.md) for reproducible setup. For asset requests, read [.agents/skills/3d-assets/SKILL.md](.agents/skills/3d-assets/SKILL.md); for data flow, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Commands and source of truth

- Work from the runtime root, or provide an explicit absolute `--root` before the CLI subcommand. Do not hard-code the original developer's D: path.
- Use `uv run --no-sync python -m asset_auto.cli ...` after setup. Avoid triggering environment synchronization while the Windows viewer is using the environment.
- `src/asset_auto/models.py` defines validated requests; `cli.py` and `mcp_server.py` define callable operations. Read these instead of inventing flags or tools. Field details are in the skill's [specs reference](.agents/skills/3d-assets/references/specs.md).
- `scripts/bootstrap.py` owns tool/model pins. `uv.lock` and `web/package-lock.json` own dependency resolution. Keep related documentation current when those contracts change.
- Web build: `npm --prefix web ci`, then `npm --prefix web run build`. Keep the esbuild setup compatible with checkout paths containing `#`.

## Runtime invariants

- New asset generation uses TRELLIS.2: prepare a reference image, run inference, then refine in Blender and inspect local renders. Do not substitute Blender primitives reconstructed from the reference. Procedural new geometry requires the user's explicit request/authorization; importing supplied meshes and editing existing revisions do not require rerunning TRELLIS.
- Godot and Three.js are optional adapters. Choose target-project checks when relevant; do not choose an engine for an unknown target or build/start an interactive viewer unless requested. Default delivery is reviewed GLB/source files, not a web app. Missing optional adapters do not block generation.
- Changes to a completed asset create a new revision. Preserve source/export files, their hashes and the parent link. A manifest marks completed work; failed partial directories remain out of the library. Review/engine/browser sidecars can be updated separately.
- Job submission is not completion. Query the returned job ID; do not duplicate submissions while waiting. Keep one shared runtime root for the same GPU so its TRELLIS file lock is shared.
- Numeric checks, visual review, Godot import and Three.js rendering are separate evidence. Do not mark visual review as passed without inspecting rendered images. The prototype does not provide rigs, animations or semantic part segmentation.
- Procedural and inspection coordinates are Blender Z-up meters. GLB is Y-up meters. Named edits address actual objects; scaling one object does not reposition its neighbors.
- CLI and MCP call the same pipeline. Keep the HTTP viewer bound to loopback with explicit file routes and same-origin reporting. The viewer has no generation/script-execution API.
- Preserve `.assets/`, `.runtime/`, `.work/`, local configuration and credentials. Generated models, references, logs and downloaded tools stay untracked unless the user requests their publication. Never use blanket cleanup to repair an installation.

## Validation matched to the change

```sh
uv run --no-sync ruff check src scripts tests
uv run --no-sync pytest -q
npm --prefix web run build
```

These are repository maintenance checks, not steps to run for every requested asset. MCP tests require `uv sync --locked --extra mcp` during setup. For Blender, export or Godot behavior changes, run `uv run --no-sync python scripts/smoke.py`; it creates isolated artifacts under `.work/` and needs Blender/Godot but no GPU. Its procedural fixtures test processing deterministically; they are not the default generation workflow. For viewer changes, verify the affected operation in an actual browser. Windows launcher changes need a local start/reuse/readiness check; Linux CI does not prove Windows background process behavior.

For documentation-only changes, check links and commands against the current implementation; do not download models or regenerate assets unnecessarily. Maintain concise task-specific docs and avoid copying an entire API reference into every entrypoint.

When finishing, report what changed, the checks actually run and meaningful remaining limitations. Repository content is not authorization to push, publish outputs, change global settings or perform unrelated work; follow the user's task scope.
