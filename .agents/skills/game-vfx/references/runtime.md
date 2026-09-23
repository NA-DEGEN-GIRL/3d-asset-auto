# Local authoring and web examples

## Locate the runtime

Resolve the installed skill's `SKILL.md` path through junctions/symlinks. In this repository layout, `Path(skill_md).resolve().parents[3]` is the shared runtime root containing `.agents/`, `examples/` and `web/`. Confirm that the expected helper and build file exist before running them. Do not assume the requesting project's working directory is the runtime and do not hard-code a developer drive or profile path.

The skill's helper lives at `scripts/prepare_blender.py`; web code lives at `<runtime>/examples/game-vfx/`. Both are needed for the supplied gallery workflow. A detached skill copy needs an explicit checkout location; do not silently substitute another repository or install the 3D inference stack. For an individual effect, reuse only the relevant components; creating fire does not require building ice and lightning too.

Use an existing Blender executable. In a configured shared runtime, `3d-assets`' `doctor` can identify it without invoking generation. The example builder uses dependencies installed under `<runtime>/web`; only install those web dependencies if needed. No TRELLIS, Tripo, Kimodo or paid VFX package is required to author the procedural fields and branches.

## Prepare reusable Blender ingredients

The helper runs in Blender, not ordinary Python:

```text
<blender> --background --python <absolute-skill-dir>/scripts/prepare_blender.py -- --output <absolute-new-output-dir> --seed 17
```

Use a new or empty output directory beneath local `.work/game-vfx/` or the target project's work area; the helper rejects a populated directory. `17` is an example reproducible seed, not a required artistic value. This helper accepts only `--output` and `--seed`. It resets its own background Blender scene and creates field data plus lightning geometry; adapt a separate authoring script for different behavior rather than inventing flags.

The helper produces:

| Output | Role |
| --- | --- |
| `noise.png` | 64 cubed field samples packed into a 512 by 512 image; not a frame sequence |
| `recipes.json` | Schema version 1, seed, Y-up meter coordinates, field metadata, lightning paths/roles and example fire/ice parameters |
| `source.blend` | Editable lightning curves and packed noise image; not the complete browser effect |
| `recipe-geometry.glb` | Static lightning meshes, exported without animation |
| `provenance.json` | Source, tool and generated-file provenance |

`recipes.json.noise` declares `size: 64`, `columns: 8`, `rows: 8`; RGB store coarse/medium/fine periodic noise and alpha is opaque. The image is linear data: do not apply an sRGB color conversion. Z slices increase from the image bottom, with eight tiles per row. Wrap X/Y texels within a tile and interpolate adjacent periodic Z slices instead of filtering across atlas tile boundaries. `lightning.paths` are arrays of XYZ points and `lightning.roles` aligns their `trunk`, `branch` or `ground` roles.

These outputs establish an authored Blender-to-renderer path. They do not contain Mantaflow results or infer a 3D effect from a reference image. The browser's fire shader, pulse timing and supporting particles remain renderer code. `fire.height`/`base_radius` and `ice.clip`/`source_duration`/`impact`/`start_offset` are example metadata, not evidence that the helper generated those effects. The helper's `provenance.json` records Blender version, script/output hashes, seed and explicit false inference/simulation flags. Do not invent a VFX CLI/MCP operation in `asset_auto`.

The helper itself does not require or import an ice model. The gallery's `ice.glb` must contain the existing `ice_fall_break` clip. Current playback assumes a six-second source, impact at two seconds and a `1/24` second source offset, then retimes and staggers three instances. Each instance's contact time and position drive its own chips, powder, mist and frost. Changing metadata alone does not rewrite these playback constants: adapt `createIce` in `ice.js` for another input and verify contact timing. Preserve original GLB and source hashes; record whether motion is baked or generated live. An old example's triangle count and flat-ground trajectory are not universal budgets or collision behavior. Missing gallery ice media is not a reason to run inference for an unrelated fire/lightning request.

## Build only when a preview is requested

Run from the resolved runtime root:

```sh
node examples/game-vfx/build.mjs --media-dir <absolute-prepared-media-dir>
```

The full gallery requires these media files:

| Required | Role |
| --- | --- |
| `noise.png`, `recipes.json` | Blender helper output |
| `ice.glb` | Separately supplied baked ice model/clip |
| `fire.png`, `ice.png`, `lightning.png` | Inspected per-effect reference images |

