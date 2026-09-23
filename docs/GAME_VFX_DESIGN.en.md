# game-vfx design notes

[한국어](GAME_VFX_DESIGN.md) | **English**

Status: **initial Blender-centered implementation**. A separate [game-vfx skill](../.agents/skills/game-vfx/SKILL.md), Blender ingredient builder and fire/ice/lightning [web playback module](../examples/game-vfx/effects.js) are provided. This does not add a general VFX command to `asset_auto`, and there are no Houdini/EmberGen adapters. Usage and boundaries are separated below.

## Problem to solve

Current VFX experiments establish that an LLM can author Blender and renderer code. They still require effects to be assembled from scratch, and image/video reference quality does not automatically transfer to the implementation. Adding review instructions to a model-generation skill or merely renaming it does not close this gap.

The goal is **a separate skill that executes effect requests through verified tools and reusable configurations, then reviews and repairs their actual game presentation**. Procedural methods are not prohibited. Simulations, shaders and templates are valid; distinguish temporary code arranging basic shapes from a verified production path.

## Responsibilities

| Owner | Role and boundary |
| --- | --- |
| `3d-assets` | Model generation, editing, rigging and mesh animation; used when an effect needs physical objects such as ice chunks or meteors |
| `game-vfx` | Effect form, timing and layers; tool execution, reusable effect configurations, destination output and review |
| Image/video tools | Expression references and usable texture materials; do not assume automatic recovery of 3D physics or game effects from footage |
| Destination game | Terrain, attachment locations, collision/damage events and playback lifecycle; distinguish visual events from gameplay decisions |

Effects without mesh requirements need no TRELLIS/Tripo installation or calls. New physical models follow the `3d-assets` generation policy; supplied models can be reused. Adding references, materials or supporting particles does not complete requested spatial motion.

## Required foundations

- **Verified production path:** Tool integration with readiness checks, actual execution, settings/seed/output/version records and failure recovery. Use MCP only when it provides the needed access; reuse working CLI or scripting paths first.
- **Reusable effect configurations:** Suitable simulation settings, shaders/materials/textures and mesh/particle/trail timing. Preserve editable sources and resource usage terms. Do not make one example's values universal.
- **Playback contract:** Required files, coordinates/scale/time, start/cancel/retrigger/end behavior and resource ownership. Distinguish GLB models/clips from engine-specific behavior. With no engine selected, deliver materials and specifications and mark integration untested.
- **Expression review:** Compare adopted events, silhouettes and speed changes against actual output. Review and repair at relevant viewpoints, backgrounds and concurrent-use conditions. Full footage on a plane cannot replace a requested freely viewed spatial main effect.

## Selected tools and unknowns

| Candidate | Purpose to investigate | Still to verify |
| --- | --- | --- |
| Existing Blender — default | 3D noise baking, editable lightning curves and reused fragment motion/bakes | Fire uses an authored spatial density shader; Mantaflow/liquids are untested |
| Houdini — deferred | Investigate destruction/fluid/particle authoring if a need is demonstrated | Additional tooling, licensing and automation are excluded from default setup |
| EmberGen — deferred | Investigate fire/smoke simulation if a need is demonstrated | Additional tooling, licensing and automation are excluded from default setup |
| Destination engine effect system | Material assembly, particles/materials and game event integration | Project-specific implementation and performance; do not always require both Godot and Three.js |

