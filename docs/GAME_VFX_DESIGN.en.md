# game-vfx design notes

[한국어](GAME_VFX_DESIGN.md) | **English**

Status: redesign proposal. There is no installable `game-vfx` skill, dedicated VFX generation command or automation adapter for the candidate tools below. This document does not decide implementation, purchases or installation.

## Problem to solve

Current VFX experiments establish that an LLM can author Blender and renderer code. They still require effects to be assembled from scratch, and image/video reference quality does not automatically transfer to the implementation. Adding review instructions to a model-generation skill or merely renaming it does not close this gap.

The goal is **a separate skill that executes effect requests through verified tools and reusable configurations, then reviews and repairs their actual game presentation**. Procedural methods are not prohibited. Simulations, shaders and templates are valid; distinguish temporary code arranging basic shapes from a verified production path.

## Responsibilities

| Owner | Role and boundary |
| --- | --- |
| `3d-assets` | Model generation, editing, rigging and mesh animation; used when an effect needs physical objects such as ice chunks or meteors |
| Proposed `game-vfx` | Effect form, timing and layers; tool execution, reusable effect configurations, destination output and review |
| Image/video tools | Expression references and usable texture materials; do not assume automatic recovery of 3D physics or game effects from footage |
| Destination game | Terrain, attachment locations, collision/damage events and playback lifecycle; distinguish visual events from gameplay decisions |

Effects without mesh requirements need no TRELLIS/Tripo installation or calls. New physical models follow the `3d-assets` generation policy; supplied models can be reused. Adding references, materials or supporting particles does not complete requested spatial motion.

## Required foundations

- **Verified production path:** Tool integration with readiness checks, actual execution, settings/seed/output/version records and failure recovery. Use MCP only when it provides the needed access; reuse working CLI or scripting paths first.
- **Reusable effect configurations:** Suitable simulation settings, shaders/materials/textures and mesh/particle/trail timing. Preserve editable sources and resource usage terms. Do not make one example's values universal.
- **Playback contract:** Required files, coordinates/scale/time, start/cancel/retrigger/end behavior and resource ownership. Distinguish GLB models/clips from engine-specific behavior. With no engine selected, deliver materials and specifications and mark integration untested.
- **Expression review:** Compare adopted events, silhouettes and speed changes against actual output. Review and repair at relevant viewpoints, backgrounds and concurrent-use conditions. Full footage on a plane cannot replace a requested freely viewed spatial main effect.

## Candidate tools and unknowns

| Candidate | Purpose to investigate | Still to verify |
| --- | --- | --- |
| Existing Blender | Reuse mesh editing, rigid-fragment motion and baking; investigate other simulations when needed | Existing fragment checks do not prove fire/fluid quality or reusable VFX automation |
| Houdini | Destruction, fluid and particle authoring with game-oriented exports | Local execution/licensing, LLM control and playback in the chosen destination |
| EmberGen | Fire, smoke and explosion simulation with texture/volume outputs | Local execution/licensing, available automation and required spatial presentation in the destination |
| Destination engine effect system | Material assembly, particles/materials and game event integration | Project-specific implementation and performance; do not always require both Godot and Three.js |

Official capability references: [Houdini Realtime FX](https://www.sidefx.com/products/houdini/vfx/realtime-fx/), [EmberGen documentation](https://docs.jangafx.com/embergen/), [Godot 3D particles](https://docs.godotengine.org/en/stable/tutorials/3d/particles/index.html). Product features and verified integration in this repository are separate. No default tool is selected; this proposal alone does not initiate additional spending, downloads or account connections.

## Criteria for an initial implementation

Choose a bounded effect category and destination, then use a small case to check the path from reference preparation through actual tool execution and export to destination playback. Do not advertise a general VFX generation skill before checking these conditions.

- Actual execution, configuration and outputs are recorded; the result is more than images or reference video.
- Meaningful size, timing or direction changes use the same configuration without rewriting the entire implementation each time.
- Adopted expression is visible in the final destination, with applicable spatial, transparency, contact, lifecycle and concurrent-use criteria reviewed.
- Reports distinguish learned generation, simulation, authored code and untested coverage.

Retain the existing [VFX experiments](VFX.en.md), `examples/vfx-web/`, rigid-body fixture and local outputs as reuse candidates. Working examples do not establish a completed separate `game-vfx` implementation or commercial-game quality. The intended skill will briefly route through verified production paths, loading detailed tool/output guidance only when needed.
