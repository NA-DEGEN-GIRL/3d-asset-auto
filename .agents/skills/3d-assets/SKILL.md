---
name: 3d-assets
description: Generate 3D assets with default local TRELLIS.2 or explicitly requested Tripo API, refine them in Blender, inspect renders, and export GLB across projects. Use for props, image-to-3D reconstruction and mesh edits. Project checks and a viewer are optional; pure concept images use an image skill instead.
---

# 3D assets

Use this skill's `scripts/assetctl.py` wrapper. It resolves the repository through its own real path, so it works from another game project's directory and through a personal-skill symlink. Commands return JSON. Run `python <skill-directory>/scripts/assetctl.py doctor` first to discover actual capabilities. Never claim an unavailable provider is installed or that a submission has finished.

## Choose the work

- Inspect the target project's existing assets and import conventions when a project is provided. Preserve its scale, palette, naming, triangle/texture budgets, and file locations. If the target is unknown, produce a portable GLB and editable source without choosing an engine or creating an app.
- For new asset creation, default to TRELLIS.2 (`provider: "trellis"`), then Blender for cleanup, edits, inspection and export. Use a supplied reference image; for a text-only request, use the host's available image-generation skill/tool to prepare a suitable reference before inference. The runtime's `prompt` does not generate that image. If neither a reference nor image-generation capability is available, explain the missing input and request a reference.
- Use paid `provider: "tripo"` only when the user explicitly asks to use Tripo/Tripo3D. Read the runtime's [Tripo guide](../../../docs/TRIPO.md) at `<doctor.root>/docs/TRIPO.md` for credentials, single-image/multiview inputs, cost planning and task recovery. Use that resolved root when the skill is linked from another directory. Key presence, possible quality gains, multiple images or a failed TRELLIS run do not select Tripo or authorize an automatic fallback. Keep the selected provider through the task unless the user changes it.
- Do not replace image-to-3D inference by looking at the reference and assembling Blender primitives, or by importing a newly authored procedural mesh to bypass this workflow. A Blender rendering of primitives is not evidence of inference. Verify the completed revision's provider and its actual TRELLIS generation records or Tripo remote task record; for an edit, follow its parent to the original generation.
- Use `procedural` for new geometry only when the user explicitly requests or authorizes a procedural workflow for that task, such as a blockout or dimensioned assembly. Complexity, speed or an available recipe alone is not authorization to switch. Use `import` for a supplied existing mesh, and edits for existing revisions; neither requires regenerating it with TRELLIS. If reference preparation or GPU inference is blocked, report the blocker rather than silently downgrading to procedural generation.
- Use a named-part edit for an existing asset. Read its inspection report first. Names are exact. An inferred mesh may be one object; do not pretend semantic parts exist. Existing Tripo revisions can be edited locally without another paid API task. To perform a complex geometry edit, author a Blender Python script against a copy, run it with the installed Blender in background mode, then import the resulting `.blend` through the runtime to obtain a new inspected revision.
- Multi-image TRELLIS and rigging are currently unavailable. Explicit Tripo supports 2–4 named views including front; it does not add rigging or semantic segmentation to this static pipeline. Do not run the static pipeline on a rigged asset.

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

1. Convert the request to a validated JSON spec. Use absolute paths for reference images from another project. State any material assumptions once; use existing project conventions when possible. For explicit Tripo, run the local `tripo-plan` and read-only `tripo-balance` before submission, and keep the required `tripo.max_credits` within the user's authorized budget. It guards the estimate, not the vendor's final bill. Do not print or embed the API key.
2. For long work, submit with `generate <spec.json> --async` or `edit <changes.json> --async`. Save the returned job ID, do useful independent work, then inspect `job <id>`. Do not submit the same generation twice because output is not immediate.
3. Read the completed revision's inspection report. Triangle count is a hard budget; non-manifold edges and missing UVs are contextual warnings. Do not remove intended open surfaces or disconnected accessories automatically.
4. Open actual local render images using the host image-inspection tool. For a new asset inspect all five views; for a narrow edit inspect views that show the changed part and affected silhouette, broadening when uncertain. Examine holes, material loss, reference fidelity, and requested changes. Record the views and specific observations with `review`; a numeric pass is not visual approval. If image inspection is unavailable, report visual review as incomplete rather than substituting a browser load check.
5. For a repair, use a new revision and name the observed defect. Reinspect changed geometry and rerender. Start with a limit of two local generation attempts and three local repair passes for an asset, unless the user gives another budget. A Tripo request defaults to one paid submission; further submissions require an already authorized retry budget or a new user decision. Resume a known remote task with `resume-tripo` instead of generating again. An unknown submission outcome stops for reconciliation; never repost automatically. If the result still fails, retain the best revision and explain the remaining defect rather than presenting it as approved.
6. Apply additional checks only under the context policy above. The Godot command is `godot <id> <revision>`. For an explicitly requested browser check, verify the selected revision visibly loads in the existing project or optional viewer. Loader/draw results remain separate from visual review.
7. When integration is requested, copy the selected GLB and only the needed integration files into the target project, using its conventions. Otherwise deliver the files. A standalone adapter check is not evidence that the destination project's gameplay or conventions work.

## Reporting

Report asset ID, revision, actual provider, checks passed, important defects, and a usable GLB/source location. For Tripo distinguish estimated credits from actual account/task evidence; do not promise better quality or speed without comparison. Include a viewer URL only if a viewer was requested and actually started. Preserve the `.blend` and preceding revisions. Do not collapse generated, numeric-pass, visual-pass, and engine-tested into a single unqualified "game-ready" claim. Tool/model archives, job logs and generated outputs remain local unless the user asks to publish them; explicitly selected Tripo uploads its input images to the vendor.
