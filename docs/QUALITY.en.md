# Purpose-based quality and assessment

[한국어](QUALITY.md) | **English**

Before authoring, define a few **observable acceptance criteria** for the request's core function and appearance. Specify what should be visible or absent at relevant distances, angles and states instead of only saying “natural.” Infer reasonable defaults from the request/project/model and record assumptions. Do not impose one anatomical, topology or motion checklist on every asset.

Use `features` to describe **representation → intended behavior → operating range/acceptance → limitations**. Surfaces, deformable meshes, rigid assemblies and skeletons are different choices. Similar rest appearances can behave differently at range limits or around other parts. Choose checks for the actual representation and use.

A narrow static edit may need only brief criteria and relevant renders. For repeatable measurements or delivery metadata, prepare a spec under `.work/` and optionally run `assess` on the exact completed revision. No engine or web app is required.

## Using motion references

For complex, unfamiliar, unclear or repeatedly failing motion, clarify targets with images/video before further correction. Reuse supplied references or inspected existing motion. When a pose sheet helps, use an available image-generation tool. A simple well-defined edit can reuse existing material; reference work stays within the task budget.

Extract relevant **phases, key poses, support/contact onset and release, and movement directions**. Briefly record source paths/URLs, generated status, useful panels/times and the associated clip/event. Adapt targets to the asset's proportions, range, equipment and style. Build the poses on the actual rig and turn observed reference/render differences into concrete corrections. If the pose matches but the surface collapses, diagnose the deformation stage.

Inspect generated sheets for structural/anatomical plausibility, left/right identity and consistent body/equipment/contact relationships. Repair or reject impossible/inconsistent panels. Do not treat occluded depth or perspective as known 3D geometry; seek other views or real motion and record uncertainty. Generated images are design hypotheses, not ground truth or renders of the delivered asset.

Different panel numbers do not prove different phases. Repeated poses or swapped limbs/supports must not be counted as progression or valid alternation. Repeated settled/held poses can be intentional but must be distinguished from motion. More panels or colored labels alone do not establish consistency. If sequencing/contact/timing cannot be resolved, or contradictions persist after a targeted correction, switch to frames from inspectable existing motion or real video instead of indefinitely expanding the same sheet. Existing Kimodo sources can help, but new Kimodo installation/inference still requires explicit selection. Inspect alternative references too, recording accepted/excluded portions and remaining limits.

Still-image order or spacing does not verify speed, rhythm or transitions. Check the timing of video references, then review the target at intended playback speed or with a time-preserving render sequence. Recheck corresponding events and transitions in the final GLB. References support the agent's design and Blender decisions; automatic image/video-to-motion extraction is not implemented.

## Complete each requested clip

Track each requested clip's purpose/criteria, relevant phases/contact events, needed references, actual review evidence, defects and status. A few successful representative clips cannot approve the rest. Keep records concise and useful rather than prescribing a document size.

When generating references, default to **a pose sheet or reference set for each clip**. Several phases of one clip can share a sheet if poses and contacts remain readable. A sheet showing one or two poses from many unrelated motions is an overview; add separate material for missing phases/transitions. Split overcrowded sheets and add angles/close-ups for hidden relationships. Do not force every motion into a universal image/panel count or compress a large task into one or two images.

Reuse verified shared appearance, equipment and rest-pose information. Do not assume it covers each motion's unique range, contacts or transitions. Simple clear edits outside the reference-use conditions do not require new images. Sufficiency means the clip can be concretely designed and compared, not that a picture quota was met.

Work per clip or small related group through **references/targets → authoring → multiview/playback review → repair → new export and recheck**. Bulk drafts can establish shared style/rig behavior, but are not completed clips. If one clip stalls, preserve its diagnosis and remaining work while progressing independent clips. Shared rig/weight/constraint changes require rechecking affected earlier clips. Compare all requested final-GLB data against the evidence; a complete name inventory alone does not approve quality.

Scale effort and repair budgets with clip count, complexity and observation needs. Do not reduce per-clip review to fit an invented task-wide picture/call cap. Keep completed, active and unstarted work visible when splitting execution, and continue through the requested set. Respect actual user time/cost limits and report affected clips if genuinely unresolved; a self-imposed tiny budget is not a reason to silently omit the rest. Reference-image and result-render budgets are distinct; additional paid work stays within existing authorization.

## Inspect according to purpose

