# Local Blender editing and clip merging

[한국어](BLENDER.md) | **English**

Editing is independent of generation: TRELLIS, Tripo and imported assets can all be edited locally. Keep static props unrigged and use object keyframes for rigid parts. When deformation needs a rig, use an existing one or a [SkinTokens draft](CHARACTERS.en.md#rigging), then refine weights, rigs and motion in Blender.

`blender-edit` snapshots a completed parent and an agent-authored Python script into a new revision. It executes trusted local `bpy` code with full Blender/process privileges. It is not a sandbox or a viewer execution API, and must not bypass the inference requirement for new meshes.

## Scripted editing

Import external unrigged object/morph clips with `provider: "import", asset_kind: "animated"`; use `character` for rigs. Static import/edit reject rigs and animation. Read actual object names with `inspect`.

This example adds an object-level `hover` clip. For an assembly, animate a shared root/Empty while preserving relative placement. Save as `.work/hover.py`:

```python
import bpy
from mathutils import Vector

obj = context.objects[context.parameters["object"]]
rest = obj.location.copy()
scene = bpy.context.scene
frames = max(2, round(scene.render.fps / scene.render.fps_base))
context.new_action(obj, "hover")
for frame, height in [(1, 0.0), (1 + frames // 2, 0.08), (1 + frames, 0.0)]:
    obj.location = rest + Vector((0.0, 0.0, height))
    obj.keyframe_insert(data_path="location", frame=frame)
context.stash_action(obj)
```

Save `.work/hover.json` with an exact parent, absolute script path and actual object name:

```json
{
  "asset_id": "my-prop",
  "revision": "EXACT_PARENT_REVISION",
  "script": "/absolute/runtime/.work/hover.py",
  "description": "Add a short hover clip to the existing prop",
  "parameters": {"object": "ACTUAL_OBJECT_NAME"},
  "require_animation": true,
  "preview_clips": ["hover"]
}
```

```sh
uv run --no-sync python -m asset_auto.cli blender-edit .work/hover.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

The script edits the source scene; the runtime exports, inspects and renders. `preserve_animations` defaults to `true`, rejecting changed/deleted existing actions and missing output clips. Retain FPS and `fps_base` to preserve playback speed. Set preservation to `false` only for intended existing-clip edits/retiming and preserve other clips in the script. `require_animation` defaults to `false`; `preview_clips` accepts up to eight actual names; omitted `triangle_budget` inherits the parent's value. Exceeding a budget does not trigger automatic rig decimation.

The injected context is implemented in [authoring tools](../src/asset_auto/blender_authoring_tools.py):

| API | Purpose |
| --- | --- |
| `objects`, `armatures` | Actual scene-name/object mapping and armature list |
| `parameters`, `source`, `output` | Request parameters and absolute snapshot/output paths |
| `capture_rest()` | Record intentionally changed object transforms/morph defaults before keyframing |
| `reset_pose()` | Restore recorded object/morph/bone defaults without deleting clips |
| `new_action(owner, name)` | Stash the existing clip and create a uniquely named action/slot |
| `stash_action(owner, name=None)` | Store the active action/slot as an exportable clip |
| `bake_action(owner, name, frame_start, frame_end)` | Bake prepared constraints/retargeting to object/pose keyframes |

Authoring coordinates are Blender Z-up meters. Bone edit-mode structure, mesh coordinates, weights and materials do not require `capture_rest()`. Custom authoring is not learned motion or a general automatic retarget solver. Bake constraints as needed and verify the final exported motion/deformation.

## Several motions in one GLB

Default delivery is **one GLB containing every requested named clip**. Merge compatible provider outputs, including separate Tripo clips, and verify the final inventory. Deliver separate files only when requested, retaining intermediate revisions.

Follow [per-clip completion](QUALITY.en.md#complete-each-requested-clip): provide sufficient references and author/review/repair each motion. A compressed overview sheet or successful merge does not complete all clips.

Local `process` presets retain other clips and replace only the requested name in a new revision. Applying `idle`, then `walk`, then `run` accumulates all three.

For separate outputs, save `.work/merge.json`:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_BASE_REVISION",
  "sources": [
    {"asset_id": "my-character", "revision": "EXACT_WALK_REVISION", "clips": ["walk"]},
    {"path": "/absolute/path/compatible-run.glb", "clips": ["run"], "rename": {"run": "sprint"}}
  ],
  "preview_clips": ["walk", "sprint"]
}
```

```sh
uv run --no-sync python -m asset_auto.cli merge-animations .work/merge.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

There may be 1–32 sources. Omitted `clips` selects all named source clips. `rename` maps original names to output names. The default `on_conflict: "error"` rejects duplicates; use `"replace"` only for intended replacements.

Merging preserves the base geometry, skin and rest state while transferring compatible clips. Similar bone names alone are insufficient. Incompatible hierarchies, rest transforms, skin or morph layouts require an explicit mapped constraint/bake retargeting script first. Animation extensions are unsupported and are not silently discarded.

## Editing one clip and comparing preservation

Declare the intended clip names and edit scope first. `blender-edit` uses the completed parent's hash-verified `source.blend`. Reimporting GLB inside the script or rebuilding all clips at another FPS can resample untouched motion. Reuse source actions and their timebase. `preserve_animations: false` and `preview_clips` do **not** automatically enforce a per-clip edit allowlist.

`compare-animations` reads two final GLBs and returns JSON immediately, without Blender, GPU work or API calls. `changed_clips` declares intended additions, edits or removals; omission protects all existing clips. Duplicate names and declarations absent from both inputs are rejected. Relative paths resolve against the runtime root; use absolute paths for external files.

Save `.work/compare-clips.json`:

```json
{
  "before": "/absolute/runtime/.assets/my-character/BEFORE_REVISION/asset.glb",
  "after": "/absolute/runtime/.assets/my-character/AFTER_REVISION/asset.glb",
  "changed_clips": ["cast"]
}
```

```sh
uv run --no-sync python -m asset_auto.cli compare-animations .work/compare-clips.json
```

MCP `compare_asset_animations(request)` performs the same check. Save returned evidence and input hashes in local work notes when needed. It does not modify inputs, revisions or review records. Successful execution is not automatically a preservation pass.

- `clips`: added/removed/changed status, start/end/span in seconds, key count and time/interpolation/transform/morph differences. Decoded data is compared independently of buffer offsets or sparse/interleaved storage; cubic tangents are included.
- `model_context`: core glTF mesh, weights, binds, node defaults/hierarchy, materials and images. Equal channels cannot approve unchanged deformation/appearance if this context changed. Unsupported extensions produce `unverified`.
- `preservation_status`: `preserved` for equal protected clips and model context; `changed` for unexpected clip/model changes; `unverified` when context cannot be verified; `no_protected_clips` when no existing clips are protected. Intended edited motion still needs its own review.

This is exact data preservation, not a sampled equivalence test. Resampling, equivalent quaternion representations or node reordering can conservatively report `changed`. When needed, compare actual joints/deformed geometry at matching seconds in Blender, using suitable correspondence and tolerances if topology changed. Check duration/start time before normalized phase comparisons; matching endpoints or progress percentages can hide retiming. Playback, contacts, visual quality and `usage.json` policies are outside this tool's verdict.

If only the clip changed and the model/rig remains compatible, merge just that corrected clip into the base GLB to avoid re-exporting the others. If shared mesh/rig/weights changed, use the corrected model as the final base and review affected motions. Do not revert a needed model repair just to obtain identical preservation numbers.

## Review and recovery

Use [quality assessment](QUALITY.en.md) when functional features or important motion need usage policies, conditional measurements and critical renders. For unclear or repeatedly failing motion, use [references](QUALITY.en.md#using-motion-references). Diagnose the responsible stage with [staged comparison](QUALITY.en.md#staged-rig-and-motion-diagnosis). Edits and merges inherit hash-bound usage intent but require fresh evidence for the resulting revision.

`authoring-request.json` binds the request and snapshots: `input.glb`, `input.blend`, `script.py` or merge inputs `animation-N.glb`. `local_processing` records the operation/input/hashes separately from original generation. Inspect overview PNGs and actual `animation-previews.json` images. The automatic overview is limited to eight clips × three frames; choose changed clips with `preview_clips` and disclose unreviewed coverage. Custom scripts do not automatically receive naturalness, contact or continuous-collision validation.

```sh
uv run --no-sync python -m asset_auto.cli resume-blender-edit ASSET_ID CHILD_REVISION --async
uv run --no-sync python -m asset_auto.cli resume-merge-animations ASSET_ID CHILD_REVISION --async
```

Read the failed job and resume its incomplete child. Once `authored.blend` and its hash-bound execution checkpoint exist, render/export recovery does not rerun the script. Before that checkpoint, rerunning from the source snapshot may be necessary; account for script side effects. Changed inputs/scripts require a new edit, not mutation of the saved recovery request.

MCP exposes `edit_in_blender`, `merge_asset_animations`, `resume_blender_edit` and `resume_animation_merge`; query returned jobs with `asset_job_status`. Use Godot/viewers only for relevant integration or requested previews.
