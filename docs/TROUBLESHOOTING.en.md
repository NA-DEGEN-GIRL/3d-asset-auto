# Troubleshooting

[한국어](TROUBLESHOOTING.md) | **English**

Run commands from the installed runtime root. Start with:

```sh
uv run --no-sync python -m asset_auto.cli doctor
```

Core setup is TRELLIS, weights and Blender. Missing optional Godot/web components do not block generation or local PNG review. Missing TRELLIS/reference input blocks default new-mesh generation. Explicit Tripo can work without local GPU/weights, but needs credentials, credits and Blender. Do not silently switch provider or substitute procedural modeling.

## Failed to fetch or connection refused when selecting an asset

A cached asset list can remain visible after the server stops, while GLB requests fail. On Windows rerun `start-viewer.cmd` and refresh; on Linux keep the `sh start-viewer.sh` terminal running. The Windows launcher starts a background server, checks readiness and reuses the same checkout's server. It does not configure startup after reboot.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/api/capabilities'
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
```

Read the newest `.work/viewer/*.stderr.log` when unavailable. A different returned `root` indicates another checkout's server. Inspect its PID/command/purpose before stopping it. If the server responds but one model fails, check that revision's `asset.glb` and logs.

## Port already in use or stopping the server

The Windows launcher does not take a port from another application. Use a different port:

```sh
uv run --no-sync python -m asset_auto.cli serve --port 8766
```

This runs in the foreground. Keep the terminal open and visit the [alternate local viewer](http://127.0.0.1:8766/); stop with Ctrl+C.

Before stopping a hidden Windows viewer or updating its environment, identify `OwningProcess` with `Get-NetTCPConnection` and verify its command with `Get-CimInstance Win32_Process -Filter 'ProcessId = PID'`. Replace `PID` with the actual number, then use `Stop-Process -Id PID` only for that confirmed viewer. Do not terminate all Python processes.

## Missing web build or stale UI

```sh
npm --prefix web ci
npm --prefix web run build
```

Refresh the browser. Restart the server if it first started without `web/dist`. Refresh the library to see new assets. Fresh clones contain no generated models, so an empty library is expected.

## uv sync fails because an executable is in use on Windows

An active viewer/job may hold environment files. Stop only confirmed relevant processes, then run `uv sync --locked`. After setup, use `uv run --no-sync ...` for normal operations. Preserve `--extra mcp` when synchronizing an MCP-enabled environment.

## Missing tools or models

Install only missing components (`blender`, `godot`, `trellis`, `models`). `--only core`, or no scope flag, installs the default core:

```sh
uv run --no-sync python scripts/bootstrap.py --only blender
```

For existing installations, see [path configuration](../INSTALL.md#6-existing-tools-and-configuration). TRELLIS must be ready for default generation; Godot may be unavailable. Explicit Tripo-only setups do not require TRELLIS. File discovery is not successful execution.

## Missing reference or old procedural requests

Omitted provider now means `trellis`; provide a real `image` path. Combining an image with `procedural`/`import` is rejected. Use a procedural recipe only for an explicitly requested procedural task. Saved revisions include their provider, so edits of old assets are unaffected by this default.

## Download 403 or checksum mismatch

For anonymous GitHub rate limits, wait for recovery or use an already authorized installation `GITHUB_TOKEN`. Keep it out of logs/requests/Git. CI uses a read-only token for release metadata.

Do not disable checksum verification. Check source/network, then rerun the affected download. Valid caches are reused and failed `.part` downloads are rewritten. Do not delete model/asset directories to fix one download.

For Kimodo encoder 401/403 errors, see [account and token access](KIMODO.en.md#install-when-needed).

## Submitted job is absent from the library or interrupted

```sh
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

Read `.assets/jobs/JOB_ID/job.json`, `worker.log` and revision `trellis.log`/`blender.log`. `running` may mean waiting for the GPU lock. Do not submit a duplicate. A revision without a completed manifest is excluded from the library.

`interrupted` means the worker disappeared; it does not resume automatically. For TRELLIS, diagnose the logs before intentionally starting another job. For VRAM problems, inspect competing GPU work and start validation at resolution 512; no setting guarantees every GPU.

Tripo may continue remotely after a local interruption. Resume known tasks with `resume-tripo ASSET_ID REVISION --async`. With an unknown submission and no task ID, reconcile on the dashboard before another generation. See [recovery](TRIPO.en.md#interruption-and-recovery).

## Tripo credential, balance, budget or input errors

`tripo-plan SPEC` checks local inputs/estimates without a key. `tripo-balance` checks authentication/balance. Verify credential locations without printing secrets: `TRIPO_API_KEY`, default `.secrets/tripo_api_key`, or `TRIPO_API_KEY_FILE`.

The guard is optional, default 100; standard generation is estimated at 30. If an agent repeatedly asks for a guard or renewed approval for explicitly requested standard work, reload the current skill. Respect a smaller user limit. Do not automatically raise it, top up credits, switch provider or resubmit on low balance. Inputs are PNG/JPEG up to 20 MB each. `image` and `views` are mutually exclusive; multiview requires front plus another direction. See [input/cost rules](TRIPO.en.md#inputs-and-cost-estimates).

## Unknown part or rejected armature

Use `inspect ASSET_ID REVISION` for actual object names. One `Mesh_0` is not semantic separation. If needed, use local `prepare-segment`, agent-observed points and `process`, then rename inspected parts. Automatic labels or disconnected geometry are not proof of semantic meaning.

Import rigs with `asset_kind: "character"`, unrigged object/morph clips with `animated`, both under `provider: "import"`. Use `blender-edit` for rigged/animated parents. See [preservation boundaries](CHARACTERS.en.md#character-preservation-and-edit-boundaries).

## Rigging, motion or segmentation failures

Check the exact completed parent. Local rigging/segmentation need static parents; biped presets need a rig. Local animation accepts external rigs without remote IDs. Object/custom motion uses Blender scripts. Only explicitly selected Tripo animation needs a Tripo `rig_task_id`.

Install the [needed local backend](../INSTALL.md#local-postprocessing-on-demand), checking CUDA/WSL readiness. Installation failure does not justify a key request or paid fallback. An installation marker does not prove output quality.

The agent maps unknown bones from actual positions/hierarchy. Local presets need one armature, valid weights and positive uniform scale; walking/running need both thigh→shin→foot chains, while idle needs chest. Do not infer roles from numbers or invent replacement bones to hide a mismatch.

Segmentation context binds the exact source and twelve view hashes. Re-prepare changed inputs. The agent chooses actual pixel points; the user need not draw masks. Retain unclassified faces and report budget excess without automatic decimation. Successful inference with missing/misclassified parts is still a failed semantic review.

For a rejected Tripo rig check, inspect the actual front and `rig_forward_axis`; +Z is only a default. Provider +X conversion is specific to Tripo. Resume the saved incomplete processing child with `resume-process`; never automatically retry an unknown remote submission. See [processing recovery](CHARACTERS.en.md#records-and-recovery).

Budget excess is not rig failure: character processing preserves rigs without automatic reduction. Inspect materials, part names and joint deformation in actual renders. The shared viewer's static loader is not motion validation.

For floor penetration, compare inspection/previews and provider source. Local `local-motion.json` distinguishes final `ground_checks` from intermediate `generated_ground_checks` by artifact hashes. Examine IK limits and correction magnitude. The recorded Tripo zombie walk also penetrated in the remote source and failed visual gait review. The presence of a correction does not approve walking quality.

## Numerical checks pass but the asset looks wrong

Triangle count, file validity and engine load do not establish visual quality. Inspect holes, shading, silhouette and color; record actual defects and repair in a new revision:

```sh
uv run --no-sync python -m asset_auto.cli review ASSET_ID REVISION --result fail --notes "OBSERVATIONS"
```

Use actual IDs/findings. See [quality](QUALITY.en.md) and [surface diagnosis](FINISHING.en.md). After an individual motion edit, use [clip preservation comparison](BLENDER.en.md#editing-one-clip-and-comparing-preservation) to detect changes to other data.

## Skill missing or Runtime environment missing

Check that the personal skill link points to the checkout's `.agents/skills/3d-assets`. Copying only that folder breaks runtime-relative discovery. Update the link after moving the checkout. If `.venv` is missing, run `uv sync --locked` there.

The agent may need to rediscover the skill in a new session, or use its absolute `SKILL.md` path. If CLI/MCP libraries differ, compare `ASSET_AUTO_ROOT` and `doctor` output for both processes.
