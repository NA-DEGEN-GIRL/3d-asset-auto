# Private resource policy

[한국어](RESOURCES.md) | **English**

GPU selection and CPU budgets belong to the machine's operator. Keep the shared policy outside the repository so `3d-assets`, `game-vfx` and runtime workers use the same limits without publishing hardware identifiers or copying machine settings into asset requests. A user or operator can authorize a change; an agent must not remove a protected device, widen the CPU budget or enable a protected GPU just to get a blocked job running.

With no resource policy, the runtime retains its existing command arguments, environment and process affinity. A policy does not install a backend, select Kimodo/Tripo, reserve GPU memory or guarantee that inference fits in VRAM.

## Configuration and precedence

Effective settings resolve from highest to lowest priority:

1. `ASSET_AUTO_GPU`, `ASSET_AUTO_CPUS`, `ASSET_AUTO_THREADS` for their respective settings.
2. The private file selected by `ASSET_AUTO_RESOURCES_FILE`, or otherwise `$XDG_CONFIG_HOME/codex-skill-runtimes/resources.json`; when `XDG_CONFIG_HOME` is absent, `~/.config/codex-skill-runtimes/resources.json`.
3. The `resources` object in `<runtime-root>/asset-system.local.json`.
4. Existing automatic behavior.

Set these on the host where the worker executes. A caller's Windows/SSH/WSL configuration is not proof that a different host enforces it. Keep the private file and machine-specific local configuration out of Git; do not paste credentials, host addresses or real device UUIDs into reusable examples.

The policy uses `version: 1`. Omit settings that the operator has not selected; read the resolved plan before execution.

File layers merge by field, including named runtime overrides. The selected runtime then overrides shared fields; the three environment overrides above still take priority. `ASSET_AUTO_GPU` accepts `auto`, `cpu` or comma-separated full UUIDs, `ASSET_AUTO_CPUS` accepts the CPU range string and `ASSET_AUTO_THREADS` a positive integer.

| Setting | Meaning |
| --- | --- |
| `gpu` | `"auto"`, `"cpu"`, or a list of full NVIDIA GPU UUIDs; use UUIDs rather than unstable numeric indexes. |
| `protected_gpus` | Full UUIDs excluded from ordinary GPU selection. |
| `cpus` | Allowed logical CPU selection, expressed as ranges such as `"0-3"`. Choose a range available to the actual worker. |
| `threads` | Positive worker/thread-library budget. It is separate from CPU affinity. |
| `nice` | Linux niceness from -20 to 19. Application never decreases the process's existing numerical value, so it cannot raise scheduling priority. |
| `oom_score_adj` | Linux OOM selection adjustment from -1000 to 1000; this is not a RAM limit. |
| `max_parallel_blender` | Maximum simultaneous policy-managed Blender processes for the same user across sessions and checkouts. |
| `wait_timeout_seconds` | Positive maximum resource-wait duration, or `null` (default) to keep waiting for the selected resource. |
| `poll_interval_seconds` | Positive resource-wait polling interval; defaults to 2 seconds. |
| `runtimes` | Overrides for `trellis`, `kimodo`, `local_rig`, `local_parts` and `blender`: `gpu`, `threads`, `allow_protected`. |
| `runtimes.kimodo.text_encoder_device` | `"cuda"` (default) or `"cpu"`; the motion network still needs CUDA. |

This example is a template, not a runnable machine configuration. Replace both placeholder UUIDs with operator-selected full UUIDs, and choose CPUs/budgets available to the worker. The private file contains the object directly; `asset-system.local.json` nests it under `resources`.

```json
{
  "version": 1,
  "gpu": ["GPU-00000000-0000-0000-0000-000000000001"],
  "protected_gpus": ["GPU-00000000-0000-0000-0000-000000000002"],
  "cpus": "0-3",
  "threads": 4,
  "nice": 10,
  "oom_score_adj": 500,
  "max_parallel_blender": 1,
  "runtimes": {
    "blender": {"gpu": "cpu"},
    "kimodo": {"text_encoder_device": "cpu"}
  }
}
```

`allow_protected` is an explicit operator exception for the named runtime, not an automatic retry setting. If selection leaves no permitted GPU, stop with the policy error. Do not change the policy, choose another host or invoke a paid provider as an automatic workaround. Continue independent work that fits the authorized resources.

For CUDA workers, `gpu: "auto"` with protected GPUs requires an unambiguous inherited full-UUID selection; otherwise select the permitted UUIDs explicitly. The runtime does not guess a free device by index. OOM adjustment also never decreases its current numerical value: it cannot grant additional OOM protection. Read enforcement diagnostics when a requested value is retained unchanged.

