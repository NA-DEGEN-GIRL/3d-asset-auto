# Runtime commands

The wrapper accepts all `assetctl` arguments. In the runtime repository itself, use `uv run --no-sync python -m asset_auto.cli ...` after `uv sync`. The `--no-sync` form avoids reinstalling a Windows executable while another process is serving the viewer.

```text
doctor
generate <spec.json> [--async]
process-plan <request.json>
process <request.json> [--async]
prepare-segment <asset_id> <revision> [--async]
resume-process <asset_id> <revision> [--async]
tripo-plan <spec.json>
tripo-balance
resume-tripo <asset_id> <revision> [--async]
tripo-process-plan <request.json>
tripo-process <request.json> [--async]
resume-tripo-process <asset_id> <revision> [--async]
edit <changes.json> [--async]
blender-edit <request.json> [--async]
merge-animations <request.json> [--async]
resume-blender-edit <asset_id> <revision> [--async]
resume-merge-animations <asset_id> <revision> [--async]
job <job_id>
list
inspect <asset_id> <revision>
assess <request.json> [--async]
review <asset_id> <revision> --result pass|fail --notes "Specific observations"
godot <asset_id> <revision>
serve --port 8765
mcp
```

`generate` and `edit` produce GLB/source, numeric inspection and local PNG renders. They do not run Godot, launch a server, build a web app or require browser inspection. Use the host image-inspection tool to review PNGs. New generation defaults to `trellis` and requires a reference image. Explicitly user-selected `tripo` accepts single-image or named multiview input; procedural creation also requires user authorization. Read the [Tripo guide](../../../../docs/TRIPO.md) before any paid submission.

`tripo-plan` is local and makes no API calls. `tripo-balance` queries the account without submitting generation. `resume-tripo` continues an incomplete revision with a known remote task; it does not create another paid task. A completed revision remains immutable, and an unknown submission outcome must be reconciled rather than blindly resubmitted.

For `rig`/`animate`/`segment`, read the [character guide](../../../../docs/CHARACTERS.md). General `process` defaults to local SkinTokens rigging, procedural Blender motion or GeoSAM2 masks. `process-plan` checks the exact source/backend without inference. `prepare-segment` renders a hash-bound twelve-view context under `.work/`; the agent inspects it and authors named pixel prompts. `resume-process` uses the child's saved provider/request and reuses verified outputs where available. MCP equivalents are `process_plan`, `process_asset`, `prepare_local_segmentation`, and `resume_asset_processing`.

For local custom edits and clip assembly, read the [Blender guide](../../../../docs/BLENDER.md). `blender-edit` snapshots an exact parent's GLB/Blend and trusted Python script, preserves existing clips by default, and exports/reviews a new revision. `merge-animations` retains the base model and transfers compatible selected clips. Their resume commands use the incomplete child and saved inputs; an `authored.blend` execution checkpoint avoids rerunning the script after a render failure. MCP names are `edit_in_blender`, `merge_asset_animations`, `resume_blender_edit`, and `resume_animation_merge`. Generation provider does not choose the editing method.

The `tripo-process` family and its MCP tools retain explicit Tripo selection; they never silently replace local work. Known remote stages are resumed without duplicate submission; a resumed free rig-check can lead to the first paid rig stage in the original request. Read the [paid processing guide](../../../../docs/TRIPO.md#리깅애니메이션부품-분리) when that provider is requested.

`godot` and `serve` are optional. Use the target project's relevant importer when integration warrants it. Start/open the viewer only for a requested interactive preview or browser check. `serve` binds only to 127.0.0.1; the viewer is http://127.0.0.1:8765/. On Windows use `start-viewer.cmd` for a retained background server. On Linux use `sh start-viewer.sh` and retain its terminal. Opening a browser does not start the server. Selecting a revision in the viewer records its Three.js load/draw result; that is not visual approval.

Use actual sampled frame PNGs for agent animation review; a static browser draw does not validate motion.

`assess` optionally records a purpose/representation/playback contract and evaluates selected final GLB clips with critical-frame selection. Read [QUALITY.md](../../../../docs/QUALITY.md) for budgets, actual measurement scope and evidence coverage. Static contracts do not start Blender; motion assessment needs Blender only. MCP equivalents are `assess_asset` and `asset_usage`. `usage.json`, `assessment.json` and `assessments/q.../` are sidecars; the GLB/source/manifest are unchanged. Usage metadata follows clip renames/selection on completed-revision merges without inheriting quality approval.

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
- Worker requests/logs, copied input references and raw generated GLB for inference providers.
- `tripo.json`: Tripo task ID, status and provenance for paid cloud generation, including an interrupted/incomplete revision.
- `processing.json`: exact parent request and source hash. Completed manifest retains original generation provenance and adds `local_processing` or `remote_processing`.
- `local-process.json`, `local-rig.json`, `local-parts.json`, `local-motion.json`: applicable local backend/checkpoint and quality records. Local motion includes dense grounding checks; GeoSAM2 keeps source/context bindings and unclassified faces.
- `authoring-request.json`: bound request/input hashes for `blender-edit` or `merge-animations`; `input.glb`, `input.blend`, `script.py` or `animation-N.glb` are immutable snapshots as applicable.
- `authored.blend`, `authoring-executed.json`: script execution checkpoint; `authoring.json` or `animation-merge.json` records the result, retained as manifest `local_processing`.
- Tripo processing checkpoints retain free/paid stage task IDs for remote recovery.
- `animation-previews.json`: up to 8 clips × 3 sampled frame paths for output review. Compare `sampled_clips` and `total_clips`; exported clips beyond the previews are preserved, not visually reviewed.
- `part-previews.json`: up to 32 individual part PNGs for segmentation and subsequent static part review; `truncated: true` marks incomplete preview coverage.

An incomplete revision has no manifest and is excluded from the library. Jobs retain success/failure and results under `.assets/jobs/`. Inspect failure logs before retrying; a failure never replaces the previous completed revision. For Tripo, preserve the task record and use known-task resume to avoid another charge.

The runtime configuration is optional, local, and ignored by Git: `asset-system.local.json` with `blender`, `trellis`, `godot`, `models` path overrides. Environment overrides: `ASSET_AUTO_ROOT`, `ASSET_AUTO_BLENDER`, `ASSET_AUTO_TRELLIS`, `ASSET_AUTO_GODOT`, `ASSET_AUTO_MODELS`. Relative tool/model paths resolve against the runtime root.
