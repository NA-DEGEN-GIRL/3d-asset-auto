# Authoring and review

## Expression before implementation

For each effect, select the visible characteristics that carry its identity: silhouette, path, build-up, peak event, secondary response and dissipation as relevant. Infer useful defaults from the request and project. Record enough to compare the output, rather than reducing every spell to the same expanding ring plus particles.

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
- **Heavier simulation:** consider Blender fluid/volume baking when the requested behavior benefits from it. Probe a bounded setup before long bakes, then verify the chosen export/playback path. The current examples do not establish Mantaflow, liquid or general volume-cache delivery.

Adapt a fitting component instead of reconstructing its infrastructure for every request. When repeated adjustments cannot recover the target expression, reconsider the representation or source, not only constants. Decompose combined spells into named visual layers and events so their contribution can be inspected separately.

## From authoring to game playback

Keep the `.blend` or other editable source alongside the exported geometry, textures, parameters and target code. Record seed, input hashes, coordinate conversion, size, duration, event times and resource ownership. Blender uses Z-up; glTF and these web examples use Y-up. Avoid converting an imported GLB twice.

Plan how the effect starts, seeks, stops, restarts and finishes. A seeded absolute-time update is useful for reproducible review, but target gameplay may also need live endpoints, attachment transforms or collision callbacks. Keep visual contact events distinct from damage logic. State when scene lighting, post-processing or a particular shader is required for the shown result.

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
5. Separate numeric/structural results, visual expression and target integration. Completion requires the relevant observed criteria, not just tests passing. If a real time/cost constraint stops repairs or an approach stalls, retain the best source and report the specific unresolved behavior rather than calling it approved.

Treat excessive brightness, geometry and particles as costs, not substitutes for expression. Test performance at the requested resolution, hardware and simultaneous count before making performance claims; a responsive isolated demo establishes only that tested case.

## Licensing and provenance

Prefer the existing local Blender toolchain, original authored materials and explicitly compatible dependencies. Record the origin and terms of models, textures, fonts, reference media and reusable code; distinguish study-only references from shipped content. Model/provider output terms still apply when a generated asset is reused, and a public URL alone does not grant redistribution rights.

Blender's license does not apply its GPL to ordinary artwork/export data, while its published Python API scripts have separate GPL-compliance requirements. Follow the [official Blender license guidance](https://www.blender.org/about/license/) when distributing the helper or add-ons. Preserve applicable runtime dependency notices. This distinction does not clear third-party material embedded in an output or require licensing an entire existing repository anew.

Keep actual tool runs and output hashes as provenance. Label authored shaders, procedural geometry, simulation bakes and learned model output accurately. Do not infer license clearance, model inference, fluid simulation or visual approval from a file's existence.