An occupied permitted device is different from an invalid or missing device. For explicitly selected GPUs, wait for that selection and for a Blender concurrency slot; do not move to another GPU because one is busy. Keep the same submitted job and cancel it if waiting is no longer wanted. Invalid policy or a missing selected UUID fails immediately. These controls coordinate managed jobs and observed GPU work; they do not provide exclusive OS-level ownership of arbitrary GPU/CPU activity.

GPU UUID leases and Blender slots are shared across the same user's sessions/checkouts under `$XDG_CACHE_HOME/codex-skill-runtimes/locks`, or `~/.cache/codex-skill-runtimes/locks` by default. Waiting checks external CUDA compute processes, not every graphics workload, and does not kill or move them. An external process can start after a check; the queue is not strict FIFO or a security boundary.

Local `*.resources.json` records capture launch/wait evidence. Background jobs keep their job state `running` while `resource_progress.state` reports `waiting_resources`; this is not permission to submit a duplicate job.

## Check the actual execution path

From the runtime root:

```sh
uv run --no-sync python -m asset_auto.cli resources --runtime blender
uv run --no-sync python -m asset_auto.cli resources --runtime kimodo
uv run --no-sync python -m asset_auto.cli doctor
```

`resources` reports the resolved plan without starting inference. `doctor` includes resource-policy diagnostics. Inspect the source, selected/excluded devices and unsupported controls; a plan is not evidence that a model or render completed. From another project, keep the existing skill wrapper's execution routing and pass an explicit runtime root where required.

The skill wrapper's `runtime-status` includes a `resource_policy.check_argv` for its selected execution route. Status itself does not read the policy or import the runtime on a bridge client. Run that check to inspect the worker host's actual policy.

Native Linux workers can apply affinity, niceness and OOM adjustment. Windows can apply CUDA/thread environment settings, but those Linux OS controls are unsupported there and must be reported as such. Windows/WSL/SSH bridges must not claim automatic device enforcement: configure policy where the worker executes, or fail when an active policy cannot be enforced across that boundary.

CUDA-only backends reject `gpu: "cpu"` explicitly when they have no CPU implementation. This applies to TRELLIS, local learned rigging/parts and the Kimodo motion network; hiding GPUs does not turn them into CPU inference.

The normal TRELLIS generation command also sets its native `--threads` budget and selects logical `--gpu 0` after UUID filtering. A custom TRELLIS command through `resources --exec` receives the policy environment and Linux process limits; include the corresponding native `--threads`/`--gpu` arguments yourself. Library thread variables alone cannot control every application's internal thread pool.

## Blender and VFX

Use the resource-aware launcher for custom Blender authoring and simulation as well as pipeline work. Running `<blender>` directly bypasses the launcher's controls and concurrency limit. Keep new simulations and their resource provenance in local work folders.

```text
uv run --no-sync python -m asset_auto.cli resources --runtime blender --exec -- <absolute-blender> --background --python <absolute-script> -- <script-arguments>
```

`resources --runtime blender --shell-prefix` prints a guarded CLI prefix, including the resolved root and `--exec --`. On Windows it uses PowerShell's `&` and single-quoted arguments; on POSIX it uses shell quoting. Append the full executable and arguments using that shell's quoting rules. It is not a set of environment assignments and does not authorize bypassing the guarded launcher.

Mantaflow simulation is a CPU work path; budget CPU affinity and threads for the bake. Rendering is a separate step. `CUDA_VISIBLE_DEVICES` alone does not exclude a protected GPU from EEVEE/OpenGL: those APIs can select devices independently of CUDA. Use an enforced CPU/software-rendering path when GPU exclusion is required; do not approve GPU isolation from an environment mask alone. The guarded segmentation preparation path selects Cycles CPU and requests software OpenGL under an active GPU restriction; verify that the execution platform honors those settings.

Resource control is a cooperative launcher contract, not a sandbox for trusted Blender Python. Scripts must retain the selected renderer/device policy. Review actual renderer/device evidence separately from successful export or simulation.

## Kimodo encoder placement

Kimodo can keep its motion network on the selected CUDA GPU while placing the text encoder on CPU by an explicit policy choice. The default encoder remains on CUDA; there is no automatic CPU-encoder or remote-encoder fallback after a GPU error. This mixed placement is not full CPU Kimodo support.

Budget approximately 17 GiB VRAM for the full GPU path, or roughly 2 GiB for the motion network with the encoder on CPU, as planning estimates only. Explicit GPU selection checks the first visible device's total capacity against that encoder-mode threshold; it does not sum several GPUs or prove enough free memory. Model versions, sequence settings, CUDA allocations and other processes affect actual use. CPU encoder placement trades GPU memory for substantial host RAM and slower encoding; inspect the plan and measure the authorized workload. See [Kimodo setup and validation](KIMODO.en.md).

Keep the resolved plan, effective launch settings and observed execution evidence with private local job/output provenance. Report requested limits, enforcement gaps and observed memory separately; neither a plan nor successful inference proves visual quality. Publication of generated assets does not by itself authorize publication of machine details.
