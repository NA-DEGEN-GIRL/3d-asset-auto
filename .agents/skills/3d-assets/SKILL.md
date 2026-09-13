---
name: 3d-assets
description: Create 3D assets with TRELLIS.2, refine in Blender, and inspect GLB outputs. Use for mesh edits, local learned rigging and part segmentation, and local animation; Tripo is an explicitly requested paid option. Engine checks and a viewer are optional.
---

# 3D assets

Use `scripts/assetctl.py` through this skill's resolved path; its wrapper locates the shared runtime even from another project. Run `doctor` to discover actual capabilities. Read [runtime.md](references/runtime.md) for commands and [specs.md](references/specs.md) when constructing requests. A submitted job or installed file is not evidence of successful inference.

## Choose the workflow

- Match the target project's existing scale, naming, materials and budgets. With no target, deliver portable GLB/source files without choosing an engine or creating an app.
- New meshes default to TRELLIS.2. Use a supplied reference or an available image-generation tool to prepare one; `prompt` is provenance, not text-to-image. Do not reconstruct the reference with Blender primitives or import a newly authored procedural mesh to bypass inference. New procedural geometry requires the user's explicit request. Existing supplied meshes can be imported and edited without regeneration.
- Rigging, animation and semantic part segmentation default to `provider: "local"` through `process`. Read [CHARACTERS.md](../../../docs/CHARACTERS.md) at `<doctor.root>/docs/CHARACTERS.md` only when these operations are needed. Install their isolated backends on demand. A simple prop does not require every postprocessing model or operation.
- Local rigging uses learned SkinTokens skeleton/weight prediction; local segmentation uses learned GeoSAM2 masks from points on observed renders. Do not substitute bounding-box bones or disconnected-component splitting and call it learned/semantic output. Local idle/walk/run are procedural Blender IK motions on actual bones, not captured or learned motion.
- For segmentation, run `prepare-segment`, inspect its actual views, and author named positive/negative pixel points yourself. Do not turn this into an end-user annotation task. Preserve `unclassified` faces and inspect individual result parts. For unknown bone names, inspect joint positions/hierarchy and supply an observed `bone_map`; never infer anatomy from bone numbers alone.
- Choose Tripo only when the user explicitly asks for it. Read [TRIPO.md](../../../docs/TRIPO.md) at `<doctor.root>/docs/TRIPO.md` for paid input, cost and recovery rules. Key presence, missing local models or a failed inference never authorize switching to Tripo. Requested standard work proceeds without repeated credit approval; the optional estimate guard defaults to 100 and a smaller user limit wins.
- Static named edits use actual object names. Import supplied rigs with `provider: "import", asset_kind: "character"` so bones, weights and clips survive. Static import/edit reject rigged inputs; edit the preserved static parent then rig a new revision. Arbitrary local rig/weight editing is outside this adapter.

## Execute and review

1. Prepare a validated spec, using absolute external file paths. Preserve source revisions. For long work use `generate`, `process`, `prepare-segment` or `edit` with `--async`; save the job ID and query `job`. Do not duplicate submissions while waiting.
2. For processing, use `process-plan` to check the exact source and required backend. For explicit Tripo, run the relevant plan and read-only balance internally, then continue within the requested scope. Do not expose keys or request another approval for the same authorized work.
3. Inspect numeric output and provenance. Keep the original mesh generator separate from `local_processing` or `remote_processing`; an imported/rendered file is not inference evidence. Character processing reports budget excess without automatically decimating its skin. Interpret open boundaries and UV warnings in context.
4. Open actual local PNGs. For a new result inspect all five views; for a narrow edit start with affected views. For segmentation inspect the part previews; for animation inspect sampled motion frames and dense ground-check reports. Record specific findings with `review`. Numeric or loader success is not visual approval.
5. Preview coverage is bounded: at most 8 clips × 3 frames and 32 individual parts. Read clip counts and the part `truncated` flag. Unseen clips/parts remain unreviewed, and three frames do not prove whole-motion quality.
6. Repair observed defects in a new revision and reinspect. Start with two local inference attempts and three repair passes unless the user gives another budget. Preserve the best result and report defects when the budget ends. Use `resume-process` for saved processing; local compute may restart if no reusable output exists. Tripo's unknown submission outcomes require reconciliation, never automatic POST retry or extra paid variants.

## Choose only relevant integration checks

Blender renders support agent review without a browser. For standalone assets, deliver files and findings. For project integration, use that project's importer when compatibility needs checking. Godot is one optional adapter; it does not imply running Three.js too. Build/start a viewer only when an interactive preview or web rendering check was requested. The current viewer's static draw does not validate motion. Unperformed optional checks are untested, not generation failures.

## Report

Give the asset/revision, actual generation and processing backends, checks performed, material defects and usable GLB/source paths. Distinguish local readiness, model inference, numeric checks, visual review and engine tests. Mention a viewer URL only if requested and running. Keep models, references, logs and outputs local unless publication was requested; explicitly selected Tripo sends its input to that service.