Review proportions, silhouette and readability at the normal viewing scale. Add close-ups when that view cannot settle an important criterion or reveals a suspected defect. Change angles for occlusion and lighting/material display for diagnosis. Render a closer/higher-resolution view when enlarging an overview lacks detail; also recheck the whole model after a local correction.

| Quality driver | Relevant evidence |
| --- | --- |
| Interacting parts | Inspect connected structure through the contact region: continuity, orientation, pivots, surface wrapping/fitting and useful range. Check the whole moving equipment/assembly against nearby body/clothing/parts. Matching anchors or adding physics/colliders does not prove contact or function. |
| Geometry, surface and material | Distinguish geometry, normal and material defects: unintended holes, dents, noise, shading problems and seams. Preserve intended openings, thin surfaces, UV splits and style instead of blanket welding/smoothing. |
| Change over time | Inspect transitions, range limits and contact onset/release as well as key poses. Check intended-speed playback when timing matters. Inspect several loop cycles for pops, stalls and unwanted speed changes, and support-point sliding for locomotion. Endpoints and isolated poses do not prove the complete motion. |

Inspect the **final GLB**. A correct source Blend does not prove export preserved deformation/materials/clips. Critical PNGs support pose comparison; playback or time-preserving sequences support transition/rhythm review. Disclose unobserved playback instead of approving it. A custom web app is not mandatory.

For processing-induced surface damage, compare generation, cleanup, rigging and export using [finishing diagnosis](FINISHING.en.md). Separate UV/normal splits, real holes and isolated components.

Inspect **the same important moment from complementary angles**. Include an opposite/rear view when deformation/contact is hidden. Many frames from one camera or five views of a resting pose cannot approve motion. Scope narrow edits appropriately while recording unseen states/directions.

## Staged rig and motion diagnosis

Before complex motion on a new, changed or unverified rig, independently probe required joint chains. Separate bending and twisting from rest to examine axes, bending direction and actual surface deformation. Matching endpoints or angle clamps cannot excuse flipped joints or severe folds. Reuse evidence only for unchanged rig/mesh/weights/constraints and relevant operating ranges.

For organic characters, consider species, proportions, style and intended range when reviewing joint connections, volume and folds. Separate bone/flesh layers or muscle simulation are not universally required. When bone motion is correct but the surface collapses/twists, choose weights, joint geometry or corrective shapes according to cause, then check neighboring and other used poses. Distinguish intentional stylization from unwanted volume loss.

Blender's [Armature Preserve Volume](https://docs.blender.org/manual/en/latest/modeling/modifiers/deform/armature.html) is one option for joint-related volume loss. Verify export support for settings, corrective shapes and drivers, then compare the same poses/transitions in the final GLB.

Locate the **first failing stage and compare its preceding stage**, aligning units, orientation, rest pose and event times. Select the stages present and relevant to the task; unavailable intermediate evidence leaves the cause uncertain.

| Stage | Diagnostic question |
| --- | --- |
| Source motion and source skeleton | Was the requested motion, timing or travel already wrong before target application? |
| Motion on the target skeleton | Do bone mapping, rest pose, axes, hierarchy, scale or constraints explain the difference? |
| Skeleton and deformed mesh | If bone movement is right, are binding, weights or deformation responsible? Separate geometry from shading defects. |
| Equipment/contact/constrained assembly | Compare matching states with/without equipment when useful. Record visibility and constraint state; inspect the full intended final assembly separately. |
| Source scene and final GLB | Reimport and compare poses, deformation, materials and clips. Repair export/interpolation/merge defects at that stage. |

Use copies or separate revisions for diagnostic poses and temporary equipment/constraint changes; do not mix them into delivery clips. Reuse intermediate data instead of repeatedly regenerating source motion for target skin/contact defects. `assess` does not automatically classify these causes.

## Motion meaning and contact events

For interactions, identify relevant preparation, action, recovery and contact onset/maintenance/release. Put actual events in `events` and required intervals/directions/results in `acceptance`. A release or launch should align the hand/object/constraint release with independent object movement; a grip constraint must not remain active afterward unintentionally. Event names/keyframes alone do not approve meaning or timing.

Review connected joints, surfaces and objects together through transitions. Choose phases for the intended behavior rather than imposing one weapon/character sequence universally.

## Repair and stopping conditions

