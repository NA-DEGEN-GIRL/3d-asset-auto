# Rigging, animation and segmentation

[한국어](CHARACTERS.md) | **English**

Editing is independent of generation and defaults to **local processing**. Choose static geometry, object motion, an existing rig, a SkinTokens draft or custom Blender scripts according to the request/model. This guide covers `process` rigging, presets and GeoSAM2 segmentation. For custom motion, rig/weight editing and clip assembly, use [Blender authoring](BLENDER.en.md). Local processing needs no API key or Tripo credits; install models only for needed inference.

Use `provider: "tripo"` or the legacy `tripo-process` command only when explicitly selected. Setup failure or key presence does not select a paid fallback. See [Tripo processing](TRIPO.en.md#rigging-animation-and-segmentation) for costs, orientation and recovery.

## Inputs and processing choices

Provide an exact completed `asset_id` and parent `revision`. Generation and processing providers are separate. Results create a new revision preserving parent/source/hashes.

| Operation | Default local implementation | Input |
| --- | --- | --- |
| `rig` | SkinTokens skeleton/weight inference transferred to the original mesh | Completed static GLB |
| `animate` | Procedural biped IK/rotation on actual Blender bones | Completed rig and observed names |
| `segment` | GeoSAM2 learned point masks propagated to mesh faces | Prepared static views and agent-selected part points |

Manual bones or connectivity splits are not learned inference. Presets are procedural; explicitly selected [Kimodo](KIMODO.en.md) provides a separate learned human-motion path. Custom/non-biped authoring uses Blender scripts. General automatic retarget solvers, retopology and texture rebaking are not implemented.

Follow [on-demand installation](../INSTALL.md#local-postprocessing-on-demand). Rigging/segmentation inference runs in Linux/WSL; normal processing/rendering uses installed Blender. Procedural motion and custom scripts need no extra AI model. Kimodo setup/inference requires explicit selection.

## Rigging

Save a static parent in `.work/rig.json`. Omitted provider defaults to local:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "rig"
}
```

```sh
uv run --no-sync python -m asset_auto.cli process-plan .work/rig.json
uv run --no-sync python -m asset_auto.cli process .work/rig.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

SkinTokens uses the current GLB and `use_transfer` to transfer predicted bones/weights to its original mesh. Inspect skins, unweighted vertices, hierarchy and five actual overview renders for preserved silhouette/materials. Success is not automatic rig approval. Numeric `bone_...` names do not establish anatomy. Refine the draft with `blender-edit` when needed.

## Animation

Local presets accept imported or Tripo rigs without a remote task ID. They require one armature, valid weights for all mesh vertices and positive uniform armature scale. Rig only when deformation needs it; use [object keyframes](BLENDER.en.md#scripted-editing) for rigid motion.

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_RIGGED_REVISION",
  "operation": "animate",
  "animation": "walk",
  "animate_in_place": true
}
```

Save `.work/walk.json`, then use `process-plan` and `process --async`. `animation` is `idle`, `walk` or `run` (default `walk`); `animate_in_place` defaults to `true`. A new revision adds/replaces only the requested preset while retaining other clips. Sequential `idle` → `walk` → `run` accumulates all three; use [merging](BLENDER.en.md#several-motions-in-one-glb) for separate outputs.

Recognized bone names can map automatically. Otherwise the agent reads actual `head_world`, `tail_world` and hierarchy to supply `bone_map`, without asking the user to annotate or inferring anatomy from numbers. Example format:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_RIGGED_REVISION",
  "operation": "animate",
  "animation": "walk",
  "bone_map": {
    "left_thigh": "observed_left_thigh",
    "left_shin": "observed_left_shin",
    "left_foot": "observed_left_foot",
    "right_thigh": "observed_right_thigh",
    "right_shin": "observed_right_shin",
    "right_foot": "observed_right_foot"
  }
}
```

`walk`/`run` require both thigh→shin→foot chains; `idle` requires chest. Other roles include root, pelvis, chest, head and both upper arms/forearms. Match `rig_forward_axis` to the inspected model. Supported aliases live in the [motion worker](../src/asset_auto/blender_motion_worker.py).

Probe required chains/deformation before complex motion on new, changed or unverified rigs. Use [staged diagnosis](QUALITY.en.md#staged-rig-and-motion-diagnosis) for source motion, mapping, weights, equipment and export; reuse only relevant unchanged evidence.

Inspect overview views, animation PNGs and dense floor checks in `local-motion.json`. `ground_checks` refers to the reimported final GLB; `generated_ground_checks` refers to the intermediate. Each artifact records file/stage/SHA256, also retained in inspection/manifest. Review IK limits, correction magnitude and actual surface deformation together. Foot-sliding prevention, heel-to-toe gait and continuous self-collision checks are not implemented; floor correction does not establish natural walking.

Automatic previews cover at most eight clips × three frames. Imported clips remain preserved, but `sampled_clips < total_clips` means missing visual coverage. Samples do not prove the full timeline.

## Segmentation and part names

The agent observes prepared views, names parts and selects points; GeoSAM2 propagates masks. **The end user is not required to draw masks/points.** Start from a completed static parent:

```sh
uv run --no-sync python -m asset_auto.cli prepare-segment ASSET_ID REVISION --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

The returned `context` is a hash-bound `.work/segment-contexts/.../context.json` with the source GLB, twelve views and geometry. Inspect 1024×1024 `color_0000.png` through `color_0011.png`, choose a useful `segmentation_view` (0–11), and specify actual original-resolution pixels. Replace these example coordinates:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "segment",
  "segmentation_context": "/absolute/runtime/.work/segment-contexts/CONTEXT_ID/context.json",
  "segmentation_view": 0,
  "segmentation_parts": [
    {"name": "head", "positive_points": [[512, 240]], "negative_points": [[512, 600]]},
    {"name": "torso", "positive_points": [[512, 540]], "negative_points": [[512, 240]]}
  ]
}
```

Save `.work/segment.json`, then use `process-plan` and `process --async`. Positive points include a region; negative points exclude it. Convert displayed coordinates back to the original image scale if needed. Changed source/context files require new preparation.

Names are proposed semantics, not proof of correct segmentation. Retain uncertain faces in `unclassified`. This path preserves triangles, UVs, materials, normals and positions, reporting budget excess without automatic reduction. Inspect all overview and individual `part-previews.json` images for boundaries, overlap, missing regions and texture changes. Connectivity splits alone do not establish semantic parts.

Rename inspected static parts using `edit`:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_SEGMENTED_REVISION",
  "description": "Name the left-arm part confirmed in individual renders",
  "changes": [{"part": "actual_mesh_name", "rename": "left_arm"}]
}
```

Part previews are limited to 32. `truncated: true` leaves remaining parts unreviewed. Segmentation does not create a rig or joint-ready topology. Report open cuts, fused regions and material defects as observed.

## Character preservation and edit boundaries

Import external rigs explicitly:

```json
{
  "asset_id": "imported-character",
  "provider": "import",
  "asset_kind": "character",
  "source": "/absolute/path/character.glb"
}
```

Use `asset_kind: "animated"` for unrigged object/morph motion. `character` requires a rig; `animated` requires actual clips. Default static import rejects rigs/animation.

The character path preserves bones, weights and clips without static flattening or automatic reduction. An explicit target height uses a common Empty parent for scale/floor alignment. Local processing keeps existing size/position; Tripo orientation restoration also uses a shared parent. Multiple Armature modifiers on one mesh are rejected.

Use `blender-edit` for rigged/animated parents and broader character geometry/material/weight/motion edits. Preserve existing clips by default and declare intended replacements. When appropriate, major shape repair can happen on a static parent before rigging.

## Records and recovery

```sh
uv run --no-sync python -m asset_auto.cli resume-process ASSET_ID REVISION --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

Resume the saved incomplete child using its exact provider/request/source/context. Keep local processing provenance separate from generation and retain verified intermediate outputs. Incomplete local inference may rerun when no reusable output exists. Explicit Tripo uses stage checkpoints and resumes known remote tasks; an unknown submission outcome requires reconciliation, not automatic POST retry. Completed revisions are not overwritten.

## Review and recorded validation

Choose purpose-specific criteria from [QUALITY](QUALITY.en.md). Optional assessment adds conditional loop/activity/root checks and critical renders, not automatic contact, naturalness or integration approval. Deliver Blend, GLB and findings; record only inspected images/playback as visual evidence. The shared viewer's static loading does not validate animation.

Recorded local results:

- GeoSAM2 preserved 18,984 triangles with ten agent-observed names plus `unclassified` (2,283 faces, about 12%). Five overviews and eleven part images were reviewed. Overall appearance was preserved, but missed/misclassified regions and open boundaries left semantic part quality a draft/failed visual review. The original model came from an earlier Tripo generation; this processing made no API calls. Static segmentation smoke checks preserved geometry/UV/material/normal/transforms and did not decimate over-budget assets.
- SkinTokens on that zombie produced 46 bones, 15,741 weighted vertices and no unweighted vertices, with source hashes and five-view static appearance checked.
- Local `idle`/`walk`/`run` passed the recorded prototype appearance/deformation review across nine sample images. These are short-stride, mostly flat-foot presets; natural gait, continuous self-collision and absence of sliding were not established.
- Reimported final-GLB floor checks at authored and half frames used 121/61/41 samples, with maximum penetration 0/0.128/0.661 mm within that model's 2 mm tolerance. Maximum rest-position difference was about 2.58×10⁻⁷ m; normalized weight L1 difference about 3.73×10⁻⁸. Material/image bytes were preserved. No paid calls were used for local rigging or these clips.
- An unrelated MIT Microsoft Rocketbox adult model produced 80 bones, 7,440 triangles and 4,803 weighted vertices, with no unweighted vertices, preserved source hash and five-view static review. Adult motion remains untested.
- Windows tests, Linux process-lifetime checks, Ruff/web builds and static Blender/Godot, character, motion and segmentation smoke checks passed. Readiness, mocks, actual inference and visual quality remain separate claims.

Earlier paid Tripo generation/segmentation/rigging/walking used 30/40/25/10 credits. Its 13 segmented regions retained fused areas/open cuts; the remote walk penetrated the floor and failed gait review. See [Tripo evidence](TRIPO.en.md#recorded-validation).
