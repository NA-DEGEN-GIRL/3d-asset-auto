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

For explicitly requested Tripo, use `provider: "tripo"` with either `image` or `views: {front, left?, back?, right?}`. Multiview requires front and at least one other view. Supply `tripo: {"model": "v3.1-20260211", "max_credits": 30}`; that is the currently supported model and default. An integer `max_credits` in 1–100000 is required. Input files are local PNG/JPEG; API keys never belong in specs. See the [Tripo guide](../../../../docs/TRIPO.md) for complete examples, supported output settings and the estimate guard's limits. No automatic provider or multiview fallback is permitted.

For procedural generation set `provider: "procedural"` and supply `recipe.materials` and `recipe.parts`. Full tested recipes live in the repository's `examples/sword.json` and `examples/chest.json`. Materials accept RGBA values in [0,1], metallic and roughness. Parts accept unique `name`, `primitive` (`box`, `cylinder`, `sphere`, `cone`), positive XYZ `dimensions`, XYZ `location`, `rotation_degrees`, `material`, `bevel`, and `segments` (3–64). Coordinates are Blender Z-up meters. Dimensions are local before rotation. New assets are centered on X/Y with their lowest point at Z=0. Optional target_height scales the whole asset uniformly.

For importing existing work use `provider: "import"` with `source` pointing to a `.glb` or `.blend`. This static pipeline rejects armatures. It can simplify dense geometry to the triangle budget; review the resulting silhouette and texture seams. It does not perform animation-quality retopology or texture rebaking.

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

For observed shading/seam defects, edits also support `merge_distance` in meters (greater than 0 and at most 0.01) and `shading: "smooth"|"flat"`. Welding preserves per-corner UVs and recomputes face orientation; explicit shading changes discard imported custom normals. Use a very small scale-appropriate merge distance only after inspecting the mesh. These operations do not guarantee that holes, missing surfaces, UV artifacts or reference color drift are repaired; inspect the new renders.