For each observed defect, record the failed criterion, location/clip/time, revision, reproducible view/evidence path, observations and cause hypothesis. Follow **repair → new revision/export → recheck under the same revealing conditions**. If duration changes, align the same event. Check overall appearance and affected neighbors. A flattering new angle or a successful script is not proof of repair.

Recheck likely regressions and preserve data outside the edit: mesh, skin, material and existing clips. For example, penetration corrections may damage joint direction/volume; timing/interpolation changes may break contacts or loop boundaries. Identical names do not prove unchanged content/speed. Use hashes/data comparisons, or corresponding data and time-based results with justified tolerances when export representation changes.

Declare intended clip edits and use [preservation comparison](BLENDER.en.md#editing-one-clip-and-comparing-preservation). If resampling changes data, compare actual poses/deformation at matching seconds. Normalized progress alone can hide changed timing.

Numerical, visual, functional and engine-import evidence are separate. One cannot erase an observed failure in another. “Prototype” may describe an agreed detail level, not waive required behavior. Do not silently lower criteria to fit the result.

Plan repair effort around clip count/complexity, importance, scope and cost, respecting user constraints. Do not universalize one asset's tolerances, angle limits or iteration count. Finish when relevant criteria are supported. When progress stalls, reconsider the cause/method. If the remaining budget cannot support a justified repair or is exhausted, preserve the best revision and report incomplete work, conditions, impact, attempted changes and next needs. Local repair effort does not authorize additional paid generation; follow [Tripo spending scope](TRIPO.en.md).

## Request and commands

`AssessmentRequest` uses exact `asset_id`/`revision`, optional `usage` and selected `clips`. Omitted `usage` loads existing intent only when bound to the same GLB hash. Without intent, the runtime does not guess motion meaning and leaves clips unassessed. Explicit `usage` replaces the whole contract; read/merge existing content if preserving it.

Example format; adapt names, criteria and measurements to the asset:

```json
{
  "asset_id": "moving-device",
  "revision": "EXACT_COMPLETED_REVISION",
  "usage": {
    "purpose": "An interactive mechanical game prop",
    "assumptions": ["Used at the normal gameplay camera distance"],
    "features": [{
      "name": "moving_assembly",
      "representation": "Rigid parts under a common pivot",
      "intended_behavior": "Open and close within the defined range",
      "acceptance": ["Connections remain covered at the range limit"],
      "limitations": ["Elastic deformation is not represented"]
    }],
    "clips": {
      "open": {
        "purpose": "Open once and hold the final state",
        "playback": "hold",
        "motion": "none",
        "events": [{"name": "full_extension", "time_seconds": 0.75}],
        "acceptance": ["No interference with nearby parts at full extension"]
      },
      "cycle": {
        "purpose": "Continuous repetition",
        "playback": "loop",
        "rules": {
          "position_tolerance_m": 0.002,
          "rotation_tolerance_degrees": 1,
          "max_angular_velocity_jump_dps": 20,
          "max_still_seconds": 0.15
        }
      }
    }
  },
  "sample_rate": 30,
  "max_render_frames": 16
}
```

```sh
uv run --no-sync python -m asset_auto.cli assess .work/assessment.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

CLI and MCP `assess_asset(request)` share the pipeline. MCP `asset_usage(asset_id, revision)` reads intent/latest assessment. Static contracts (`clips: {}`) do not run Blender. Motion assessment reimports a copy of the final GLB without generation, paid calls or source re-export.

## Playback policies and measurement limits

`playback` is `unspecified`, `loop`, `once` or `hold`. `once` declares one-shot playback; `hold` declares retention of the final pose. Projects implement state transitions/blending. Loop endpoint checks apply only to loops. Set `max_still_seconds` only when holds are unwanted.

`motion` is `unspecified`, `in_place`, `root_motion` or `none`. Root motion requires an observed `root_target`. Reports identify `object:NAME`, `bone:RIG/BONE` or `morph:MESH/SHAPE`; roots support object/bone transforms only. Use actual inspected names.

Root-motion loop pose comparison removes the declared root's accumulated translation/rotation while checking scale preservation. Root displacement and average displacement speed are **parent-local**, not necessarily world/game speed under moving/scaled/rotated parents. `target_speed_mps` records intent, not automatic speed matching or foot-contact evidence. `root_target` with `max_root_drift_m` checks intermediate in-place drift even when the root returns to its start.

| Measurement | Meaning |
| --- | --- |
| Loop position/rotation/scale/morph difference | Start/end local values. Defaults: 1 mm, 1 degree, 0.001 scale/morph; adapt to purpose. |
| Boundary linear/angular velocity difference | One-sided differences in first/last intervals. Without `max_linear_velocity_jump_mps`/`max_angular_velocity_jump_dps`, measured but not judged. |
| Low-activity duration | Intervals where all local transform/morph rates are below thresholds; does not infer intentional holds or meaning. |
| Root drift/displacement | Selected root's local motion, not foot sliding or support stability. |

Activity thresholds are `still_position_speed_mps` (0.001), `still_rotation_speed_dps` (0.1), and `still_value_speed` (0.001). Defaults are not universal quality guarantees. Low-activity intervals spanning a loop boundary are joined. Tiny jitter passing an activity test does not establish useful motion.

Contacts/sliding need actual points, intervals, reference frames and relative motion. Center-of-mass checks require mass assumptions. Free-text acceptance and representation suitability are not automatically approved; the agent supplies relevant measurements, rendered evidence or requested integration evidence. No general collision/contact/style judge is provided.

## Critical moments and budgets

Sampling defaults to 30 Hz and at most 1,201 samples per clip. `sample_rate` is 2–120; `max_samples_per_clip` is 5–10,001. Select at most 16 clips per call. Exceeding the sample budget requests a changed request rather than silently reducing frequency. Sampling can miss fast changes between samples.

Set event times in seconds within the actual GLB clip timeline. Candidates include event neighborhoods, endpoints/neighbors, low-activity transitions and transform/morph extrema. Candidate reasons are recorded; an automatic extremum is not proof of a meaningful contact event. Significant changes relative to tolerances get priority; adjust tolerance or declare an event when smaller changes matter.

`render: false` performs measurements/candidate selection only. **Each `assess` call** shares a default total of 24 images (`max_render_frames`: 0–128) across selected clips, prioritizing events. This is not a task-wide cap or a reference-generation budget. Default `views` are `["front", "right", "back"]`; `left` and `perspective` are available. These are Blender world directions, so inspect the actual orientation/occlusion. Multiple directions are allocated together; 24 images can cover eight moments in three views. No extra static lighting-setup images are rendered.

If many clips leave important states uncovered, split calls using `clips` and budget each selected clip/group appropriately. Preserve the complete `usage.clips`; later calls on the same GLB can omit `usage`. Do not replace a complete contract by repeatedly submitting one-clip `usage` objects. Keep each `assessments/q.../report.json` and actually reviewed image paths in per-clip notes. `assessment.json` is replaced by the latest call, and `unassessed_clips` describes that call, not accumulated approval.

Candidate `views` contains actual PNG paths; `file` is the first-image compatibility field. Read `unrendered_views`, per-clip `view_counts`, `rendered_moments`, `unrendered_frames`, `unrendered_view_images`, and `unassessed_clips`. `rendered_frames` counts images, not distinct moments. Adjust selection/views/budget for missing important events. Uninspected PNGs remain `pending`/`untested`.

The normal three-frame preview uses one `perspective` camera and is marked `single_view_overview` in `animation-previews.json`. Use additional assessment or targeted multiview renders when needed. Narrow static edits do not require analysis of every clip.

## Delivery and traceability

- `usage.json`: purpose, representation, playback, criteria and final GLB SHA256. Deliver it with the GLB when relevant; it is repository metadata, not an automatically applied engine standard.
- `assessment.json`: latest assessment only; execution, numerical, visual, functional and integration results are separate.
- `assessments/q.../`: per-call request, input copy, report and PNG evidence. Failure preserves earlier completed assets/contracts.

Numerical `passed` means only the configured check passed. `untested` means missing criteria/evidence. Record actual coverage, findings and unreviewed scope using `review --notes`. This stores an agent judgment; it does not automate quality approval. Use `--result fail` when reviewed core criteria fail or evidence is insufficient. Do not record a pass without review. Unnecessary optional engine checks are not failure criteria. A new revision does not inherit approval.

Edits retain policies for remaining clip names and mark them for recheck. Merges transfer source usage with clip selection/renaming. Replacing a clip without source usage removes stale policy for that name. External GLB files alone do not establish usage intent. Update inherited policies/events when geometry, names or timing changes.
