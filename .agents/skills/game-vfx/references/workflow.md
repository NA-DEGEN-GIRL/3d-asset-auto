# Authoring and review

## Project and representation

Inspect the existing engine/renderer, relevant version/backend, release platform, camera range, interaction and output contract before choosing implementation. A web project may use different rendering backends; Godot desktop and web exports may expose different features. Check the actual configuration and needed features rather than inferring capability from an engine name. Reuse working project materials/particles when they fit; do not install a second engine or a new effect library merely to follow an example.

Keep two concerns distinct: producing ingredients (meshes, textures, fields, baked motion) and assembling their target playback (materials, emitters, trails, lighting and events). Choose them together early enough to avoid an unplayable bake. If the target is unknown, an explicit portable-format request can still be completed; clarify only missing constraints that materially change the result. Shared ingredients and effect intent are not an automatic shader/scene conversion contract.

## Expression before implementation

For each effect, identify the characteristics that make the adopted reference recognizable in motion, including its large-scale shape and event rhythm where relevant. Preserve those characteristics before adding fine noise, particles or glow. A plausible effect of the same element may still miss the requested expression. Infer useful defaults from the request and project, and record the intended differences when adapting a reference.

Useful example criteria:

| Effect | Expression to test | Likely technical failure |
| --- | --- | --- |
| Fire | An evolving hot core, curling tongues and an energetic rise or burst; cooling material reads differently | A static glowing cone, opaque shell, rectangular volume boundary or detached sparks |
| Ice | Readable mass and descent, coherent contact, a decisive breakup and debris settling | A flat splash replacing the chunk, hovering fragments, premature shattering or loss of scale |
| Lightning | Directed strike, hierarchical branches, brief varied pulses and a clear endpoint | A smooth tube, evenly spaced decorative twigs, disconnected flash or branches visible only from one view |

These are diagnostic examples, not requirements for every style. A quiet magical flame or sustained electrical beam needs different timing. Choose criteria and effort for the intended result.

## Image and temporal references

Use supplied or existing references when sufficient. ImageGen can establish shape, palette and material; an authorized video tool such as Grok Imagine can clarify acceleration, secondary motion and event order. Consult the repository's [motion reference workflow](../../../../docs/MOTION_REFERENCES.md) for the existing Grok path and its input, cost and recovery handling. A reference-generation request is not permission for unlimited variants or paid retries.

Prepare adequate references per effect. A combined mood board may establish a common style, but it cannot demonstrate each effect's temporal behavior. Inspect the actual returned media and reject unintended shape changes, reversed causal order, inconsistent scale or implausible contacts. Generated frames are design candidates, not captured 3D trajectories or proof of realizable physics.

Separate adopted expressions from rejected artifacts. If still images leave timing or spatial relationships unclear, use a short temporal reference or a rough animated study; do not keep adding panels that repeat the same ambiguous pose. Match important events rather than frame numbers when reference and final durations differ. Keep usable media and generation metadata, excluding tokens and raw credential-bearing logs.

## Choose the production path

Use the simplest representation that meets the intended camera, interaction and quality requirements:

