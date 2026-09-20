# Execution host and first-time setup

**English** | [한국어](execution-setup.ko.md)

## Inspect before installing

When the user asks to install/setup this skill on another computer, inspect the
OS, existing runtime, Python, required tools and (only for a selected model) GPU
and disk capacity. Use the user's existing runtime and authenticated tools when
usable. Ask only for missing choices that affect the requested capability:
installation directory when nonstandard, selected optional model, or credentials.
Do not ask for API secrets in chat. Use a private local key file/environment,
validate through a read-only account check, and report only configured/verified.
Copy a key to another host only with the user's authorization.
When Windows execution is already available, check its doctor before requesting
a new key: the agent can use that existing authenticated route without copying
credentials to Linux.

Install the core first. Model environments and weights are separate, optional
installations selected for the task; a CPU-only server must not be reported as
ready for CUDA generation. Do not change the requested model/provider to make
installation pass. Existing approval to install covers ordinary setup commands;
do not repeatedly ask about prerequisites already authorized.

## Windows and Linux core

Use a full runtime checkout, not a copy of the skill folder. Preserve any
existing checkout, local settings, assets and uncommitted work.

```sh
# In the runtime checkout on either operating system:
uv sync --locked --python 3.13
python .agents/skills/3d-assets/scripts/assetctl.py runtime-configure --root /absolute/runtime --execution auto
python .agents/skills/3d-assets/scripts/assetctl.py runtime-status
python .agents/skills/3d-assets/scripts/assetctl.py --execution local doctor
```

Use an available Python to run the wrapper (`python3` on Linux); use a real
Windows absolute path on Windows. Registration checks the installed virtualenv
and pyproject; it does not install tools or prove generation capability. It stores
only root/execution in `~/.config/codex-skill-runtimes/3d-assets.json`
(or `XDG_CONFIG_HOME`), shared across Codex profiles on that host.

Install/configure Blender for editing, animation and GLB processing. A headless
Linux server can use Cycles CPU renders. Check actual export/render compatibility
with the installed Blender version. Read the repository's INSTALL.md for selected
TRELLIS/CUDA, SkinTokens, GeoSAM2 or explicitly selected Kimodo/Tripo setup.
No GPU is required for ordinary Blender editing; this is not TRELLIS readiness.
Some distribution Blender builds lack OpenImageDenoiser and fail this runtime's
CPU preview rendering. In that case install the pinned official portable Blender
with `python scripts/bootstrap.py --only blender`; it stays under this runtime's
`.runtime` without replacing the system package. Repeat the actual render check.

## Select and pin execution

- `--execution local`: run this machine's registered runtime (or the linked
  checkout if unregistered), including while a Windows bridge is enabled.
- `--execution windows`: from SSH, use the registered Windows bridge; if it is
  unavailable, fail instead of silently running locally. On Windows this runs
  its native runtime.
- `auto`: prefer an explicitly registered native runtime. Without a native
  registration, preserve the existing Windows bridge behavior on SSH; otherwise
  use the linked local checkout. This resolves an installation, not every model's
  capability. Use `doctor` and the operation's plan before choosing the host.

Choose by the requested capability, existing assets and input locations. For
example, keep server audio edits on Linux; choose Windows for a CUDA model that
only Windows has. If local prerequisites are missing, the agent can plan a
Windows execution **before submission** using windows-bridge.md. The wrapper
never retries a failed/uncertain submission on another host or changes provider.

After choosing, use the explicit execution flag for submission, job polling,
resume, inspection and editing of that result. Keep runtime root/host with every
job or asset ID. Each host owns its library and jobs; registering a native
runtime does not migrate Windows history. To move existing work, transfer its
required inputs or export then import, with provenance; never assume an ID refers
to the same files on both machines.

Windows bridge requests need Windows input paths. Follow windows-bridge.md to
upload inputs and fetch results into the SSH project; native Linux requests use
Linux paths directly. The project/coding task itself stays on its original host.
Native Linux jobs can continue without Windows. Windows jobs need the workspace
worker and tunnel to remain available.

## Validate setup

Run status/doctor, then a small deterministic import/edit/export using temporary
fixtures and inspect actual output hashes/files. These checks are not model
inference or quality approval. Test a requested API/model separately within the
authorized scope, preserving paid receipts and avoiding automatic repeat calls.

Maintainers: host selection lives in the wrapper, before runtime invocation.
The manager distributes the same wrapper/docs as a lightweight SSH projection.
Registered roots live outside that projection, so document refreshes never
replace native environments or assets. Keep wrapper routing tests and the paired
Korean guide current when changing this contract.
Native runtime code/dependencies are versioned separately: update that installation
deliberately and re-run its smoke checks when a new skill needs newer runtime
commands. A synchronized instruction file is not a runtime upgrade.
