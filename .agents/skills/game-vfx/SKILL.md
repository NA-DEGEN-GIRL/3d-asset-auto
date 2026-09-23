---
name: game-vfx
description: Create and refine game spell and impact effects for the target project's renderer, using suitable shaders, particles, meshes and optional Blender baking. Use for fire, ice, lightning, trails and related VFX; request 3d-assets when a separate physical model is needed.
---

# Game VFX

Start from the target project's renderer and requested expression. Reuse its working effect system where suitable; choose ingredients and playback together. Blender is the preferred available local tool for ingredients or offline baking when needed, not a mandatory first step for every effect. Procedural geometry, fields, particles, simulations and shaders are valid techniques; neither a solver nor a generated reference guarantees a finished effect.

The supplied gallery depends on the shared repository's Blender helper and `examples/game-vfx/` runtime. Resolve this `SKILL.md` through any installation junction/symlink to locate that repository; the active project may be elsewhere. Read [runtime.md](references/runtime.md) before using those examples. A detached copy does not include that runtime; an existing project's own playback need not adopt it.

## Choose and make the effect

- Inspect the project's renderer/backend, release platform, camera, interaction and requested output where available. Set observable technical and expressive acceptance criteria against the adopted references and requested finish; do not lower them to the starting component's quality. If the target is unknown, preserve portable ingredients and intent or honor the requested format; do not choose an engine, build both web and Godot, or open a viewer by default.
- For unfamiliar, complex or creative effects, inspect image and temporal references during design. Available ImageGen and authorized Grok video can help establish form and movement; reuse sufficient existing material. Read [workflow.md](references/workflow.md) for reference selection, construction and per-effect review. References guide implementation; they do not automatically supply geometry, physics or temporal consistency.
- Adapt a suitable component's shape, timing, motion and material, or change the production path if it cannot meet the target. Read [production choices](references/workflow.md#choose-the-production-path), including optional simulation. The supplied fire, ice and lightning examples are starting components, not the quality ceiling or a general fluid-cache exporter. New libraries, models or MCPs need a demonstrated benefit in the task; tool availability is not quality evidence.
- Request `3d-assets` for a separate physical asset when useful, such as a distinctive meteor or ice chunk; reuse supplied or existing meshes first. Its mesh-generation rules apply to that delegated work, not to VFX ribbons, fields, particles or branches. TRELLIS is unnecessary for mesh-free effects; Tripo and Kimodo still require explicit selection.
- Preserve editable source, inputs, seed, timing and resource provenance. Keep new outputs in separate local work/revision folders and retain completed sources. Image/video generation and additional paid work stay within existing authorization.

## Review and deliver

Judge each requested effect independently in its actual playback representation. Compare adopted expression at corresponding events, inspect the same revealing moments from complementary angles, and check transitions at intended speed. Include relevant occlusion, background, contact, repeat/restart and simultaneous-use conditions. A flat animation can support particles or a deliberately fixed view; it cannot silently replace a requested spatial primary effect.

Record a visible defect and its failed criterion, repair the responsible source or runtime component, then recheck under the same conditions. Check that fixes retain the intended motion, scale and rhythm. Numerical tests, rendered image counts and a "prototype" label do not clear a known visual defect. Scale work to all requested effects; report unresolved items and untested conditions separately when a real budget or blocker prevents completion.

Deliver editable source and required resources, with coordinates, event timing, playback controls and integration limits. Preserve reusable ingredients and intent across engines; materials and particle systems need target-specific implementation and review. Honor explicit formats using [format choices](references/workflow.md#delivery-format-constraints). Distinguish authored motion, baked simulation and live collision. Assess [runtime cost](references/workflow.md#runtime-cost-and-target-checks) separately from visual quality; a working browser preview proves neither production performance nor another engine's compatibility.

Use license-compatible tools and inspect the terms of external materials independently; keep source/attribution with reused resources. The [workflow's licensing guidance](references/workflow.md#licensing-and-provenance) separates tool code, generated data and external content. Keep models, references, raw logs and credentials local unless publication was requested. Build and launch the example web app only when requested, serving the generated site rather than the repository root.

When evaluating or improving this skill, use the [independent-session test guide](../../../docs/VFX_TESTING.en.md). This is a maintenance workflow, not a requirement to launch another session for ordinary effect requests.
