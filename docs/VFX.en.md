# Game effects and VFX

[한국어](VFX.md) | **English**

The skill can **author and review game effects for the destination renderer**, separately from mesh assets. Current starting points are a [Three.js shockwave](../examples/vfx-web/effect.js) and an [image/video-based flame flipbook](../examples/vfx-web/soul-effect.js). A universal VFX generation model, video-to-3D-particle extraction and automatic conversion of Blender effects to every engine are not implemented.

## Choose the representation first

Define the purpose, destination project/renderer, camera distance, origin/direction/scale, and the relationship between anticipation, release, dissipation and gameplay events. A short impact, persistent aura and moving projectile need different criteria. If the engine is unknown, prepare suitable portable ingredients such as textures, meshes and timing notes; do not add a web app or choose an engine without a preview request.

| Expression needed | Authoring and delivery |
| --- | --- |
| Moving debris/objects or deforming effect meshes | Blender object/morph/rig animation and GLB; verify playback in the destination |
| Repeated sparks, smoke or explosion particles | Destination particle/sprite system with emission, lifetime, randomization and materials |
| Shockwave, slash trail, magic circle or distortion | Shaders, ribbons/trails or carrier surfaces with material, timing and orientation settings |
| Complex surface changes such as painted flames or smoke | Reviewed textures/flipbooks from generated imagery, simulation or hand-authored images as appropriate |

A VFX request includes authoring its rendering points, quads, rings, ribbons and shaders. Do not force TRELLIS or a rig onto these rendering carriers. **New physical weapons, buildings or ornamental models needed alongside the effect still follow the default TRELLIS policy.** Explicit-selection requirements for Tripo and Kimodo remain unchanged.

GLB can carry reusable meshes and supported animation. Do not assume it preserves arbitrary shaders, emitters, screen distortion, postprocessing or gameplay logic. Deliver native effects with code/shaders/textures and settings. Implement and test engine-specific behavior separately; do not require both Godot and Three.js for every effect.

## Effects defined by texture and flow

Do not substitute recolored default particles or geometric shapes for fire, water, ice or spirits when form, surface and temporal change determine quality. Reuse sufficient existing material or **prepare relevant image and temporal references during initial design**. Define adopted silhouette, texture, flow direction, release speed and aftermath as appropriate. Do not require new image/video generation for every intentionally geometric effect or simple range indicator.

