# 3d-assets user guide

[한국어](user-guide.md) | **English**

Ask `$3d-assets help` for a short guide without starting production. Ask for `help in detail`, `just the available model choices`, or `how to use Kimodo` to focus the answer.

Generate props, buildings and characters or edit existing models, with rigging, animation and part segmentation when needed. The default delivery is **a reviewed GLB and Blender source**. Multiple motions are delivered as named clips in one GLB.

## Models and tools

| Goal | Model or tool | Selection and role |
| --- | --- | --- |
| Generate a new 3D model | **TRELLIS.2** | Default. Generates a mesh from a single reference image on a local GPU. |
| Paid 3D generation or multiview input | **Tripo / Tripo3D API** | Selected **only when you say “use Tripo.”** Requires configured credentials and credits. |
| Draft a rig | **SkinTokens** | Install when a deforming mesh needs bones and skin weights. Existing rigs or Blender authoring are also valid choices. |
| Generate human motion | **Kimodo-SOMA-RP-v1.1** | Selected **only when you say “use Kimodo.”** Generates local text-conditioned motion for an already rigged humanoid, followed by Blender refinement. |
| Edit geometry, materials, rigs or motion | **Blender** | Default local editor. Supports custom motion, clip edits/merging and task-appropriate `idle`, `walk`, `run` presets. |
| Separate semantic parts | **GeoSAM2** | Install when needed. The agent supplies names and points from inspected renders and reviews the separated result. |
| Prepare shape or motion references | Available **ImageGen**, optional **Grok Imagine video**, etc. | Images inform shape/poses; video informs sequence/timing. Generated video is not automatically converted to 3D motion. |
| Validate a project or preview on the web | **Godot / Three.js** | Use for relevant destination-project checks or requested web previews. Neither is required on every job. |

These are **supported capabilities**, not a claim that everything is installed or inference-tested on your host. Ask `Check which tools are available in this environment` for a read-only distinction between installation and verified execution.

## Defaults to remember

- New meshes follow **reference image → TRELLIS.2 → Blender → render review**. For text requests, an available image tool prepares the reference first. Blender primitives do not replace inference.
- **Choose Tripo and Kimodo explicitly and independently.** A Tripo mesh does not select Kimodo or paid Tripo processing automatically. Kimodo does not generate meshes or rig characters.
- Editing existing models does not require regeneration. Static props stay unrigged; procedural new meshes are used when you request that approach.
- Default inspection uses local renders. Add **“show it on the web”** when you want an app. Setup, inference and numerical checks are separate from actual quality approval.
- An explicit Tripo request covers one standard generation per asset. The default `max_credits: 100` is a **local estimate guard**, not a server spending cap or permission for unlimited retries. Reference images are uploaded to Tripo. See [costs, credentials and recovery](../../../../docs/TRIPO.en.md).
- GPU selection, CPU threads and parallel Blender jobs follow the execution host's **private resource policy**. Busy selected resources cause waiting, not an automatic switch to another GPU. See [resource settings](../../../../docs/RESOURCES.en.md).

## Requests you can reuse

> `$3d-assets` Make a stone house for a fantasy village. Inspect renders and deliver a GLB.

> `$3d-assets` Use Tripo to make a shield from these front and back images.

> `$3d-assets` Use Tripo to create an explorer character, rig it, then use Kimodo for a greeting. Refine it in Blender and show a web comparison.

> `$3d-assets` Edit only this character's attack. Preserve the other motions and deliver them together in one GLB.

> `$3d-assets` Briefly check available models and GPU/CPU limits on this host. Do not install or generate anything.

## More detail

Help requests are natural-language conversation, not new CLI subcommands. See [runtime.md](runtime.md) for commands, [specs.md](specs.md) for request fields and [execution-setup.md](execution-setup.md) for host setup and connections.

See [Kimodo](../../../../docs/KIMODO.en.md) for the rig/refinement workflow and [Blender](../../../../docs/BLENDER.en.md) for editing and merging. For effects such as fire or lightning, start with the separate **`$game-vfx help`**; use this skill alongside it when an effect needs a standalone 3D model.
