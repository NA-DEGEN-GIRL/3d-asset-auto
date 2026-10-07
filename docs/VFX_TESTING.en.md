# Independent-session game-vfx testing

[한국어](VFX_TESTING.md) | **English**

Evaluate [game-vfx](../.agents/skills/game-vfx/SKILL.md) by making real effects in **a fresh LLM session separate from the skill-authoring conversation**. Use this guide when evaluating the skill; ordinary production requests do not require this report format.

## Request for the fresh session

Pin the skill version and prepare the actual project and references. Do not pass the authoring session's solution code, preferred answer or expected verdict to the tester. Replace brackets below with conditions actually supplied by the user; leave unknowns unspecified. Preserve any explicitly requested tool choice.

```text
$game-vfx Create [effect name and gameplay use] in this project.

Project: [folder, known engine/renderer/version; unspecified if unknown]
Effect: [required onset/travel/contact/end behavior and interactions; list each effect]
References: [supplied images/video/existing-effect paths and desired features]
Usage: [known device, camera, scale, background and concurrent-use conditions]
Quality: [readable form, timing, intensity and required level of finish]
Output: [formats and location; requested integration/preview, if any]
Budget: [authorized time, local compute/storage, paid calls and spending limit]

Read the project and linked skill, then make the effect for these conditions.
Do not edit the skill/shared documentation or publish outputs during this test.
```

Do not repeat review, repair or preservation procedures in this request or remind the tester separately during production: the test checks whether those behaviors come from the skill itself. Environment assistance such as installation paths and connection methods is allowed. If quality instructions have to be supplemented, record that intervention and distinguish the result before it. The evidence list below belongs to the authoring session's evaluation; do not inject it as an additional production prompt.

Let the session choose methods from explicit requirements and observed conditions. An unknown engine does not override the requested output format. Budget entries record both prior authorization and permissions the user gives for this test; paid calls and uploads must stay within that scope. Preserve outputs, caches, references and captures in a unique local folder separate from skill source, without overwriting earlier results.

## Evidence to return to the authoring session

The authoring session checks per-effect evidence in the production record and artifacts. Distinguish created files and passed checks from meeting the requested quality, and leave missing evidence unverified.

- Original request, skill version/checkout, actual tool/renderer versions and chosen authoring/playback path.
- Editable sources, delivery files, reproduction entrypoint/commands, checks performed and log locations.
- Captures/playback actually inspected, with event times, cameras and usage conditions. Reference artwork is not evidence of the final result.
- Observations against criteria, review after repairs, unresolved defects, untested coverage and budget/tool blockers.

| Observed cause | Evidence to return |
| --- | --- |
| Missing or ambiguous guidance | The decision lacking guidance and its consequence |
| Existing guidance not applied | Relevant wording and how the actual action differed |
| Tool, environment or integration failure | Reproduction command, versions, error and smallest failing stage |

Mark mixed causes or insufficient evidence explicitly. The tester reports evidence without automatically editing the skill. The authoring session extracts reusable decisions from observed failures. Do not turn one sample's constants or appearance into a prescribed answer or perfect-score rubric; when needed, check the revision in another fresh session with different effect/project conditions. Follow the [VFX guide](VFX.en.md) for production and review criteria.

## 2026-10-07 independent hybrid-production test

At skill revision `2e48363`, an agent with no inherited conversation received a new ice-wolf projectile brief and a Three.js WebGL/Effekseer preview requirement. Previous examples, production code and supplemental review instructions were withheld. Results:

- It created a new reference image and TRELLIS.2 mesh, preserved the Blender-processed source, and combined Three.js ice materials/fracture with Effekseer supporting particles. Dedicated Blender sculpting/refinement was not exercised.
- From the requested multi-angle captures, the agent independently identified and repaired thin trails, a uniform impact ring and oversized fragments hiding the frost. It rechecked matching events/views, a bright background, occluders, three simultaneous casts and moments immediately before/after contact.
- Browser connection failures required the authoring session to capture the raw views requested by the agent. No solution or quality feedback was supplied; this environment assistance is distinct from a fully unassisted run.
- Actual WebGL loading, playback controls, seeking and restarting were checked. Active Effekseer nodes reached zero at the end and repeated runs returned matching counts; these observations do not prove performance or freedom from memory leaks.

**Verdict:** hybrid method selection and self-directed review/repair were demonstrated. Software WebGL snapshots did not validate normal-GPU performance or continuous real-time playback quality. Contact was authored for a flat floor; arbitrary terrain and other engines were out of scope. A separate code review raised a possible resource-lifetime issue on browser history-cache restoration, without completing reproduction. Generated artifacts and private execution records remain outside Git. Do not supply this case as an answer to a new evaluation agent.
