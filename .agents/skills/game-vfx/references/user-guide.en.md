# game-vfx user guide

[한국어](user-guide.md) | **English**

Ask `$game-vfx help` for a short guide to capabilities, tool choices and example requests. A help-only request does not start installation, generation, baking, a web preview or paid calls. If you also request production work, the explanation is followed by that work.

## What can it do?

Create or edit game effects such as fire, ice, lightning, shockwaves, trails and auras. It designs shape, motion, color/material and activation, impact and decay timing, then combines shaders, particles, meshes and animation **for the actual project's renderer**. It preserves the required sources and playback code and reviews each effect's important moments and transitions from complementary angles.

This is not a single dedicated AI VFX model that automatically produces complete effects. The supplied fire, ice and lightning examples are reusable starting points, not a guarantee of universal coverage or commercial-game quality. Actual terrain collision, damage and gameplay-event connections require separate implementation and verification in the destination project.

## Which tools and models are used?

| Tool or path | Role and selection |
| --- | --- |
| Destination shaders, particles and mesh systems | The default playback path. Authoring follows the existing effect system, renderer/version, device, camera and interactions. An unspecified engine is not chosen automatically. |
| Blender | A preferred local tool for needed curves, meshes, noise ingredients, object animation, rigid-body motion and baking. It is not a mandatory step for every effect. |
| Supplied Blender helper + Three.js examples | The helper creates 3D noise and lightning paths. Fire uses a spatial field shader, ice replays an existing fracture clip, and lightning combines paths with discharge timing. The three complete effects are not stored in one GLB. |
| Blender Mantaflow — optional when useful | Can provide gas/fire/smoke or liquid simulation ingredients. Conversion to the target playback representation requires work; the supplied helper has no general fluid-cache exporter/player. Not every fireball needs simulation. |
| ImageGen / authorized Grok video | Supports references for shape, color, material and timing, or reviewed texture ingredients. Images/video do not automatically reconstruct 3D fluids, collisions, trajectories or game effects. Selection depends on available tools and the task's authorization. |
| Separate `3d-assets` skill | Used when a standalone model such as an ice chunk or meteor is needed. Existing meshes can be reused; new models default to reference image → **TRELLIS.2**. **Tripo is a paid option requiring explicit user selection**. Effects without model requirements need no such inference. |

Procedural fields, ribbons, particles and lightning branches are normal VFX authoring techniques, distinct from `3d-assets` policy for generating standalone models. Kimodo for human motion is not a default VFX tool and requires explicit selection. Houdini, EmberGen and similar tools are not default dependencies or supplied automated adapters.

## How should I request work?

When known, include **the desired appearance and behavior, destination project, duration/size, camera range and required files**. Unknown details can be omitted. Point to existing files or image/video references when available.

| Goal | Example request |
| --- | --- |
| Recall capabilities and tools | `$game-vfx help. Briefly explain the default tools and optional paths.` |
| Check current installation | `$game-vfx check which tools are available in this execution environment using read-only inspection. Do not install or generate anything.` |
| Create for an existing game | `$game-vfx create a one-second blue lightning strike in this Godot project. Its branches and impact timing must read clearly from the game camera.` |
| Specify output format | `$game-vfx deliver a three-second blue fire pillar only as GLB. It will be viewed from several angles.` |
| Reuse an existing model | `$game-vfx use this meteor GLB for a falling impact effect and integrate it into the current project.` |
| Select a production method | `$game-vfx bake a smoke explosion with Mantaflow and convert it for playback in this project.` |
| Combine explanation and work | `$game-vfx briefly explain your tool choices, then improve the readability of this project's sword trail.` |
| Request a web preview | `$game-vfx also open a web preview where I can rotate and play the completed effect.` |

## Deliverables and verification

- **Default delivery:** The requested format and required playback resources, editable source, size/coordinate/time/event notes and actual review coverage. The requested files take priority even without a selected engine; a web preview is built only when requested.
- **GLB boundaries:** It can carry meshes and supported materials/animation, but engine shaders, particle systems and Blender fluid caches are not automatically embedded. GLB-only requests are designed around representations that the format can carry.
- **Installation versus verification:** This guide describes supported paths, not proof that everything is installed on the current machine. An explicit availability request can use read-only `doctor` and relevant resource-plan inspection. Detected files, successful execution, visual quality and destination-game performance are reported separately. Credentials and private device identifiers are not disclosed.
- **Sources and licensing:** Check the terms for external models, textures, footage, code and service outputs individually and preserve provenance. A free or installed tool does not establish redistribution rights for every output.

Read more: [authoring and review](workflow.md), [supplied example runtime contract](runtime.md), [design and execution](../../../../docs/GAME_VFX_DESIGN.en.md), [VFX authoring and experiments](../../../../docs/VFX.en.md), [separate 3D asset skill](../../3d-assets/SKILL.md).
