---
name: 3d-assets
description: Create, revise, inspect, and export local 3D mesh assets for games and Three.js using the 3d-asset-auto runtime. Use for requested props, image-to-3D reconstruction, named-part edits, and Godot or web asset checks. Pure concept images use an image skill instead.
---

# 3D assets

Use this skill's `scripts/assetctl.py` wrapper. It resolves the repository through its own real path, so it works from another game project's directory and through a personal-skill symlink. Commands return JSON. Run `python <skill-directory>/scripts/assetctl.py doctor` first to discover actual capabilities. Never claim an unavailable provider is installed or that a submission has finished.

## Choose the work

- Inspect the target game's existing assets and import conventions when a project is provided. Preserve its scale, palette, naming, triangle/texture budgets, and file locations. Do not change unrelated project configuration.
- Use a procedural recipe for dimensioned props and modular parts. Use TRELLIS for a supplied or generated reference image. Image generation is optional: use the available image-generation skill/tool if the user wants a concept that does not yet exist. Do not assume this runtime provides text-to-image.
- Use a named-part edit for an existing asset. Read its inspection report first. Names are exact. A TRELLIS mesh may be one object; do not pretend semantic parts exist. To perform a complex geometry edit, author a Blender Python script against a copy, run it with the installed Blender in background mode, then import the resulting `.blend` through the runtime to obtain a new inspected revision.
- Multi-image TRELLIS and rigging are currently unavailable. Report that boundary accurately; do not run the static pipeline on a rigged asset.

Read [runtime.md](references/runtime.md) for commands and artifact paths; read [specs.md](references/specs.md) when constructing a generation or edit request. These are the actual implemented interfaces, not illustrative tool names.

## Produce and verify

1. Convert the request to a validated JSON spec. Use absolute paths for reference images from another project. State any material assumptions once; use existing project conventions when possible.
2. For long work, submit with `generate <spec.json> --async` or `edit <changes.json> --async`. Save the returned job ID, do useful independent work, then inspect `job <id>`. Do not submit the same generation twice because output is not immediate.
3. Read the completed revision's inspection report. Triangle count is a hard budget; non-manifold edges and missing UVs are contextual warnings. Do not remove intended open surfaces or disconnected accessories automatically.
4. Open actual front/back/left/right/perspective render images using the host image-inspection tool. Examine silhouette, unexpected holes, material loss, reference fidelity, and requested changes. Record specific observations with `review`; a numeric pass is not visual approval.
5. For a repair, use a new revision and name the observed defect. Reinspect changed geometry and rerender. Start with a limit of two generation attempts and three repair passes for an asset, unless the user gives another budget. If the result still fails, retain the best revision and explain the remaining defect rather than presenting it as approved.
6. If Godot validation is requested, run `godot <id> <revision>`. If Three.js validation is requested, open the local viewer, select the revision, and verify its visible loaded model and status. Test relevant controls. The viewer records loader/draw results; visual review remains separate.
7. Copy only the selected validated GLB (and any engine-specific integration files actually needed) into the authorized game project. Check it with that project's real loader/import path where available. The standalone Godot check is not evidence that gameplay or project-specific conventions work.

## Reporting

Report asset ID, revision, actual checks passed, important defects, and a usable GLB or local viewer location. Preserve the `.blend` and preceding revisions. Do not collapse generated, numeric-pass, visual-pass, and engine-tested into a single unqualified "game-ready" claim. Tool/model archives, references, job logs and generated outputs remain local unless the user asks to publish them.
