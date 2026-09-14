# Request specifications

For optional usage/quality contracts, `AssessmentRequest` accepts exact `asset_id`/`revision`, `usage` (purpose, assumptions, generic feature representations and named clip policies/rules/events), selected `clips`, sample/render budgets and `render`. See [QUALITY.md](../../../../docs/QUALITY.md) for tested examples and units. These are assessment fields, not generation or paid processing flags. Omitted usage loads existing GLB-bound intent; omitted clip selection assesses declared clips only. No schema implies automatic contact, semantic or visual approval.

New generation defaults to `provider: "trellis"`. A reference image is required, even when provider is omitted. Image-to-3D uses TRELLIS or explicitly user-selected `tripo`, not a Blender primitive reconstruction of the image. An `image` field with `procedural` or `import` is rejected. Procedural generation is an explicitly user-authorized alternative; supplied existing meshes can be imported without new inference.

Generation example (image path must exist; prompt is provenance, not a text-to-image command):

```json
{
  "asset_id": "oak-chest-ai",
  "provider": "trellis",
  "prompt": "Small oak chest for the game's inventory scene",
  "image": "/absolute/path/reference.png",
  "triangle_budget": 12000,
  "target_height": 0.75,
  "resolution": 512,
  "atlas": 1024,
  "seed": 42
}
```

IDs: lowercase letters, digits and hyphens, starting with a letter, at most 64 characters. TRELLIS resolution is 512 or 1024; atlas is 512, 1024 or 2048. TRELLIS currently runs one CLI inference per job; the resident server is not used.

For explicitly requested Tripo, use `provider: "tripo"` with either `image` or `views: {front, left?, back?, right?}`. Multiview requires front and at least one other view. The optional `tripo` object defaults to `{"model": "v3.1-20260211", "max_credits": 100}`; that is the currently supported model. `max_credits` accepts integers in 1–100000 when a user supplies a different limit. Standard generation is estimated at 30 credits; the default guard is not a retry budget. Do not ask the user to fill it for a standard requested generation. Input files are local PNG/JPEG; API keys never belong in specs. See the [Tripo guide](../../../../docs/TRIPO.md) for complete examples, supported output settings and the estimate guard's limits. No automatic provider or multiview fallback is permitted.

For procedural generation set `provider: "procedural"` and supply `recipe.materials` and `recipe.parts`. Full tested recipes live in the repository's `examples/sword.json` and `examples/chest.json`. Materials accept RGBA values in [0,1], metallic and roughness. Parts accept unique `name`, `primitive` (`box`, `cylinder`, `sphere`, `cone`), positive XYZ `dimensions`, XYZ `location`, `rotation_degrees`, `material`, `bevel`, and `segments` (3–64). Coordinates are Blender Z-up meters. Dimensions are local before rotation. New assets are centered on X/Y with their lowest point at Z=0. Optional target_height scales the whole asset uniformly.

For importing existing work use `provider: "import"` with `source` pointing to a `.glb` or `.blend`. Default `asset_kind: "static"` rejects armatures or animation and can simplify geometry to the triangle budget. `asset_kind: "character"` requires a rig and preserves bones, weights and clips. `asset_kind: "animated"` requires animation without requiring a rig, for object/morph clips. Both preserve hierarchy without flattening or decimation; optional `target_height` uses one shared parent transform and omission retains placement. Neither path performs automatic retopology or texture rebaking. See the [character guide](../../../../docs/CHARACTERS.md) and [Blender guide](../../../../docs/BLENDER.md).

`PostprocessRequest` uses exact completed `asset_id`/`revision`, `operation: "rig"|"animate"|"segment"` and defaults to `provider: "local"`. `process-plan`, `process` and `resume-process` are the general commands; Tripo-specific aliases retain explicit cloud selection. Optional `triangle_budget` inherits the parent. Shared animation fields are `animation: "idle"|"walk"|"run"` (default `walk`), `animate_in_place: true` and actual GLB front `rig_forward_axis: "+x"|"-x"|"+z"|"-z"` (default `+z`). Local animation accepts `bone_map` from canonical motion roles to observed unique bone names and retains other clips while replacing only the requested preset.

Local segmentation requires `segmentation_context` from `prepare-segment`, `segmentation_view` (0–11) and 1–32 uniquely named `segmentation_parts`. Each part has `name`, 1–64 `positive_points: [[x,y],...]` and optional `negative_points` (at most 64). Use nonnegative pixel coordinates from the inspected 1024×1024 selected context image. The agent authors these prompts; an unprompted generic split is not the local semantic workflow. Context and source hashes must match.

