---
name: 3d-assets
description: Generate local 3D assets with TRELLIS.2, refine them in Blender, visually inspect renders, and export GLB for use across projects. Use for props, image-to-3D reconstruction and mesh edits. Project checks and an interactive viewer are optional; pure concept images use an image skill instead.
---

# 3D assets

Use this skill's `scripts/assetctl.py` wrapper. It resolves the repository through its own real path, so it works from another game project's directory and through a personal-skill symlink. Commands return JSON. Run `python <skill-directory>/scripts/assetctl.py doctor` first to discover actual capabilities. Never claim an unavailable provider is installed or that a submission has finished.

## Choose the work

- Inspect the target project's existing assets and import conventions when a project is provided. Preserve its scale, palette, naming, triangle/texture budgets, and file locations. If the target is unknown, produce a portable GLB and editable source without choosing an engine or creating an app.
- For new asset creation, use TRELLIS.2 (`provider: "trellis"`), then Blender for cleanup, edits, inspection and export. Use a supplied reference image; for a text-only request, use the host's available image-generation skill/tool to prepare a suitable reference before submitting TRELLIS. The runtime's `prompt` does not generate that image. If neither a reference nor image-generation capability is available, explain the missing input and request a reference.
- Do not replace image-to-3D inference by looking at the reference and assembling Blender primitives, or by importing a newly authored procedural mesh to bypass this workflow. A Blender rendering of primitives is not evidence of TRELLIS inference. Verify the completed revision's provider and actual TRELLIS generation records; for an edit, follow its parent to the original generation.
- Use `procedural` for new geometry only when the user explicitly requests or authorizes a procedural workflow for that task, such as a blockout or dimensioned assembly. Complexity, speed or an available recipe alone is not authorization to switch. Use `import` for a supplied existing mesh, and edits for existing revisions; neither requires regenerating it with TRELLIS. If reference preparation or GPU inference is blocked, report the blocker rather than silently downgrading to procedural generation.
- Use a named-part edit for an existing asset. Read its inspection report first. Names are exact. A TRELLIS mesh may be one object; do not pretend semantic parts exist. To perform a complex geometry edit, author a Blender Python script against a copy, run it with the installed Blender in background mode, then import the resulting `.blend` through the runtime to obtain a new inspected revision.
- Multi-image TRELLIS and rigging are currently unavailable. Report that boundary accurately; do not run the static pipeline on a rigged asset.

Read [runtime.md](references/runtime.md) for commands and artifact paths; read [specs.md](references/specs.md) when constructing a generation or edit request. These are the actual implemented interfaces, not illustrative tool names.

## Choose only relevant checks

The default flow is reference image → TRELLIS.2 → Blender processing → numeric inspection and agent review of local PNG renders → GLB delivery or integration. Blender provides renders without a browser. Installed Godot, Node.js or viewer files are not a reason to run them.

| Context | Additional action |
| --- | --- |
| Standalone model or unknown target | Deliver GLB/source and review findings. No engine or viewer setup. |
| Existing project | Use its actual importer/loader when an integration change or compatibility uncertainty warrants it. Infer the engine from that project. |
| Godot import check requested or relevant to that project's integration | Run the Godot adapter if useful; do not also run Three.js automatically. |
| User asks for interactive preview, a viewer/web app, or a browser rendering check | Use the existing viewer/app where suitable. Build or start a web interface only for that request. |

Do not create a separate test app for every asset, require the user to inspect models that you can review through images, or rerun unrelated engine checks after each small edit. Optional checks not run are untested, not an asset failure. Repository CI and developer smoke tests are maintenance checks, not per-asset requirements.

## Produce and verify

1. Convert the request to a validated JSON spec. Use absolute paths for reference images from another project. State any material assumptions once; use existing project conventions when possible.
2. For long work, submit with `generate <spec.json> --async` or `edit <changes.json> --async`. Save the returned job ID, do useful independent work, then inspect `job <id>`. Do not submit the same generation twice because output is not immediate.
3. Read the completed revision's inspection report. Triangle count is a hard budget; non-manifold edges and missing UVs are contextual warnings. Do not remove intended open surfaces or disconnected accessories automatically.
4. Open actual local render images using the host image-inspection tool. For a new asset inspect all five views; for a narrow edit inspect views that show the changed part and affected silhouette, broadening when uncertain. Examine holes, material loss, reference fidelity, and requested changes. Record the views and specific observations with `review`; a numeric pass is not visual approval. If image inspection is unavailable, report visual review as incomplete rather than substituting a browser load check.
5. For a repair, use a new revision and name the observed defect. Reinspect changed geometry and rerender. Start with a limit of two generation attempts and three repair passes for an asset, unless the user gives another budget. If the result still fails, retain the best revision and explain the remaining defect rather than presenting it as approved.
6. Apply additional checks only under the context policy above. The Godot command is `godot <id> <revision>`. For an explicitly requested browser check, verify the selected revision visibly loads in the existing project or optional viewer. Loader/draw results remain separate from visual review.
7. When integration is requested, copy the selected GLB and only the needed integration files into the target project, using its conventions. Otherwise deliver the files. A standalone adapter check is not evidence that the destination project's gameplay or conventions work.

## Reporting

Report asset ID, revision, actual checks passed, important defects, and a usable GLB/source location. Include a viewer URL only if a viewer was requested and actually started. Preserve the `.blend` and preceding revisions. Do not collapse generated, numeric-pass, visual-pass, and engine-tested into a single unqualified "game-ready" claim. Tool/model archives, references, job logs and generated outputs remain local unless the user asks to publish them.
