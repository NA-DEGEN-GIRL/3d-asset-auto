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
For multiple effects, author, review playback and repair each one.
Preserve editable sources and the requested outputs; inspect the actual result.
Finish with a brief report of artifact locations, versions and checks,
review evidence, unresolved defects and conditions not verified.
Do not edit the skill/shared documentation or publish outputs during this test.
```

Let the session choose methods from explicit requirements and observed conditions. An unknown engine does not override the requested output format. Budget entries record both prior authorization and permissions the user gives for this test; paid calls and uploads must stay within that scope. Preserve outputs, caches, references and captures in a unique local folder separate from skill source, without overwriting earlier results.

## Evidence to return to the authoring session

Keep a brief record for each effect. Distinguish created files and passed checks from meeting the requested quality.

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
