# Request specifications

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

For importing existing work use `provider: "import"` with `source` pointing to a `.glb` or `.blend`. The default `asset_kind: "static"` rejects armatures and can simplify geometry to the triangle budget. Explicit `asset_kind: "character"` preserves bones, weights and animation without flattening or decimation; an optional `target_height` uses one shared parent transform. Character imports without `target_height` retain their hierarchy transforms. Neither path performs animation-quality retopology or texture rebaking. See the [character guide](../../../../docs/CHARACTERS.md) for source constraints and visual review.

`PostprocessRequest` operates on an exact completed `asset_id` and `revision`. `operation` is `rig`, `animate` or `segment`, with `provider: "tripo"` and `max_credits: 100` defaults. Rigging supports `rig_type: "biped"`, `rig_model: "v1.0-20240301"`, and `rig_forward_axis: "+x"|"-x"|"+z"|"-z"` (default `+z`, the actual input GLB front). Animation supports `animation: "idle"|"walk"|"run"` (default `walk`) and `animate_in_place: true`, inheriting the parent's rig orientation; `segmentation_granularity` is `simple|balanced|detailed` (default `balanced`). Optional `triangle_budget` inherits the parent's value when omitted. No prompt or procedural input belongs in this request. Detailed examples, costs and prerequisites are in the [character guide](../../../../docs/CHARACTERS.md).

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

`rename` assigns a valid unique object name to one exact static part; it cannot use wildcard `part: "*"`. Assign semantic names only after inspecting that part's actual geometry/render. Edits reject rigged parents: change the preserved static parent and rig the new revision instead.

For observed shading/seam defects, edits also support `merge_distance` in meters (greater than 0 and at most 0.01) and `shading: "smooth"|"flat"`. Welding preserves per-corner UVs and recomputes face orientation; explicit shading changes discard imported custom normals. Use a very small scale-appropriate merge distance only after inspecting the mesh. These operations do not guarantee that holes, missing surfaces, UV artifacts or reference color drift are repaired; inspect the new renders.
