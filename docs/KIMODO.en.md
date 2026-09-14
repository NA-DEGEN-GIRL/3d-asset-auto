# Local text motion with Kimodo

[한국어](KIMODO.md) | **English**

[Kimodo](https://github.com/nv-tlabs/kimodo) `Kimodo-SOMA-RP-v1.1` generates human motion for an already rigged asset: **text → local inference → observed bone mapping in Blender → new GLB retaining existing clips → multiview review**. It is independent of the mesh generator and uses no Tripo API. New mesh generation still defaults to TRELLIS.2.

Kimodo does not automatically rig the character mesh. Prepare bones/skin weights through an existing rig or [SkinTokens](CHARACTERS.en.md#rigging) first.

**Install and run Kimodo only for explicitly selected Kimodo work.** Generic animation requests, installed weights or failed Blender edits do not select it. Otherwise use existing clips, [Blender authoring](BLENDER.en.md) or procedural `process` presets. Once selected, proceed within the request through setup, inference, application and review without repeated confirmation. Existing Kimodo clips can be corrected in Blender without rerunning inference.

## Install when needed

The setup requires Linux or Windows WSL2, an NVIDIA CUDA GPU and a C++ compiler. The recorded upstream guidance estimates about 17 GB VRAM with the text encoder. This adapter runs both model and encoder on the same GPU without automatic CPU/remote-encoder fallback, in an environment separate from the main `.venv`.

```sh
uv run --no-sync python scripts/bootstrap_kimodo.py
uv run --no-sync python -m asset_auto.cli doctor
```

Windows defaults to WSL `Ubuntu-24.04`; change it with `--wsl-distribution`. The selected Linux environment needs `uv` and `g++`. Pinned sources are built into a wheel in a Linux temporary directory to avoid build issues with `#` in the checkout path. Existing project files and system Python are preserved.

The encoder uses LLM2Vec based on [Meta-Llama-3-8B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct). Use an authorized Hugging Face read token, stored alone in `<runtime-root>/.secrets/hf_token`, or existing HF login/`HF_TOKEN`. Account access requests and terms are handled on Hugging Face. Keep tokens out of chat, requests, logs and Git. After download, inference uses pinned local files without searching for remote encoder services.

Account approval and token permission are separate. For fine-grained-token 403 errors mentioning public gated repositories, enable **Read access to contents of all public gated repos you can access** in [token settings](https://huggingface.co/settings/tokens). Editing an existing token's permissions does not require copying it again. The installer distinguishes access failures from connectivity problems, continues other downloads and explains how to rerun.

`--skip-models` prepares only the environment. `environment_ready`/CUDA checks do not prove complete weights or successful inference. `doctor.animation.text_to_motion.available` requires downloaded models. Resolve 401/403 access and rerun the same setup command; completed downloads are reused.

Source/model revisions are pinned in [kimodo_runtime.py](../src/asset_auto/kimodo_runtime.py), setup in [bootstrap_kimodo.py](../scripts/bootstrap_kimodo.py), and dependency resolution in [requirements-linux.lock](../scripts/kimodo/requirements-linux.lock). `.runtime/installed/kimodo.json` records file hashes/sizes and environment metadata. Code, weights and the Llama-based encoder have their respective terms; weights are not redistributed here.

## Apply to an existing rig

Inspect actual joint positions, hierarchy and facing direction first. `bone_map` keys are **SOMA roles** and values are **actual target Blender bone names**. This is a format example, not a mapping to copy blindly onto another rig:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_RIGGED_REVISION",
  "prompt": "A person stands and waves hello with their right hand.",
  "clip_name": "wave_hello",
  "duration_seconds": 4,
  "seed": 42,
  "diffusion_steps": 100,
  "forward_axis": "-y",
  "in_place": false,
  "bone_map": {
    "Hips": "pelvis", "Chest": "chest", "Head": "head",
    "LeftArm": "left_upper_arm", "LeftForeArm": "left_forearm", "LeftHand": "left_hand",
    "RightArm": "right_upper_arm", "RightForeArm": "right_forearm", "RightHand": "right_hand",
    "LeftLeg": "left_thigh", "LeftShin": "left_shin", "LeftFoot": "left_foot",
    "RightLeg": "right_thigh", "RightShin": "right_shin", "RightFoot": "right_foot"
  }
}
```

Save as `.work/motion.json`:

```sh
uv run --no-sync python -m asset_auto.cli text-motion-plan .work/motion.json
uv run --no-sync python -m asset_auto.cli text-motion .work/motion.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`text-motion-plan` checks source hashes, readiness, required mapping/hierarchy, preserved clips and unmapped bones without inference or paid calls. MCP exposes `text_motion_plan`, `generate_text_motion` and `resume_text_motion`; generation/resume return jobs. From another project, use the [skill wrapper](../.agents/skills/3d-assets/references/runtime.md).

The input is a completed revision with one humanoid armature and valid skin weights. The 15 example SOMA roles are required; add observed spine/neck/shoulder/toe roles as appropriate. Duplicate target bones, missing/reversed hierarchies and existing clip-name conflicts are rejected. Target application expects positive uniform armature scale and standard inherited transforms; resolve/bake active constraints first.

`forward_axis` is the model's facing direction in **Blender Z-up world coordinates**: default `-y`, or `+y`, `+x`, `-x`. It differs from `process`'s GLB Y-up `rig_forward_axis`. Duration is 2–10 seconds, seed 0–2147483647, diffusion steps 10–500. Motion is converted to the existing scene timebase to preserve old clip speed. The new duration is rounded to the nearest scene frame while retaining endpoint poses; the at-most-half-frame difference is recorded in `retarget-map.json`.

`in_place: true` removes horizontal root travel only, retaining vertical travel/rotation. It does not fix contacts, synthesize a proper in-place gait or make a seamless loop. Record playback/travel intent through [usage metadata](QUALITY.en.md).

## Apply, review and recover

The adapter maps SOMA global rotations to the target rest pose/hierarchy and scales travel by leg-length ratio. Unmapped fingers/end bones receive no separate motion. Exporting an internal 30-joint SOMA representation to 77 joints does not prove learned or verified detailed finger performance. Target proportions, penetration, sliding, tool contacts and loops require correction. This is not a universal IK solver or motion approval system.

For the next requested motion, use the preceding result as parent and a new `clip_name`, accumulating named clips in **one final GLB**. Names are not silently overwritten. Use `blender-edit` for intended changes and `merge-animations` for compatible separate clips. Follow [per-clip completion](QUALITY.en.md#complete-each-requested-clip); shared pose sheets or a few successful generations cannot approve the entire set.

`text-motion` keeps the Blender-applied result in `retargeted.glb` and **merges only the new clip into the original GLB**. Existing sampler data is not resampled when the Blend and original GLB have different frame rates. `animation-merge.json` records preservation/hashes and final inspection/renders use the merged file. The same selected-clip merge can retain other data after compatible local correction.

After generation perform **target application → multiview/playback review → needed Blender corrections → final-GLB recheck**. Use [staged diagnosis](QUALITY.en.md#staged-rig-and-motion-diagnosis) to compare source motion, target skeleton, skin, equipment and export. When the source meaning is correct and application caused the defect, retain inference and repair the responsible mapping/rig/weights/contact/timing. Decide on new inference from source defects and the task budget.

Use [motion references](QUALITY.en.md#using-motion-references) when targets are unclear or correction repeatedly fails. The adapter accepts text, not pose-sheet/video inputs or automatic motion extraction. References inform prompts and Blender decisions.

Corrections create new revisions. Set `preserve_animations: false` only for intended existing-clip changes, preserve other actions in the script and compare output data. Merge compatible corrected clips with explicit `on_conflict: "replace"` only for selected names. If rig/weights changed, keep the corrected model as the final base and review affected earlier motion. See [Blender contracts](BLENDER.en.md).

Three default PNGs are a single-camera overview. `assess` defaults to 24 total front/right/back images **per call**; split clips/calls when necessary. Inspect the same important moments from complementary angles, close-ups and actual transitions/playback. Stop when criteria are supported; diagnose/repair within the real task budget or report unresolved work. Inference/export success is not visual approval.

Resume the recorded **incomplete child**, not a duplicate request:

```sh
uv run --no-sync python -m asset_auto.cli resume-text-motion ASSET_ID CHILD_REVISION --async
```

`motion-request.json` binds parent GLB/Blend, scripts, model pins and request hashes. Completed `kimodo-inference.json` verifies `motion.npz`, `motion.bvh` and `motion-data.json` for reuse. Failures after `authored.blend` resume export/render without rerunning the script. Incomplete inference may rerun; completed data or changed snapshots are not silently overwritten. Preserve original generation separately from Kimodo `local_processing`.

## Maintenance and recorded validation

```sh
uv run --no-sync pytest -q tests/test_text_motion.py
uv run --no-sync python scripts/smoke_text_motion.py
uv run --no-sync python scripts/smoke_assessment.py
```

The first uses mock requests/recovery. The others use real Blender with synthetic fixtures for rest pose, world orientation, preservation, recovery and multiview budgets. They **do not prove learned text inference or real-character visual quality**. Installation acceptance needs a separate small authorized text request and review of its output.

Optional `uv run --no-sync python scripts/smoke_kimodo_runtime.py` checks CUDA inference, MotionCorrection and NPZ/BVH/JSON outputs with public weights, without the text encoder. It writes local evidence with `text_conditioning_tested: false` and is not a substitute for the requested text-conditioned task.

The recorded 2026-09-14 RTX 5090 test generated a real four-second/120-sample right-hand wave with the left arm lowered. The measured runtime was about 114 seconds including encoder loading, excluding initial Python imports and Blender application/renders. Separate checks matched all 448 weights in each MNTP/supervised adapter to their checkpoints and verified different finite embeddings for different text.

Applying it to an existing 46-bone SkinTokens character revealed hand/head interference and about 8.7 cm floor penetration. Blender revisions retained the inferred source while correcting the target body/height. A Blend/GLB FPS mismatch initially resampled old walking data; selected-clip merging fixed preservation, with all four original sampler datasets identical in the final GLB.

The final candidate was inspected at eight moments × four directions (32 images), plus ten close-ups. At 60 Hz, minimum mesh Z was about +2.0–2.85 mm. **Hand/head contact and severe arm creasing remained after two local correction rounds, so visual review was recorded as failed.** Further rig/weight/contact work is needed. Continuous playback, precise collision, sliding and engine use of that clip remain untested.
