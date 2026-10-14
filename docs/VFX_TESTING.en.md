# Independent-session game-vfx testing

[한국어](VFX_TESTING.md) | **English**

Evaluate [game-vfx](../.agents/skills/game-vfx/SKILL.md) by making real effects in **a fresh LLM session separate from the skill-authoring conversation**. Use this guide when evaluating the skill; ordinary production requests do not require this report format.

## Request for the fresh session

For a version comparison, start with one model and one task in fresh isolated sessions under the old and proposed instructions. Hold the model/settings, identical English request, project/input snapshots, renderer, available authoring/review tools and time/token/compute/spending budgets fixed where controllable; record deviations. Pin the skill entrypoint and relevant linked dependencies by revision or content hash, record which references were actually read, and pin the prompt and playback/capture harness. Present paths or file modification times do not establish historical contents.

Replace brackets below with conditions actually supplied by the user; leave unknowns unspecified and preserve explicitly requested tool choices. Make quality, style and output requirements public, but withhold other candidates, known fixes, solution code, reference implementations and expected verdicts. Use this same English template in either guide.

```text
$game-vfx Create [effect name and gameplay use] in this project.

Project: [folder, known engine/renderer/version; unspecified if unknown]
Effect: [required onset/travel/contact/end behavior and interactions; list each effect]
References: [supplied images/video/existing-effect paths and desired features]
Usage: [known device, camera, scale, background and concurrent-use conditions]
Quality: [readable form, timing, intensity, style and required level of finish]
Output: [formats and location; requested integration/preview, if any]
Budget: [authorized time/tokens, local compute/storage, paid calls and spending limit]

Read the project and linked skill, then make the effect for these conditions.
Do not edit the skill/shared documentation or publish outputs during this test.
```

Do not add a detailed production brief, failure analysis, prescribed review counts or review/repair/preservation procedures, or remind the tester during production: the test checks whether those behaviors come from the skill itself. The evidence list below belongs to the authoring session's evaluation; do not inject it as an additional production prompt.

Let the session choose methods from explicit requirements and observed conditions. An unknown engine does not override the requested output format. Budget entries record both prior authorization and permissions the user gives for this test; paid calls and uploads must stay within that scope. Preserve outputs, caches, references and captures in a unique local folder separate from skill source, without overwriting earlier results.

## Evidence to return to the authoring session

The authoring session checks per-effect evidence in the production record and artifacts. Preserve the submission before any supervisor art feedback and keep subsequent assisted results distinct. Record environment assistance, including installation paths or delegated captures, separately from art direction; a supported run is not fully unassisted. Recover the first complete result only from existing history or unobtrusive capture; otherwise mark it unobserved rather than adding preservation instructions to the test prompt.

- Exact request, pinned instructions/dependencies and read references, model/settings, harness/tool/renderer versions, inputs/budgets and chosen authoring/playback path; deviations and interventions.
- Editable sources, delivery files, reproduction entrypoint/commands, checks performed and log locations.
- Captures/playback actually inspected, with event times, cameras and usage conditions. Reference artwork is not evidence of the final result.
- User preference, remaining visible defects, specific art-direction corrections still needed, observed repair tradeoffs, untested coverage and budget/tool blockers.

Keep visual preference, technical validity, actual listening and measured runtime performance as separate claims. Cue scheduling or waveforms do not establish sound quality; software rendering does not establish target-device performance. File/report counts and completed captures are supporting evidence, not artistic approval. Choose inspection coverage from the effect's risks rather than fixed review or image counts, and leave missing evidence unverified.

| Observed cause | Evidence to return |
| --- | --- |
| Missing or ambiguous guidance | The decision lacking guidance and its consequence |
| Existing guidance not applied | Relevant wording and how the actual action differed |
| Tool, environment or integration failure | Reproduction command, versions, error and smallest failing stage |

Mark mixed causes or insufficient evidence explicitly. The tester does not automatically edit the skill; the authoring session extracts reusable decisions from observed failures, not a prescribed answer or perfect-score rubric based on one sample. Follow the [VFX guide](VFX.en.md) for production and review criteria.

A promising first pair justifies a quiet sustained-effect probe and a narrow-edit probe for overreach, followed by repeats where outcomes remain uncertain. Check that the quiet effect retains its intended continuity and the small edit avoids unrelated redesign. One pair is directional evidence, not causal proof; cross-model claims need additional models. Evaluate playback/capture tooling changes separately before attributing gains to skill wording. Keep changes supported by useful improvement without loss of expression, correctness or scope; no detectable benefit is a reason to simplify or reconsider. These are proposed evaluation steps, not completed validation.

## 2026-10-07 independent hybrid-production test

At skill revision `2e48363`, an agent with no inherited conversation received a new ice-wolf projectile brief and a Three.js WebGL/Effekseer preview requirement. Previous examples, production code and supplemental review instructions were withheld. Results:

- It created a new reference image and TRELLIS.2 mesh, preserved the Blender-processed source, and combined Three.js ice materials/fracture with Effekseer supporting particles. Dedicated Blender sculpting/refinement was not exercised.
- From the requested multi-angle captures, the agent independently identified and repaired thin trails, a uniform impact ring and oversized fragments hiding the frost. It rechecked matching events/views, a bright background, occluders, three simultaneous casts and moments immediately before/after contact.
- Browser connection failures required the authoring session to capture the raw views requested by the agent. No solution or quality feedback was supplied; this environment assistance is distinct from a fully unassisted run.
- Actual WebGL loading, playback controls, seeking and restarting were checked. Active Effekseer nodes reached zero at the end and repeated runs returned matching counts; these observations do not prove performance or freedom from memory leaks.

**Verdict:** hybrid method selection and self-directed review/repair were demonstrated. Software WebGL snapshots did not validate normal-GPU performance or continuous real-time playback quality. Contact was authored for a flat floor; arbitrary terrain and other engines were out of scope. A separate code review raised a possible resource-lifetime issue on browser history-cache restoration, without completing reproduction. Generated artifacts and private execution records remain outside Git. Do not supply this case as an answer to a new evaluation agent.