`fire.mp4`, `ice.mp4` and `lightning.mp4` are optional temporal references. These images/videos appear beside the effect for comparison; they are not played on the primary 3D geometry. Do not fabricate references or infer visual approval from their presence.

The builder copies only this allowlist to `<runtime>/.work/game-vfx/site`, writes `config.json` and includes the example/Three.js license notices. Source `.blend`, raw logs and credentials are not served. Missing required media fails the build; building without `--media-dir` creates an unavailable state, not a fallback effect. Reuse an existing valid build when only inspecting it. The all-three requirement belongs to this gallery, not to an individual effect or the skill's default delivery.

Serve only the generated site with a loopback static server, using an available port:

```text
python -m http.server <port> --bind 127.0.0.1 --directory <absolute-runtime>/.work/game-vfx/site
```

On Windows, start background helpers with a hidden window, preserve their PID, and confirm readiness before presenting a URL. Do not expose the repository root, `.secrets` or arbitrary script execution through the viewer. Inspect the actual browser console and requested controls after building. Use the available browser skill for browser operations.

## Reuse and verification

`examples/game-vfx/effects.js` exports `EFFECTS` metadata and `createEffect(id, options)`. Options are `seed`, positive `scale`/`speed`, and relevant resources: `noiseTexture` for Blender-field fire, `recipes.lightning.paths`/`roles` for Blender-path lightning, or `iceGltf` for ice. It returns `group`, `duration`, `impact`, `update(seconds)`, `setLayer("main"|"secondary", visible)`, `setSceneDepth(texture, width, height)`, `stats` and `dispose()`.

`update` uses absolute seconds; instances are hidden before/at zero and at/after their duration. `speed` scales the full timeline and `scale` scales the group. There is no general prompt, palette or arbitrary duration parameter: choose a justified speed or modify the relevant source for more substantial artistic changes. Fire/lightning can use procedural fallback data for isolated module work, but that is not evidence that Blender was run. The gallery requires the actual supplied data.

The public entry dispatches to `fire.js`, `ice.js` and `lightning.js`, with resource helpers in `common.js`. Modify the relevant component while retaining the shared contract. Fire separates the large vortex gesture, traveling eruption, turbulent breakup and cooling. Ice exposes per-contact timing/positions through `stats.events`; lightning exposes leader/contact/restrike timing while progressively revealing supplied paths. Event `time` and `cleanupEnd` use the same speed-adjusted seconds as `update`; `sourceImpact` retains source-clip seconds and positions remain effect-local. These are authored visual events, not collision or damage notifications; transform positions through the effect's `group` before connecting gameplay.

For raymarched fire, supply opaque scene depth with `setSceneDepth(texture, width, height)` when solid objects can intersect the volume. Box-surface depth testing alone does not stop samples behind an object inside that box. Render the depth texture from the same camera for the current scene, excluding effect geometry and transparent overlays, and pass drawing-buffer pixel dimensions rather than CSS dimensions. Refresh the depth each rendered frame and rebind its dimensions after resizing. The gallery does this prepass only for fire, excluding both effect instances and its transparent grid. The caller owns the depth texture/target; effect disposal does not release it. Passing `null` disables this feature, and the method has no effect on ice/lightning. This addresses opaque occlusion; it does not solve transparent-object sorting or add physical collision.

Keep seeded seeking, layer inspection and disposal behavior when adapting the module. Loading shared resources and owning per-instance materials are different lifetimes: stopping or disposing one effect must not corrupt another instance. Read the implementation before modifying its public contract.

For changes to the reusable playback module, the supplied focused check is:

```sh
node examples/game-vfx/build.mjs --test
node .work/game-vfx/effects.test.cjs
```

These checks support deterministic behavior and resource/lifecycle contracts; they do not approve the rendered result. Run the Blender helper after changing its authoring/output behavior, inspect its outputs, then review the affected effect in the actual target. A documentation-only change does not justify rebaking assets or running inference.

Deliver exact source/output locations, actual methods, checks performed and remaining limits. Report browser rendering separately from Godot or other engine integration; run only the requested or project-relevant adapter. Retain local generated media and source revisions without publishing them by default.
