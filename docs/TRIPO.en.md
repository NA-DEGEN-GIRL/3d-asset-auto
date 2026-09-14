# Optional Tripo3D API

[한국어](TRIPO.md) | **English**

The default generator is local TRELLIS.2. Select `provider: "tripo"` **only when the user explicitly requests Tripo/Tripo3D**. A key, unavailable GPU or multiview references do not automatically select it. Tripo uploads input images to an external service and consumes paid credits.

The generation adapter accepts a single image or 2–4 views including front, then runs Blender processing, five-view renders and GLB export. Selecting Tripo generation does not select paid editing. Subsequent work can use [local Blender authoring/merging](BLENDER.en.md) or [local rigging/segmentation](CHARACTERS.en.md). Paid processing below requires its own explicit selection. No automatic engine/viewer startup is included. Direct text-to-model and advanced generation-quality options are not implemented.

An explicit standard-generation request covers **one generation per requested asset**, without repeated credit confirmation. The optional `tripo.max_credits` estimate guard defaults to 100; the standard-generation estimate is 30. A 100-credit guard is not a retry allowance. If the user requests both single-image and multiview tests, one of each is within that scope. A smaller user budget takes priority. Unrequested variants, upgrades and additional paid regeneration are not included.

## Setup and credentials

Reuse an existing installation. For a Tripo-only setup, follow [INSTALL](../INSTALL.md#optional-tripo-cloud-provider): Python and Blender are needed, without local CUDA/TRELLIS weights.

Configure one of:

- Process environment variable `TRIPO_API_KEY`.
- A file containing only the key at `<runtime-root>/.secrets/tripo_api_key`.
- An alternate private file selected by absolute `TRIPO_API_KEY_FILE`.

Enter credentials through a local editor/secret manager, not chat, request JSON, command arguments, logs or shared MCP configuration. Ensure the CLI/MCP process can read the selected environment/file. `.env` is not automatically loaded.

```sh
uv run --no-sync python -m asset_auto.cli doctor
uv run --no-sync python -m asset_auto.cli tripo-balance
```

`doctor` checks local readiness. `tripo-balance` reads account credits without creating a generation. Without credentials, complete local validation and report live tests as unfinished.

## Inputs and cost estimates

| Item | Adapter contract |
| --- | --- |
| Model | `v3.1-20260211`, supported/default |
| Single image | `image`: local PNG/JPG/JPEG |
| Multiview | `views`: required `front` plus at least one of `left`, `back`, `right` |
| Upload | At most 20 MB per image; no WebP |
| Output options | Standard geometry, textures and PBR; original-image texture alignment |
| Seed | Request `seed` is used for model and texture seeds |
| Estimate | 30 credits per standard single-image or multiview generation |
| Guard | Optional integer `tripo.max_credits`, 1–100000, default 100 |

The 30-credit estimate was checked on **2026-09-12** and can change with service/model pricing. The guard blocks locally estimated over-budget submissions; it is **not a server-enforced spending cap, guaranteed charge or account-wide budget**. See [official pricing](https://developers.tripo3d.ai/en/pricing).

Views must depict the same object/design/colors/proportions as separate named images. A collage is not multiple input views; do not duplicate images to fill missing directions. Adapter limits follow the referenced official [upload](https://developers.tripo3d.ai/en/docs/files), [single-image](https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard) and [multiview](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/standard) interfaces.

## Requests

> `$3d-assets` Use Tripo3D with these front/back chest images and inspect the model renders.

Save `.work/tripo.json`, replacing the image path:

```json
{
  "asset_id": "chest-tripo",
  "provider": "tripo",
  "image": "/absolute/path/chest.png",
  "prompt": "A 75 cm wooden treasure chest",
  "triangle_budget": 12000,
  "target_height": 0.75,
  "seed": 42
}
```

For multiview, use `views` instead of `image`; front/back alone is sufficient:

```json
{
  "asset_id": "chest-tripo-multiview",
  "provider": "tripo",
  "views": {
    "front": "/absolute/path/chest-front.png",
    "back": "/absolute/path/chest-back.png"
  },
  "triangle_budget": 12000,
  "target_height": 0.75,
  "seed": 42
}
```

Both examples use default model/guard settings. If the user supplies a smaller cap, include it, such as `tripo: {"max_credits": 20}`. Below-estimate budgets reject submission and must not be silently increased.

`image` and `views` are mutually exclusive. `prompt` records intent/provenance, not image generation or text-to-model. TRELLIS `resolution`/`atlas` are not Tripo quality controls. `triangle_budget` applies to local Blender processing; review silhouette and texture after reduction.

## Plan, submit and review

```sh
uv run --no-sync python -m asset_auto.cli tripo-plan .work/tripo.json
uv run --no-sync python -m asset_auto.cli tripo-balance
uv run --no-sync python -m asset_auto.cli generate .work/tripo.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`tripo-plan` checks local inputs/model/estimate without uploads or API calls. The agent checks plan/balance internally and proceeds within authorized scope. Do not stop to request `max_credits` or repeated approval for the same standard request.

Poll the returned job through completion instead of resubmitting a slow request. Then inspect measurements and five actual PNG views following the [quick start](../QUICKSTART.en.md#4-inspect-the-model), and record observations with `review`. API availability does not establish superior quality or speed.

## Interruption and recovery

`tripo.json` records the remote task, progress and provenance. Remote work may continue after a local worker stops. Incomplete revisions are absent from the library; query `job JOB_ID`. Saved `recovery.asset_id`/`revision` identifies the child even after failure/interruption and is also exposed by MCP `asset_job_status` and synchronous errors. That location alone does not prove a paid submission occurred; resume requires a recorded task ID.

For an incomplete revision with a **known task ID**:

```sh
uv run --no-sync python -m asset_auto.cli resume-tripo ASSET_ID REVISION --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

Resume polls the existing task, downloads and processes its result without creating another paid task. Completed revisions are immutable; static `edit` or broader `blender-edit` creates a new local revision without paid regeneration.

If a submission response was lost and task creation is unknown, do not automatically retry POST. Reconcile against the vendor dashboard/charges first. Repeated `generate` calls without a known task can duplicate charges. Resume does not turn a failed/canceled remote task into success; another generation requires a separate spending decision. See official [task query](https://developers.tripo3d.ai/en/docs/task-query) and [account](https://developers.tripo3d.ai/en/docs/account) references.

## Rigging, animation and segmentation

General `process` defaults to local. For explicitly selected Tripo processing, save `.work/tripo-rig.json`:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "rig",
  "provider": "tripo"
}
```

```sh
uv run --no-sync python -m asset_auto.cli process-plan .work/tripo-rig.json
uv run --no-sync python -m asset_auto.cli process .work/tripo-rig.json --async
```

Legacy `tripo-process-plan`/`tripo-process` remain explicit Tripo aliases and do not convert local requests to paid work. Processing uses top-level optional `max_credits`, default 100. Respect smaller user limits without repeated approval for the selected stage.

| Operation | Supported behavior | Estimate |
| --- | --- | --- |
| `rig` | Free suitability check, then `biped`, `v1.0-20240301` | 25 credits |
| `animate` | Runtime-managed Tripo rig/animate parent; one `idle`, `walk` or `run` | 10 credits |
| `segment` | `v2.0-20260430` beta; simple/balanced/detailed granularity | 40 credits |

Rigging/segmentation use an exact completed static parent. Segmentation uploads the current GLB. Rigging uploads a geometry/material-preserving copy rotated from its observed input front to provider +X. `rig_forward_axis` specifies the actual GLB front (`+x`, `-x`, `+z`, `-z`; default `+z`). Record both hashes and restore orientation with a common mesh/skin parent transform. This reflects the observed zombie rig check changing from rejection to acceptance after a +90° Y rotation alone.

Animation inherits its parent's `rig_task_id` and orientation. Unlike local motion, it needs that remote rig record. One rig plus animation is estimated at 35 credits; rig, animation and segmentation once each total 75. Remaining guard capacity is not authorization for more variants/retries.

The paid adapter returns one requested clip. Merge compatible output locally with existing clips for final delivery. Local authoring/presets need no remote rig task. Tripo segmentation does not accept GeoSAM2 context/points. Inspect individual output parts before renaming; see [common processing](CHARACTERS.en.md). Official references: [rig check](https://developers.tripo3d.ai/en/docs/animations-rig-check), [rigging](https://developers.tripo3d.ai/en/docs/animations-rig), [animation](https://developers.tripo3d.ai/en/docs/animations-retarget), [segmentation](https://developers.tripo3d.ai/en/docs/mesh-segment).

Resume an incomplete child with `resume-process ASSET_ID REVISION --async` or `resume-tripo-process`. If only a free check finished, the originally requested paid stage may be submitted for the first time; known paid tasks are not duplicated. Reconcile unknown submissions. MCP tools are `tripo_process_plan`, `process_tripo_asset` and `resume_tripo_processing`.

## Recorded validation

Mock API tests and maintenance smoke checks using Blender 4.5.13/Godot 4.7.2 passed. They check shared processing, not live API success, and do not make Godot mandatory per asset.

One live single-image zombie generation completed upload → remote task → download → Blender, using 30 credits. Separate live processing results were:

- Segmentation: 40 credits, 13 regions and 18,984 triangles, inspected from five overview views plus thirteen part views and renamed in a new revision. Fused arm/clothing and boot/leg areas and open cuts remained; these were not thirteen finished watertight parts.
- Rigging: 25 credits, 41 bones, one skin and no unweighted vertices. Front orientation, materials, one-meter height and static appearance passed the recorded review.
- Walking: 10 credits, a 1.875-second output clip. Feet in the remote source penetrated the floor by about 0.32–0.35 m; ground-walking quality failed despite API completion.

Processing totaled 75 credits; free checks cost zero. Actual reviews are in local `review.json`, separate from initial pending inspection snapshots. Live `idle`/`run`, actual multiview generation and quality/speed comparisons against TRELLIS remain untested. Report mocks, remote completion and visual quality separately; requested live test modes are exercised once each within scope.