Official references: [Blender automation](https://docs.blender.org/manual/en/4.5/advanced/command_line/index.html), [Godot 3D particles](https://docs.godotengine.org/en/stable/tutorials/3d/particles/index.html). Default authoring uses existing Blender and Python without requiring a separate MCP. Three.js is the requested preview destination for this task, not a requirement for other projects.

## Criteria for an initial implementation

Choose a bounded effect category and destination, then use a small case to check the path from reference preparation through actual tool execution and export to destination playback. Do not advertise a general VFX generation skill before checking these conditions.

- Actual execution, configuration and outputs are recorded; the result is more than images or reference video.
- Meaningful size, timing or direction changes use the same configuration without rewriting the entire implementation each time.
- Adopted expression is visible in the final destination, with applicable spatial, transparency, contact, lifecycle and concurrent-use criteria reviewed.
- Reports distinguish learned generation, simulation, authored code and untested coverage.

Retain existing [VFX experiments](VFX.en.md), `examples/vfx-web/`, the rigid-body fixture and local outputs. This initial implementation covers the three representations below; it does not promise general effect generation or commercial-game quality. The skill separates essential decisions from detail loaded only when relevant.

## Run the fire, ice and lightning examples

| Example | Actual production/playback | Behavior outside the file |
| --- | --- | --- |
| Fire | Blender periodic 3D noise → spatial density raymarching and 3D embers | Flame, timing, lighting and particles remain Three.js code; neither fluid simulation nor full-footage planar playback |
| Ice | Existing TRELLIS mesh/Blender rigid-body bake → three delayed falls and fragment playback | Material adjustments, frost and lifecycle remain web code; motion is baked against the original flat ground |
| Lightning | Blender curves/path data → hierarchical 3D trunk/branches and delayed discharge | Lighting, afterglow and playback remain web code; no electrical/collision simulation |

Locate Blender, then prepare ingredients in a new output directory. Replace `<blender>` with its executable path.

```text
<blender> --background --python .agents/skills/game-vfx/scripts/prepare_blender.py -- --output .work/game-vfx/bake-r1 --seed 17
```

Outputs are `source.blend`, `noise.png`, `recipes.json`, `recipe-geometry.glb` and `provenance.json`. Existing output folders are not overwritten. `recipe-geometry.glb` contains static lightning geometry, not the three complete spells.

Prepare `noise.png`, `recipes.json`, `ice.glb`, `fire.png`, `ice.png` and `lightning.png` in a preview media folder. The three PNGs are per-effect references; `fire.mp4`, `ice.mp4` and `lightning.mp4` are optional reference videos. The ice GLB needs an `ice_fall_break` clip. This example's source has six seconds, impact at two seconds and a `1/24`-second start offset; change playback code and its contract together for a different clip. Generated media is outside Git, so a fresh clone must prepare these ingredients. Reusing only fire/lightning in another project does not require an ice GLB.

```sh
node examples/game-vfx/build.mjs --media-dir .work/game-vfx/media
uv run --no-sync python -m http.server 8776 --bind 127.0.0.1 --directory .work/game-vfx/site
```

If `web/node_modules` is missing, install only web dependencies with `npm --prefix web ci`. The [preview](http://127.0.0.1:8776/) supports three effects, seeking, cameras, speed, scale, backgrounds, overlap and supporting-layer inspection. Serve only the generated site; no account or generation API is exposed.

`createEffect(id, options)` provides `group`, `duration`, `impact`, `update(seconds)`, `setLayer(name, visible)` and `dispose()`. Reuse through `seed`, `scale`, `speed` and placement via `group` transforms. Do not apply speed twice through both the module and an external clock. Caller-provided textures/GLB resources remain caller-owned, so removing one instance preserves another. Follow [runtime.md](../.agents/skills/game-vfx/references/runtime.md) for actual data contracts and editing guidance.

```sh
node examples/game-vfx/build.mjs --test
node .work/game-vfx/effects.test.cjs
```

Automated checks cover seeking, replay, valid coordinates, instance independence and resource ownership. They do not approve visual quality, other engines, low-end devices or performance with many simultaneous effects.

## Installation and licensing

Link the personal `game-vfx` skill folder to this repository's `.agents/skills/game-vfx`. Resolve that link to find the shared checkout from another project; do not copy a developer-machine path. The default model-inference installation is not required to author VFX ingredients.

New [web example code](../examples/game-vfx/LICENSE.txt) is MIT; the new Blender `bpy` [helper](../.agents/skills/game-vfx/scripts/prepare_blender.py) is [GPL-3.0-or-later](../.agents/skills/game-vfx/scripts/COPYING.txt). This does not relicense the rest of the repository or external media. Blender output and published Python add-ons have different conditions: follow [Blender's official guidance](https://www.blender.org/about/license/), applicable input/service terms and preserved provenance. Distributed web builds include Three.js notices.
