# Request specifications

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

IDs: lowercase letters, digits and hyphens, starting with a letter, at most 64 characters. Resolution is 512 or 1024; atlas is 512, 1024 or 2048. No automatic multi-view fallback. TRELLIS currently runs one CLI inference per job; the resident server is not used.

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