Only explicit Tripo uses `max_credits` (default 100), `rig_type: "biped"`, `rig_model: "v1.0-20240301"` and `segmentation_granularity: "simple"|"balanced"|"detailed"` (default `balanced`). Tripo animation inherits the parent's recorded rig orientation/task; local bone maps and segmentation prompts cannot be sent through that provider. See the [character guide](../../../../docs/CHARACTERS.md) for local examples and the [Tripo guide](../../../../docs/TRIPO.md#리깅애니메이션부품-분리) for paid options.

Edit example:

```json
{
  "asset_id": "azure-sword",
  "revision": "the_exact_revision_from_list",
  "description": "Make only the grip burgundy",
  "changes": [{"part": "grip", "color": [0.19, 0.015, 0.035, 1]}]
}
```

Edits accept `scale` (positive XYZ factors, around each object's origin), `offset` (XYZ translation), `color`, `metallic`, and `roughness`. `part: "*"` selects all meshes but still scales each around its own origin; it is not an assembly-scale operation. Exact object names come from inspection. Material edits copy materials for the selected part and replace connections only for changed shader inputs. Geometry edits can require related parts to move: lengthening the grip alone does not move the pommel or guard. Submit those related changes explicitly.

`rename` assigns a valid unique object name to one exact static part; it cannot use wildcard `part: "*"`. Assign semantic names only after inspecting that part's actual geometry/render. This static `edit` rejects rigged or animated parents; use `blender-edit` for these or broader modifications.

For observed shading/seam defects, edits also support `merge_distance` in meters (greater than 0 and at most 0.01) and `shading: "smooth"|"flat"`. Welding preserves per-corner UVs and recomputes face orientation; explicit shading changes discard imported custom normals. Use a very small scale-appropriate merge distance only after inspecting the mesh. These operations do not guarantee that holes, missing surfaces, UV artifacts or reference color drift are repaired; inspect the new renders.

`BlenderEditRequest` requires exact completed `asset_id`/`revision` and a local `.py` `script` path. Optional fields: `description`, JSON `parameters`, `preserve_animations: true`, `require_animation: false`, `preview_clips` (1–8 exact names) and `triangle_budget` (12–1000000, otherwise inherited). It executes trusted local Python with an injected `context`, not a sandbox. Existing rig, weight, material and custom motion changes do not depend on generation provider. See the [Blender guide](../../../../docs/BLENDER.md) for helper contracts, examples and recovery.

`KimodoMotionRequest` is for explicitly user-selected Kimodo and requires exact completed `asset_id`/`revision`, a nonblank `prompt`, a new `clip_name` and an observed SOMA-name → target-bone-name `bone_map`. `text-motion-plan` validates it before `text-motion`; `resume-text-motion` takes the incomplete child. Optional fields are `duration_seconds` (2–10, default 4), `seed` (0–2147483647, default 42), `diffusion_steps` (10–500, default 100), `forward_axis` (Blender Z-up world `+x`/`-x`/`+y`/`-y`, default `-y`), `in_place` (default false, removes horizontal root travel only), and `description`. It preserves existing clips and requires one weighted humanoid rig. Read [Kimodo](../../../../docs/KIMODO.md) for required mapping roles, isolated installation and limits; there is no paid fallback.

`AssessmentRequest` adds optional `views` (unique selections from `front`, `back`, `left`, `right`, `perspective`; default front/right/back) to its purpose/playback contract and sampling/render budget. `max_render_frames` (default 24) counts images across selected clips and angles in one call, not the whole task. Split calls with `clips` when needed, preserving the complete usage contract. Per-moment `views` and `unrendered_views` expose actual coverage; rendering is not visual approval. See [quality assessment](../../../../docs/QUALITY.md).

`MergeAnimationsRequest` requires exact completed base `asset_id`/`revision` and 1–32 `sources`. Each `AnimationSource` selects either `asset_id` plus exact `revision`, or an external `.glb` `path`; it may select unique `clips` (omitted means all) and `rename: {original: output}`. `on_conflict` defaults to `error`; explicit `replace` replaces matching names. Optional `description` and `preview_clips` (1–8 names) apply to the result. Compatible named hierarchy/rest/skin/morph data is required; differing rigs need a deliberate Blender retarget script first. The merge preserves the base geometry and does not automatically retarget.

`AnimationComparisonRequest` takes `before` and `after` GLB paths plus optional unique `changed_clips` (default empty). Paths resolve against the runtime root unless absolute. Every other existing clip is checked for preservation; undeclared additions are reported too. Declared names must occur in at least one input. `compare-animations` returns data differences synchronously without Blender, new revisions or automatic visual approval; see [the comparison contract](../../../../docs/BLENDER.md#개별-클립-수정과-보존-비교).
