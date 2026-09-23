---
name: game-vfx
description: Create and refine game spell and impact effects with Blender authoring, reusable spatial effects and target-renderer playback. Use for fire, ice, lightning, trails and related VFX; request 3d-assets only when a separate physical model is needed.
---

# Game VFX

Use Blender as the default local authoring tool and adapt reusable effect components to the requested expression. Procedural geometry, noise, trajectories, simulations and shaders are valid VFX techniques. Choose a representation that survives the intended camera and game conditions; an attractive reference video is not a playable effect.

This skill depends on the shared repository's Blender helper and `examples/game-vfx/` runtime. Resolve this `SKILL.md` through any installation junction/symlink to locate that repository; the active project directory may be somewhere else. Read [runtime.md](references/runtime.md) before executing the supplied examples. Copying this Markdown folder without its runtime is not a complete installation.

## Choose and make the effect

- Identify the effect's purpose, target renderer when known, camera range, scale, timeline and contact events. Define a few observable technical and expressive acceptance criteria for each requested effect. Reuse project conventions; do not choose an engine or open a viewer for an unspecified target.
- For unfamiliar, complex or creative effects, inspect image and temporal references during design. Available ImageGen and authorized Grok video can help establish form and movement; reuse sufficient existing material. Read [workflow.md](references/workflow.md) for reference selection, construction and per-effect review. References guide implementation; they do not automatically supply geometry, physics or temporal consistency.
- Start with a suitable reusable component, then change its shape, timing, motion and material as needed. The examples cover authored spatial fire, baked ice fragmentation and branching lightning. They are starting points, not universal recipes or evidence of a fluid solver. Installing a paid DCC or inventing a new MCP is not the default next step.
- Request `3d-assets` for a separate physical asset when useful, such as a distinctive meteor or ice chunk; reuse supplied or existing meshes first. Its mesh-generation rules apply to that delegated work, not to VFX ribbons, fields, particles or branches. TRELLIS is unnecessary for mesh-free effects; Tripo and Kimodo still require explicit selection.
- Preserve editable source, inputs, seed, timing and resource provenance. Keep new outputs in separate local work/revision folders and retain completed sources. Image/video generation and additional paid work stay within existing authorization.

## Review and deliver

Judge each requested effect independently in its actual playback representation. Compare adopted expression at corresponding events, inspect the same revealing moments from complementary angles, and check transitions at intended speed. Include relevant occlusion, background, contact, repeat/restart and simultaneous-use conditions. A flat animation can support particles or a deliberately fixed view; it cannot silently replace a requested spatial primary effect.

Record a visible defect and its failed criterion, repair the responsible source or runtime component, then recheck under the same conditions. Check that fixes retain the intended motion, scale and rhythm. Numerical tests, rendered image counts and a "prototype" label do not clear a known visual defect. Scale work to all requested effects; report unresolved items and untested conditions separately when a real budget or blocker prevents completion.

Deliver the editable source and required runtime resources, with coordinates, timing, playback controls and integration limits, respecting an explicit output-format request. For GLB-only delivery, choose supported mesh/material/animation representations before authoring; do not silently add a runtime dependency or export only an effect's static proxy. Read [format choices](references/workflow.md#delivery-format-constraints) when the requested look depends on unsupported shaders or simulation. Distinguish authored motion, baked simulation and live game collision. A working browser preview does not prove performance or compatibility in another engine.

Use license-compatible tools and inspect the terms of external materials independently; keep source/attribution with reused resources. The [workflow's licensing guidance](references/workflow.md#licensing-and-provenance) separates tool code, generated data and external content. Keep models, references, raw logs and credentials local unless publication was requested. Build and launch the example web app only when requested, serving the generated site rather than the repository root.