- **Images:** Use ImageGen or available tools to design the expression or create production textures. Distinguish reference artwork from runtime textures; inspect transparency, padding, edges and repeatability before using the latter. Wobbling a single fire image does not reproduce newly forming and splitting flame tongues.
- **Video:** Adopt onset, peak expression, disappearance and intervening flow from Grok or other references. Follow [Grok operation/recovery guidance](MOTION_REFERENCES.en.md#grok-build-headless-use). Stable camera, scale and background with useful shape changes can make footage a candidate for baking actual frames into a flipbook. A generated multi-panel image is not automatically a temporally coherent frame sequence.
- **Implementation choice:** Flipbooks can suit flames or smoke under limited viewing conditions. Free-view volume, water refraction/intersections, spatial trails or collisions may need Blender simulation/meshes or destination depth, normal, particle and shader features. Do not assume video automatically reconstructs 3D flow, depth or normals.
- **Compositing:** Select relevant primary shapes, detail particles, trails, grounding and aftermath. Coordinate their onsets/lifetimes and preserve the main effect's readability rather than simply adding layers. Camera shake, light, sound and damage are separate integration elements; add them only when relevant to the request and destination.

Preserve and verify flipbook frame order, FPS, source timestamps, grid layout, texel borders, alpha/color space and memory cost. Wrapping to the first frame does not establish a seamless loop. Brightness-based compositing of luminous footage on black is **an approximation used by this sample**, not a general solution for water, opaque smoke or black materials. Use a separate alpha/mask or another production method when needed.

For commercial ARPG-level goals, a particular game's tool choices do not guarantee quality. Compare reference and final effect at corresponding shape/timing/intensity events, then iterate under actual combat backgrounds, concurrency and budgets. **Do not report the quality of a generated reference as the quality of the implementation.**

## Design, author and review

1. **Define observable targets.** Choose relevant criteria such as readable onset, intended maximum extent/direction, impact/release timing and a clean ending. Track multiple effects individually. For difficult or creative effects, inspect [image and temporal references](MOTION_REFERENCES.en.md) during initial design. Generated video is an expression reference, not an alpha-ready texture or actual particle data.
2. **Author layers and timing.** Record anticipation, key events and aftermath in seconds. Separate gameplay and visual events; a visual effect does not establish collision or damage behavior. Define looping/one-shot use, local/world space, attachment/travel, cancellation and restart. Retain adopted scale, silhouette and speed changes instead of shrinking expression to conceal defects.
3. **Play in the actual destination.** Review matching important states and transitions at the intended scale/camera and revealing alternative angles, on light and dark backgrounds. Inspect rectangular alpha borders, sorting, intersections, depth occlusion, flipbook seams, unintended flicker and abrupt disappearance. A thin ground effect becoming narrow from the side is a representation property; do not require identical silhouettes from every angle.
4. **Check lifecycle and cost.** Exercise repeated activation, cancellation, reverse seeking when supported, concurrent instances, cleanup and bounds. Measure relevant particle counts, overlapping transparent area and draw calls/frame costs on the target device/resolution. A small example's draw count does not establish mobile or large-battle performance.
5. **Repair and review under matching conditions.** Follow [quality principles](QUALITY.en.md): record defects, times, views, changes and remaining issues. Judge numerical checks, actual visual review and gameplay integration separately. Shader compilation or an HTTP success does not approve an effect. Paid references/generation must remain within existing authorization.

Deliver source and dependency versions, entrypoint, coordinates/scale, playback/termination contract, event timing, randomization policy, target and review coverage. Do not hand off a scene that cannot run or textures of unknown provenance. Generated results and review captures remain local by default.

## Small Three.js web test

Run from the repository root. Skip `npm ci` if web dependencies are already installed. No model downloads, Blender, Godot or paid APIs are required.

```sh
npm --prefix web ci
node examples/vfx-web/build.mjs
uv run --no-sync python -m http.server 8775 --bind 127.0.0.1 --directory .work/vfx-web/site
```

Open the [local preview](http://127.0.0.1:8775/). Keep the server terminal running and press Ctrl+C to stop it. This is separate from the GLB library viewer and serves only the static files in that directory. Choose another available port if needed.

The example is a **2.4-second arcane shockwave**: charge, release, expansion and dissipation. Controls include play/pause, speed, seeking, key-event buttons, oblique/side/top cameras, two backgrounds, per-layer visibility, an occluder and a delayed second instance. Users with `prefers-reduced-motion` start on a still frame. Source lives under `examples/vfx-web/`; the bundle goes to ignored `.work/vfx-web/site/`. The running preview does not contact a CDN or remote generation service.

### Reuse in a project

Import `effect.js` with the project's Three.js bundler. This repository's dependency version is resolved by `web/package-lock.json`.

```js
import { createArcanePulse } from './effect.js';

const pulse = createArcanePulse({ seed: 17, color: '#57eadb' });
scene.add(pulse.group);
pulse.group.position.set(0, 0, 0);
// Each frame: seconds since activation; hidden at zero and at/after duration.
pulse.update(elapsedSeconds);
// Cancel/return to a pool: hide, then restart time from zero on the next activation.
pulse.update(0);
// Permanently remove: detach and release this instance's owned GPU resources.
pulse.dispose();
```

Coordinates are Three.js **Y-up**, ground XZ, with sizes in world units; the default outer wave radius is about 3.5. Place it using the group's transform. Each instance owns its materials/randomization and updates from absolute elapsed seconds, allowing backwards and forwards seeking. The reference event time is `pulse.impact` (0.46 seconds). This is visual design metadata; `update()` does not emit gameplay callbacks. The game must define event handling during pause, seeking and reactivation.

### Image/video-based soul flame

The local test used built-in ImageGen for one transparent soul-flame image and one Grok `image_to_video` call for a six-second reference. The observed video is 544×544 at 24 FPS with 145 frames. Inspected overview frames retain cyan fire, violet edges and branching shapes. It was converted to 96 frames at 16 FPS, each 256×256, in an 8-column/12-row PNG. These are sample choices, not universal quality thresholds. Originals and generation prompts remain in `.work/vfx-soul/reference/`, outside Git.

With local media matching that contract:

```sh
ffmpeg -hide_banner -loglevel error -n -i .work/vfx-soul/reference/soul-flame.mp4 -vf "fps=16,scale=256:256,tile=8x12" -frames:v 1 .work/vfx-soul/reference/soul-atlas.png
node examples/vfx-web/build.mjs --media-dir .work/vfx-soul/reference
```

The directory must contain `soul-flame.png`, `soul-flame.mp4` and `soul-atlas.png`. The example's `--media-dir` copies only these three files and configures the layout, frame count and FPS above. Other formats require matching settings/code. A fresh checkout has no generated media and opens the geometric sample. **Running that media-free default is not evidence of image/video-based production.**

After reloading, the soul flame is selected with its source image/video below; switch effects to compare the geometric shockwave. Runtime additions are frame blending, start/end fades, black-background removal and a ground halo, not true 3D volume or fluid solving. The camera-facing plane has depth, occlusion and intersection limitations. The uncompressed GPU RGBA8 atlas footprint is about 24 MiB without mipmaps; compressed file size differs from GPU cost.

`createSoulFlame({ texture, columns, rows, frames, fps })` exposes `group`, `duration`, `update(seconds)`, `setLayer(name, visible)` and `dispose()`. Layers are `body` and `halo`. The caller owns the texture and disposes it separately after removing its last instance. Frame selection supports reverse seeking and clamps to the final frame. UI looping retriggers the effect; it is not a continuous flame loop.

### Small automated checks and limits

```sh
node examples/vfx-web/build.mjs --test
node .work/vfx-web/effect.test.cjs
```

Checks cover reproducible reverse seeking, independent instance seeds/materials/layer settings, finite particle coordinates, start/end/restart, resource disposal events after repeated creation, and flipbook blending/texture ownership. **They do not measure GPU memory or approve actual rendering/performance.** Inspect key moments, transitions, backgrounds, occlusion and overlap in the browser separately. Fluid simulation, soft-particle intersection handling, collision/damage logic and cross-engine conversion are outside this example. Media generation uses available external tools; the example build itself does not call a generation service.

## Official references

- [Three.js ShaderMaterial](https://threejs.org/docs/pages/ShaderMaterial.html): Custom shaders and material settings.
- [Three.js resource cleanup](https://github.com/mrdoob/three.js/blob/r183/manual/en/cleanup.html): Removing objects and releasing GPU resources.
- [Godot 3D particles](https://docs.godotengine.org/en/stable/tutorials/3d/particles/index.html): A separate native representation for Godot projects.