- **Authored fields and shaders:** flowing fire, magical energy and distortion can use procedural fields sampled in spatial geometry or volumes. A renderer's field or ray-marching shader is not a Blender fluid simulation. Preserve the field recipe and target shader together.
- **Curves, ribbons and meshes:** arcs, trails, blades, rings and branches benefit from reusable trajectory/width/time controls. Test perspective and occlusion; a ribbon may be appropriate while still requiring thickness or additional orientations for the expected camera range.
- **Mesh animation or baked physics:** use existing models plus Blender object animation, cuts or rigid bodies for solid fragments. A precomputed contact with a flat ground is not live collision with arbitrary terrain. Reuse `3d-assets` sources without changing completed revisions.
- **Particles and flipbooks:** appropriate for embers, mist, smoke accents and camera-constrained elements. Test transparency and overlap. A whole reference video on one plane does not satisfy a free-camera spatial spell.
- **Offline simulation:** use Blender/Mantaflow when fluid evolution contributes to the target shape or motion. Gas/fire/smoke and liquid paths produce different ingredients and require suitable conversion. Ice solids or lightning do not become fluid tasks simply because this tool is installed. Use the [bake workflow](#simulation-ingredients) when chosen; the supplied gallery is not a general volume-cache exporter/player.

Adapt fitting components and connect dependent visual layers to the same authored event positions and times. For multiple contacts, releases or moving sources, verify that each response follows its own cause; a shared decorative burst can conceal missing behavior. Decompose combined spells into named layers/events for inspection. If adjustments cannot recover the intended expression, change the relevant structure, representation or source rather than repeating small parameter edits.

## Simulation ingredients

First prove a bounded authoring → bake → conversion → target-playback path for the relevant behavior. Preserve the editable scene, source cache, settings, frame times, units/bounds and conversion provenance. Match original and converted samples at the same source time before judging the final composition. Inspect domain clipping, quantization/filtering and source-to-playback time mapping when shape or rhythm changes. Neither a completed bake nor a cache file proves that the expected field or mesh was rendered.

Choose the delivery representation for the camera and budget: mesh animation, particle textures/flipbooks, sampled volumes or another supported representation. A view-dependent bake needs an explicit camera contract; it cannot silently replace a requested spatial main effect. The maintained helper in this skill produces procedural ingredients, not Mantaflow caches. Task-specific Blender scripts and conversion/runtime work are needed for a fluid route; a local experiment does not establish a shipped one-command tool or a tested liquid adapter. Consult the [Blender fluid manual](https://docs.blender.org/manual/en/latest/physics/fluid/introduction.html) for the selected Blender version rather than inventing helper flags.

Simulation is a source for artistic shaping. Inspect the primary layer without glow/secondary particles where useful: a smooth hot rod, broad puff or washed-out core can survive a successful solver run. Locate the first loss of expression in source, conversion, material or composition, then change that cause. Spatial taper, color/opacity transfer or moving material detail may help; label them as authored treatments rather than additional solved turbulence. Recheck that they retain the adopted mass, motion and rhythm. Preserve revisions instead of repeatedly rebaking over the source.

## From authoring to game playback

Keep the `.blend` or other editable source alongside the exported geometry, textures, parameters and target code. Record seed, input hashes, coordinate conversion, size, duration, event times and resource ownership. Blender uses Z-up; glTF and these web examples use Y-up. Avoid converting an imported GLB twice.

Plan how the effect starts, seeks, stops, restarts and finishes. A seeded absolute-time update is useful for reproducible review, but target gameplay may also need live endpoints, attachment transforms or collision callbacks. Keep visual contact events distinct from damage logic. State when scene lighting, post-processing or a particular shader is required for the shown result.

Bind causally related layers to the same event positions and playback clock. Distinguish an object's center from its visible contact surface, and source-frame time from game time. A moving local volume can drag its old wake with it; use appropriate world/local placement for trails and lingering material. Verify the visible contact and transition, not only matching origin coordinates. Record artistic scaling, retiming, clipping and fades separately from source physics.

For a requested web preview, use the example build/runtime contract in [runtime.md](runtime.md). For an existing game project, implement or adapt only its renderer path. A web viewer's material override or particle layer is not embedded in the GLB. Engine-agnostic delivery can preserve ingredients and intent, but should not claim untested portability.

## Delivery format constraints

An explicit format is a design input. For example, a three-second blue fire pillar requested **only as GLB** can be authored using animated emissive meshes, morph targets or bones, with embedded textures where useful. It needs no learned mesh generation or pre-existing model. Choose and review that representation against the requested silhouette and motion; it will not automatically reproduce a spatial shader's appearance.

The supplied helper's `recipe-geometry.glb` contains static lightning geometry. It is neither an animated fire effect nor a container for the web shader. A GLB-only fire request therefore needs additional Blender authoring/export, not an invented helper flag, a renamed example file or an unrequested viewer. Inspect the final exported animation; do not assume Blender procedural material nodes, animated shader values or simulation caches transferred.

Keep editable working sources locally, but honor the requested delivered files. If the required look cannot be met in the requested format, describe the concrete missing behavior and the available representation/runtime tradeoff before changing the delivery contract. An unspecified engine alone does not block portable GLB authoring or justify choosing an engine for the user.

## Per-effect quality loop

1. Inspect the final rendered effect at normal game distance and any revealing close-up. Compare reference and result at the adopted events: buildup, peak, contact/release and decay where relevant. Match camera and framing enough for a useful comparison.
2. Hold the same important instant and inspect complementary angles. Replay transitions and pulses at the intended speed. Static meshes visible from several angles do not establish that the moving effect retains depth or timing.
3. Test relevant scene conditions: bright/dark backgrounds, foreground occluders, nearby geometry, ground contact, simultaneous instances and supported scale changes. Check empty/prestart time, cancellation, restart and post-lifetime behavior when part of the contract. Choose coverage from the effect's risks, not a universal number of images.
4. Record the defect, moment, view, failed criterion and likely source. Correct authoring, bake/export or runtime as appropriate. Re-export/rebuild and compare the same conditions, including plausible regressions in expression and untouched effects.
5. Separate structural correctness, visual expression and target integration. Compare the complete result with the adopted quality target at normal playback and viewing distance, beyond isolated details or defect-free frames. A working component study remains incomplete when its defining shape, timing or material character is missing. Record the remaining visible difference and repair its cause, or report the concrete limit preventing completion.

Treat excessive brightness, geometry and particles as costs, not substitutes for expression. A user-rejected or visibly inadequate example is not an acceptance baseline just because its runtime works. Completion requires both the adopted expression and the applicable technical criteria; bounded test artifacts may remain explicitly incomplete.

## Runtime cost and target checks

Identify target constraints early and measure before claiming game readiness. Choose representative resolution/device, viewing distance and concurrent effects from the project; avoid universal particle limits or automatic quality reductions for every web game. Separate compressed download size from decoded CPU memory, GPU resources/upload cost and rendering time. Transparent screen coverage, overlap, ray-marching and repeated instances can dominate even with small geometry or compressed files.

For the actual target, check required depth/blending, scene lighting, loading/first-use behavior and lifecycle/resource ownership. Warm up only where relevant, and confirm that stopping or disposing an instance does not corrupt shared resources. Record what was measured and what remains unknown. After optimization, repeat the same visual comparisons; a faster but flattened or weakened effect is a regression if it loses the agreed expression.

Check only the requested or project-relevant adapter. Moving a reviewed web effect to Godot requires review of that export/backend; the source ingredients and event intent can transfer without implying identical materials or performance. Do not build both engines on every asset request. Engine feature limits change: consult the installed version and official documentation when selecting features rather than embedding timeless claims such as “web supports only CPU particles.”

## Licensing and provenance

Prefer the existing local Blender toolchain, original authored materials and explicitly compatible dependencies. Record the origin and terms of models, textures, fonts, reference media and reusable code; distinguish study-only references from shipped content. Model/provider output terms still apply when a generated asset is reused, and a public URL alone does not grant redistribution rights.

Blender's license does not apply its GPL to ordinary artwork/export data, while its published Python API scripts have separate GPL-compliance requirements. Follow the [official Blender license guidance](https://www.blender.org/about/license/) when distributing the helper or add-ons. Preserve applicable runtime dependency notices. This distinction does not clear third-party material embedded in an output or require licensing an entire existing repository anew.

Keep actual tool runs and output hashes as provenance. Label authored shaders, procedural geometry, simulation bakes and learned model output accurately. Do not infer license clearance, model inference, fluid simulation or visual approval from a file's existence.
