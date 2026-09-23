# game-vfx design notes

[한국어](GAME_VFX_DESIGN.md) | **English**

Status: **A skill that selects authoring and playback for the project, with bounded example implementations**. A separate [game-vfx skill](../.agents/skills/game-vfx/SKILL.md), Blender ingredient builder and fire/ice/lightning [web playback module](../examples/game-vfx/effects.js) are provided. The examples' tool combination is not a default route for every effect. There is no general VFX command in `asset_auto`, maintained Mantaflow exporter/player or Houdini/EmberGen adapter.

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
- **Reusable effect configurations:** Preserve editable sources, materials, visual intent and event contracts, including simulation settings and bakes when relevant. Adapt engine-specific shaders, particles and scenes separately; do not make one example's values or code universal. Preserve resource usage terms.
- **Playback contract:** Required files, coordinates/scale/time, event positions, start/impact/cancel/retrigger/end behavior and resource ownership. Distinguish GLB models/clips from engine-specific behavior. With no engine selected, prioritize the requested output format and include suitable materials, specifications and untested integration scope.
- **Expression review:** Set acceptance criteria against the user's request and adopted references, rather than lowering them to what the starting example easily produces. Establish large-scale shape and event rhythm first, then verify that dependent responses follow their own event positions and times. Compare the complete expression at normal playback and viewing distance; particle/glow quantity or defect-free stills alone cannot approve it. Full footage on a plane cannot replace a requested freely viewed spatial main effect.

## Choose authoring and playback from the project

First inspect the actual project's engine, renderer, version, rendering path and existing effect conventions. Establish target device/resolution, camera range, interactions such as scale, direction, contact, attachment and collision, references and quality goals. Choose the tools that produce the required data separately from the final playback implementation. Blender is a preferred available local tool for relevant ingredient authoring and baking, not a mandatory step for every effect.

| Option | Suitable work | Boundary to check |
| --- | --- | --- |
| Existing Blender | Editable curves/meshes, noise/texture authoring, animation and relevant simulation bakes | Supplied helper builds noise and lightning paths; volume/physics-cache delivery needs a separately verified path |
| Procedural scripts/material tools | Fields, trajectories, ribbons, shaders and reusable settings | Check requested forms and temporal changes at the intended camera |
| Destination engine effect system | Material assembly, particles/scenes and gameplay-event integration | Check expression, lifecycle and performance for the actual version/rendering path/device |
| Additional DCC/simulation tools | A concrete authoring need not met by available tools | Verify installation, licensing, automation and output; do not add them as default dependencies |

Simulation is one way to produce a chosen expression; successful execution or physical calculation does not guarantee quality. Keep the separate local Mantaflow fireball experiment's [observed scope and unresolved issues](VFX.en.md#retained-authoring-experiments) distinct from supplied example capabilities. With no engine selected, prioritize producing the requested output format and include suitable sources, materials and specifications; do not automatically build both Godot and web versions.

Official references: [Blender automation](https://docs.blender.org/manual/en/4.5/advanced/command_line/index.html), [Godot 3D particles](https://docs.godotengine.org/en/stable/tutorials/3d/particles/index.html). The supplied Blender helper runs through Python without a separate MCP. The Three.js gallery below is an example for requested web previews.

## Criteria for an initial implementation

Choose a bounded effect category and destination, then use a small case to check the path from reference preparation through actual tool execution and export to destination playback. Do not advertise a general VFX generation skill before checking these conditions.

- Actual execution, configuration and outputs are recorded; the result is more than images or reference video.
- Meaningful size, timing or direction changes use the same configuration without rewriting the entire implementation each time.
- Adopted expression is visible in the final destination, with applicable spatial, transparency, contact, lifecycle and concurrent-use criteria reviewed.
- Reports distinguish learned generation, simulation, authored code and untested coverage.

Retain existing [VFX experiments](VFX.en.md), `examples/vfx-web/`, the rigid-body fixture and local outputs. This initial implementation covers the three representations below; it does not promise general effect generation or commercial-game quality. The skill separates essential decisions from detail loaded only when relevant.

When evaluating the skill itself, use [independent-session testing](VFX_TESTING.en.md) to execute real requests and return evidence to the authoring session. This does not require a full evaluation report for every ordinary effect request.

## Run the fire, ice and lightning examples

| Example | Actual production/playback | Behavior outside the file |
| --- | --- | --- |
| Fire | Blender periodic 3D noise → spatial vortex of broken flame lobes, upward-traveling eruption and cooling | Flame, timing, cinders and ground afterheat remain Three.js code; an authored density field, not fluid simulation or full-footage planar playback |
| Ice | Existing TRELLIS mesh/Blender rigid-body bake → staggered falls retimed for acceleration and fragment motion | Secondary shards, ice powder, cold mist and frost follow each contact's position/time in web code, alongside materials and lifecycle; large fragments replay the original flat-ground bake, not live collision |
| Lightning | Blender angular trunk/fork paths → descending leader, return strokes and ground current | Progressive path reveal, re-strikes, residual current and lighting are authored in web code; no electrical/collision simulation |

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

`createEffect(id, options)` provides `group`, `duration`, `impact`, `update(seconds)`, `setLayer(name, visible)`, `setSceneDepth(texture, width, height)` and `dispose()`. Reuse through `seed`, `scale`, `speed` and placement via `group` transforms. Do not apply speed twice through both the module and an external clock. Caller-provided textures/GLB resources remain caller-owned, so removing one instance preserves another. Follow [runtime.md](../.agents/skills/game-vfx/references/runtime.md) for actual data contracts and editing guidance.

`effects.js` dispatches effects and owns the shared playback/lifecycle contract. Expression lives in [fire.js](../examples/game-vfx/fire.js), [ice.js](../examples/game-vfx/ice.js) and [lightning.js](../examples/game-vfx/lightning.js), with resource management and shared materials in [common.js](../examples/game-vfx/common.js). Refining one effect does not require rewriting the other effects.

```sh
node examples/game-vfx/build.mjs --test
node .work/game-vfx/effects.test.cjs
```

Automated checks cover seeking, replay, valid coordinates, instance independence and resource ownership, plus individual ice contact positions/times and clip playback at those events using synthetic inputs, and lightning's leader → contact → ground-current order. They do not judge natural expression or establish parity with commercial-game quality. Browser visual review, other engines, low-end devices and performance with many simultaneous effects require separate verification.

## Installation and licensing

Link the personal `game-vfx` skill folder to this repository's `.agents/skills/game-vfx`. Resolve that link to find the shared checkout from another project; do not copy a developer-machine path. The default model-inference installation is not required to author VFX ingredients.

New [web example code](../examples/game-vfx/LICENSE.txt) is MIT; the new Blender `bpy` [helper](../.agents/skills/game-vfx/scripts/prepare_blender.py) is [GPL-3.0-or-later](../.agents/skills/game-vfx/scripts/COPYING.txt). This does not relicense the rest of the repository or external media. Blender output and published Python add-ons have different conditions: follow [Blender's official guidance](https://www.blender.org/about/license/), applicable input/service terms and preserved provenance. Distributed web builds include Three.js notices.
