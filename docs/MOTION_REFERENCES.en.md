# Designing motion with images and generated video

[한국어](MOTION_REFERENCES.md) | **English**

For complex or creative animation, choose image and temporal references during initial design. Image tools such as ImageGen clarify key poses and appearance; existing motion, recorded footage or generated video can clarify transitions, rhythm and contact events. Do not reserve video for repeated failures. Reuse sufficient inspected material; new images and videos are not mandatory for every motion.

This guide connects reference work to LLM-directed Blender authoring. The runtime does not extract skeletons automatically from video or accept video as Kimodo input. Default TRELLIS.2 mesh generation and explicit Kimodo/Tripo selection remain unchanged.

## Turn references into actual edits

1. **Define the expression to retain per clip.** Alongside playback, travel and contact conditions, select observable targets from the motion's defining extreme poses/silhouettes, important part trajectories, torso/limb or connected-part lead and follow, and acceleration/deceleration. Preparation/action/recovery labels alone are insufficient. Preserve the amplitude and rhythm of broad gestures and the restraint of subtle idle motion; do not enlarge every clip.
2. **Prepare a consistent source image.** Reuse supplied material, inspected pose images or a render of the actual target model. When new poses lack sufficient references, create per-clip material with ImageGen or another available image tool during initial design. Show necessary limbs/equipment and room for movement; inspect source defects first.
3. **Use video for relevant temporal questions.** Generate one clip or connected interval with a fixed camera, readable background and continuous action at the intended speed. If dividing a clip into intervals, identify shared events and inspect boundaries. Do not blindly apply a video skill's cinematic camera/cut defaults to motion studies.
4. **Separate accepted and rejected observations.** Inspect progression and neighboring event frames with timestamps. Look for side swaps, disappearance/duplication, shape drift, occluded contacts, cropped equipment and excessive holds. Distinguish intended exaggeration from shape errors, impossible poses and unknown depth; record exclusions and reasons. Check actual periods and multiple-cycle boundaries for loops. Smooth video alone cannot approve physics, grips or looping.
5. **Implement the adopted expression in Blender.** Interpret it for target proportions, equipment and gameplay purpose, but test target poses and paths on the actual rig and use [staged diagnosis](QUALITY.en.md#staged-rig-and-motion-diagnosis) to locate differences. Choose timing-only edits when the request is limited to timing or the adopted poses/trajectories are already satisfied; do not relabel missing required expression as a completed timing study. Record the actual edit scope and keep skeleton, equipment, contact constraints, corrective morphs and usage-event times coordinated.

Depth and opposite sides unseen in a video remain unverified. Separately generated front/side videos are not necessarily the same 3D action. Review the final model's [matching critical states from multiple directions](QUALITY.en.md#staged-rig-and-motion-diagnosis), transitions and playback. Generated reference appearance is not delivery evidence.

## Compare reference and final motion

Select events that reveal the adopted expression and **compare the reference beside final-GLB renders**. Choose relevant moments such as preparation, maximum extension, impact/release and recovery, plus trajectories between them. Match viewing direction and subject size in the frame where possible; do not choose cameras or frames that hide differences. Leave comparisons obscured by camera motion, perspective or occlusion unresolved, and inspect depth/penetration from complementary target-model angles.

Record event correspondence between reference and target times. If duration or speed changes, state the intended time mapping and remaining differences; normalized progress alone is insufficient. Compare transitions, speed and rhythm using playback or render sequences that preserve original timing, keeping each interval's actual duration visible even when aligning events. Record achieved expression and observed gaps, then use [repair, regression review and stopping conditions](QUALITY.en.md#repair-and-stopping-conditions).

## Grok Build headless use

Grok is an optional external reference tool, not a required runtime dependency. Check the chosen executable's version and `grok --help`, then verify that `image_to_video` is actually exposed in that session. Installed skill text does not establish tool or login availability. Work within the connected account's permissions and the authorized task/cost scope without repeatedly reconfirming the same authorized work. Source images are sent to the selected video service; leave authentication with Grok and keep keys out of requests and Git.

The locally observed skills are named `imagine` and `game-animation-frames`. Reading their advertised `SKILL.md` files worked without a dedicated skill-loading tool. Do not hard-code one computer's skill paths or one CLI version's media arguments for other installations.

The prompt file should specify:

- The inspected source image's absolute path, one motion's targets/observation conditions and a duration the actual tool supports.
- One `image_to_video` submission and its result. Preserve identifiers and do not resubmit on failure or an unknown outcome.
- No other generation services, unrequested variants, installations or setting changes outside the task scope.
- Report actual returned paths/status. The caller can save metadata; do not make a Grok file-write step necessary for successful media delivery.

After checking the installed CLI's options, adapt this headless example with real absolute paths:

```sh
grok --help
grok --cwd "/absolute/runtime/.work/motion-reference" --prompt-file "/absolute/runtime/.work/motion-reference/request.md" --output-format streaming-json --tools read_file,image_to_video --allow read_file --allow image_to_video --permission-mode dontAsk --no-subagents --max-turns 4 > "/absolute/runtime/.work/motion-reference/events.jsonl"
```

`max-turns` bounds the conversation, not video-call count or spending. Check the requested scope against actual events. When headless exposes the capability, an interactive session or new MCP server is unnecessary. Consider a separate adapter only for a demonstrated capability gap or shared client interface need. This command invokes Grok CLI; it is not a new `asset_auto` provider or MCP method.

## Preserve outputs and inspect frames

Distinguish session completion from media-tool completion. Inspect the actual `image_to_video` call, completion and returned path in `streaming-json`. **Do not regenerate a completed video because a later metadata write failed.** Verify that the returned file exists and decodes, then copy it into local work with its SHA256, source image/prompt and session/job identifiers. Reconcile unknown submissions before retrying.

When available, FFprobe/FFmpeg can read actual duration, frame rate and timestamps and extract review frames. These examples read an existing video; prepare the output directory first.

```sh
ffprobe -v error -select_streams v:0 -show_streams -show_format -show_frames -show_entries "frame=best_effort_timestamp_time:stream=width,height,avg_frame_rate,nb_frames:format=duration" -of json reference.mp4
ffmpeg -hide_banner -loglevel error -n -i reference.mp4 -an -fps_mode passthrough frames/%04d.png
```

Map PNG order to source timestamps. Inspect original neighboring frames around contacts, releases or fast changes that a sparse overview may miss. Panel counts or frame numbers do not define equal motion phases or playback speed. If playback was not observed, report ordered-frame inspection separately.

Record accepted/rejected intervals and reasons, source-to-target time mapping, actual edit scope and unknowns. After clip edits/additions, use [preservation comparison](BLENDER.en.md#editing-one-clip-and-comparing-preservation). When re-export changes other data, consider merging only compatible new clips into the original base model. Videos, frames, raw logs and character files stay local by default.

## Recorded scope

On 2026-09-15, Windows Grok Build 1.0.30 completed one headless `image_to_video` call using an actual character render for an archery reference. The request was six seconds; the result was 24 FPS, 145 frames and approximately 6.04 seconds. These observations are not output guarantees for every version.

Frame inspection supported using the aim/release/follow-through sequence, while cropped bow tips and fine shape drift ruled out treating it as an exact geometry/grip reference. A four-second clip adjusted the existing poses' aim/follow-through timing in Blender; the final GLB retained identical original data for all 24 earlier clips and the model.

Multiview, closeup and ordered-frame inspection of the exported result revealed a contact gap caused by a clamped morph range during export. Preserving the original used range, exporting again and rechecking under the same conditions resolved that defect. This frame review is distinct from directly observing continuous playback. It is one timing study, not a success-rate test across difficult actions, motion-capture accuracy evidence, proof of physical validity for all contacts or a quality comparison with other tools. It also does not establish reproduction of the reference's defining poses, trajectories or dynamism; those require the expression comparison above. Local edits did not require a new video for each correction.
