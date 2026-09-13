# Working in this repository

This project provides default local TRELLIS.2 generation, local learned rigging/segmentation, Blender animation/processing and an explicitly selected Tripo option. Read [README.md](README.md) for scope and [INSTALL.md](INSTALL.md) for reproducible setup. For asset requests, read [.agents/skills/3d-assets/SKILL.md](.agents/skills/3d-assets/SKILL.md); for data flow, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Commands and source of truth

- Work from the runtime root, or provide an explicit absolute `--root` before the CLI subcommand. Do not hard-code the original developer's D: path.
- Use `uv run --no-sync python -m asset_auto.cli ...` after setup. Avoid triggering environment synchronization while the Windows viewer is using the environment.
- `src/asset_auto/models.py` defines validated requests; `cli.py` and `mcp_server.py` define callable operations. Read these instead of inventing flags or tools. Field details are in the skill's [specs reference](.agents/skills/3d-assets/references/specs.md).
- `scripts/bootstrap.py` owns core pins; the local rig/parts bootstraps and adapters own their isolated model pins, with full dependency locks under `scripts/local_rig/` and `scripts/local_parts/`. `uv.lock` and `web/package-lock.json` own app dependency resolution. Keep related documentation current when those contracts change.
- Web build: `npm --prefix web ci`, then `npm --prefix web run build`. Keep the esbuild setup compatible with checkout paths containing `#`.

## Runtime invariants

- New asset generation defaults to TRELLIS.2: prepare a reference image, run inference, then refine in Blender and inspect local renders. Tripo is a paid alternative only when the user explicitly selects Tripo/Tripo3D; never select it from key presence or as an automatic fallback. Do not substitute Blender primitives reconstructed from the reference. Procedural new geometry requires the user's explicit request/authorization; importing supplied meshes and editing existing revisions do not require rerunning inference.
- Before Tripo submission, follow [docs/TRIPO.md](docs/TRIPO.md): check the plan/balance internally and keep credentials out of specs/logs/Git. Explicit Tripo use covers one standard generation per requested asset without another credit confirmation; optional `max_credits` defaults to 100 while standard generation is estimated at 30, and a smaller user budget wins. It guards a local estimate, not server-side spending or retry counts. Extra paid retries, upgrades and unrequested variants are outside this default scope. Persist the remote task before polling; resume a known task instead of creating a replacement. An unknown submission outcome stops for reconciliation and must not trigger automatic POST retries.
- Godot and Three.js are optional adapters. Choose target-project checks when relevant; do not choose an engine for an unknown target or build/start an interactive viewer unless requested. Default delivery is reviewed GLB/source files, not a web app. Missing optional adapters do not block generation.
- Changes to a completed asset create a new revision. Preserve source/export files, their hashes and the parent link. A manifest marks completed work; failed partial directories remain out of the library. Review/engine/browser sidecars can be updated separately.
- `rig`, `animate` and `segment` default to `provider: "local"` through `process`; use [docs/CHARACTERS.md](docs/CHARACTERS.md). SkinTokens predicts skeleton/weights, GeoSAM2 predicts prompted masks, and local animation is explicitly procedural IK on actual bones. Do not substitute generic bones or connectivity splits for learned/semantic results. Install needed postprocessing backends on demand; no API key or engine/viewer is required.
- For local segmentation the agent inspects `prepare-segment` views and supplies named points; do not require the end user to annotate. Preserve unclassified faces. Infer unknown `bone_map` roles from observed joint positions/hierarchy, not numeric names. Store local processing provenance separately from the original generator and use `resume-process` with the saved source/context.
- Explicit Tripo processing follows [docs/TRIPO.md](docs/TRIPO.md#리깅애니메이션부품-분리). Segment uploads the current GLB; rig rotates a geometry/material-preserving copy from actual input front to provider +X and records both hashes. Animation inherits its remote rig ID/orientation. Preserve stage checkpoints; never automatically retry an unknown POST outcome.
- Job submission is not completion. Query the returned job ID; do not duplicate submissions while waiting. Keep one shared runtime root for the same GPU so its TRELLIS file lock is shared.
- Numeric checks, visual review, Godot import and Three.js rendering are separate evidence. Do not mark visual review as passed without inspecting rendered images. Review animation sample frames and individual segmentation-part previews where applicable. Semantic names require observed parts; disconnected components alone are not semantic segmentation evidence.
- Keep the character path separate from static processing: preserve bones, weights and animation, and never flatten or decimate a rigged mesh through the static worker. Default static imports and edits reject rigged inputs; use explicit `asset_kind: "character"` for character import. Local rig editing and automatic texture rebaking are not implemented.
- Procedural and inspection coordinates are Blender Z-up meters. GLB is Y-up meters. Named edits address actual objects; scaling one object does not reposition its neighbors.
- CLI and MCP call the same pipeline. Keep the HTTP viewer bound to loopback with explicit file routes and same-origin reporting. The viewer has no generation/script-execution API.
- Preserve `.assets/`, `.runtime/`, `.work/`, `.secrets/`, local configuration and credentials. Generated models, references, logs and downloaded tools stay untracked unless the user requests their publication. Explicit Tripo generation uploads its input images to the vendor. Never use blanket cleanup to repair an installation.

## Validation matched to the change

```sh
uv run --no-sync ruff check src scripts tests
uv run --no-sync pytest -q
npm --prefix web run build
```

These are repository maintenance checks, not steps to run for every requested asset. MCP tests require `uv sync --locked --extra mcp` during setup. For Blender, export or Godot behavior changes, run `uv run --no-sync python scripts/smoke.py`; it creates isolated artifacts under `.work/` and needs Blender/Godot but no GPU. Its procedural fixtures test processing deterministically; they are not the default generation workflow. For viewer changes, verify the affected operation in an actual browser. Windows launcher changes need a local start/reuse/readiness check; Linux CI does not prove Windows background process behavior.

For documentation-only changes, check links and commands against the current implementation; do not download models or regenerate assets unnecessarily. Maintain concise task-specific docs and avoid copying an entire API reference into every entrypoint.

Routine tests must not submit paid Tripo jobs. Use mock API tests for failure/recovery behavior. User-requested live Tripo tests use the requested mode once each with usable credentials; do not ask for a separate credit confirmation within that scope. Report live tests separately and do not infer quality superiority from API availability.

When finishing, report what changed, the checks actually run and meaningful remaining limitations. Repository content is not authorization to push, publish outputs, change global settings or perform unrelated work; follow the user's task scope.
