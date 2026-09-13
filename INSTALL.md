# Installation guide for humans and coding agents

Install one shared runtime checkout, then point the agent skill or an optional MCP client at it. This is a repository-based installation, not a published standalone skill/plugin package. Read [AGENTS.md](AGENTS.md) before modifying the repository.

## 1. Choose the installation scope

| Profile | Install | Enables |
| --- | --- | --- |
| Default core | Python environment, trellis.cpp CUDA bundle, F16 models, Blender | Reference image → TRELLIS.2 → Blender processing → local render review → GLB |
| Local rigging, on demand | Isolated SkinTokens environment and checkpoints | Learned skeleton/weight prediction on the current mesh; no API key |
| Local parts, on demand | Isolated GeoSAM2 environment and checkpoint | Agent-observed point prompts → learned mesh part masks; no API key |
| Local editing and animation | Existing Blender | Trusted scripts for object/rig/weight/material edits and custom motion; compatible clip merging; no extra model download |
| Local motion presets | Existing Blender and a completed rig | Procedural idle/walk/run with actual bone mapping; other clips preserved |
| Explicit Tripo-only | Python environment, Blender, Tripo API credentials and credits | Paid cloud image/multiview generation → local Blender processing; no local CUDA or TRELLIS weights |
| Godot adapter | Godot binary | Import checks when relevant to the destination project |
| Interactive viewer | Node.js/npm and web bundle | A user-requested interactive preview or browser check |
| MCP addition | Python `mcp` extra and client configuration | The same runtime operations through stdio tools |

Default requirements: Windows/Linux x64, Git, uv and a compatible NVIDIA GPU/driver with enough VRAM for the workload. The commands below select Python 3.13 through uv; the package declares 3.11+, but 3.13 is the exercised setup. GPU generation has been exercised on an RTX 5090; no universal minimum VRAM is asserted. Node.js/npm (Node.js 22 in CI) is needed only for the optional viewer. Godot is not a core dependency.

The model download is about 16.5 GB, plus tool archives, extracted tools, Python/npm dependencies and generated outputs. Keep additional disk space for revisions. Model weights, installed tools and local assets are not in Git. A fresh clone starts with an empty library.

If a required prerequisite is missing, use the host's established package manager or official distribution. Inspect existing versions first. Do not replace a working system Python or install GPU drivers without a demonstrated need. If TRELLIS cannot run, report the blocker instead of calling a Blender-only installation the default system. Select Tripo only when the user explicitly chooses it; credentials or a GPU failure do not authorize switching providers.

## 2. Default installation

Clone into the user's chosen location. For an existing checkout, inspect `git status` and `git remote -v`; preserve local changes and installed assets. Do not clone over or reset an existing directory.

Windows PowerShell example:

```powershell
git clone https://github.com/NA-DEGEN-GIRL/3d-asset-auto.git 'D:\#programming\3d-asset-auto'
Set-Location 'D:\#programming\3d-asset-auto'
```

Linux example (replace the location as needed):

```sh
git clone https://github.com/NA-DEGEN-GIRL/3d-asset-auto.git ./3d-asset-auto
cd ./3d-asset-auto
```

From the repository root, on either OS:

```sh
uv sync --locked --python 3.13
uv run --no-sync python scripts/bootstrap.py
uv run --no-sync python -m asset_auto.cli doctor
```

The installer defaults to `--only core`: Blender, TRELLIS and its models, excluding Godot. Expected: `providers.trellis` is true and `models.missing` is empty. Missing Godot or `web/dist` is normal. `doctor` discovers paths and expected filenames; it does not prove binaries launch or CUDA inference works.

Run a real reference-image generation using [QUICKSTART.md](QUICKSTART.md). Inspect numeric results and open the local PNG renders with the agent's image-inspection tool. Deliver the GLB/source and observations. This completes the normal asset workflow without an engine, browser or web server.

The pinned portable tool versions are defined in [scripts/bootstrap.py](scripts/bootstrap.py). Downloads go under `.runtime/`, and checksums/source metadata under `.runtime/installed/`. For release API rate limits, the installer accepts an existing `GITHUB_TOKEN` environment variable for HTTPS requests to `api.github.com` only. It does not require a token on an ordinary successful public download. Never put a token in a committed file or printed command.

## 3. TRELLIS inputs and verification

Use `nvidia-smi` to inspect the actual GPU, driver and available VRAM, then run one reference-image request at resolution 512 as described in QUICKSTART. Report GPU installation verified only after real inference succeeds. The CLI requires GPU execution and does not silently fall back to CPU inference or procedural modeling.

For a text-only request, the agent prepares a reference using its available image-generation tool. This runtime has no text-to-image service. If neither an image nor that capability is available, request a reference instead of constructing Blender primitives from the prompt. Both the skill and `AssetSpec` default to TRELLIS; omitting `provider` still requires `image`.

To repair only missing GPU components in an existing installation:

```sh
uv run --no-sync python scripts/bootstrap.py --only trellis
uv run --no-sync python scripts/bootstrap.py --only models
uv run --no-sync python -m asset_auto.cli doctor
```

`uv run --no-sync python scripts/bootstrap.py --only all` also installs Godot. It does not build the viewer or install the separate local rigging/parts backends. The installer does not load a resident model server or configure cloud credentials. Different runtime roots have separate GPU locks, so use one shared root for clients targeting the same GPU.

For an explicitly requested procedural-only workflow or processing development, `--only blender` remains available. This is an alternative profile, not a silent downgrade when default TRELLIS generation is blocked. Existing named-part edits and supplied mesh imports use Blender without repeating inference.

## Local postprocessing on demand

Choose editing independently of generation. Existing assets use Blender for trusted `blender-edit` scripts and `merge-animations`, including assets originally generated by Tripo; see [the authoring guide](docs/BLENDER.md). Static props need no rig, and rigid object animation needs no learned model. `process` defaults to `provider: "local"` for its rigging, preset animation and segmentation operations. Install only the learned backend needed for the requested operation. A missing local backend does not select Tripo automatically.

The rigging and parts installers support native Linux and Windows through an existing WSL distribution (default `Ubuntu-24.04`). They require Linux `python3`, Git/uv and a working NVIDIA CUDA device in that environment. Inspect WSL/GPU availability first; these scripts do not install WSL, system packages or GPU drivers. SkinTokens advertises at least 14 GB VRAM; this is an upstream workload requirement, not a verified minimum for every input here.

From the runtime root, install the needed component:

```sh
uv run --no-sync python scripts/bootstrap_local_rig.py
uv run --no-sync python scripts/bootstrap_local_parts.py
uv run --no-sync python -m asset_auto.cli doctor
```

On Windows, either installer accepts `--wsl-distribution NAME` for the chosen existing distro. Both accept `--root ABSOLUTE_CHECKOUT`; the parts installer also accepts `--uv-cache PATH` for a wheel cache, not a shared environment. Use `--help` to inspect the current flags. Keep both environments under the same runtime root so local learned inference and TRELLIS share the GPU lock.

These are isolated managed Python 3.11.13 environments with PyTorch CUDA 12.8 wheels under `.runtime/local-rig/` and `.runtime/local-parts/`; they do not add Torch to the app's `.venv`. SkinTokens checkpoints are about 1.62 GB, and GeoSAM2's checkpoint is about 615 MB. Source trees, Python/Torch wheels and caches require additional space.

The [SkinTokens dependency lock](scripts/local_rig/requirements-linux.lock) pins the complete runtime's package versions. The [GeoSAM2 dependency lock](scripts/local_parts/requirements-linux.lock) pins versions and artifact SHA256 hashes, enforced with `uv pip sync --require-hashes`. Both installers' dependency dry runs passed. Model/source pins and file checks are owned by [bootstrap_local_rig.py](scripts/bootstrap_local_rig.py), [bootstrap_local_parts.py](scripts/bootstrap_local_parts.py) and [local_parts.py](src/asset_auto/local_parts.py). Readiness/provenance is recorded in `.runtime/installed/local-rig.json` or `local-parts.json`.

Upstream sources: [SkinTokens](https://github.com/VAST-AI-Research/SkinTokens) and [weights](https://huggingface.co/VAST-AI/SkinTokens), [GeoSAM2](https://github.com/VAST-AI-Research/GeoSAM2) and [weights](https://huggingface.co/VAST-AI/GeoSAM2). The adapters record MIT for SkinTokens and Apache-2.0 for GeoSAM2; dependencies have their own licenses. Review those sources for distribution requirements.

Local inference uses installed models without API credentials. Readiness checks do not prove successful rigging or segmentation: run the relevant [character workflow](docs/CHARACTERS.md) and inspect its actual output. SkinTokens is a rig draft that can be refined with a local script. Presets, custom authoring and clip merging use the normal Blender installation. The agent, not the end user, chooses segmentation prompts from the prepared renders and maps unknown bone names from observed joints.

## Optional Tripo cloud provider

For a user-selected Tripo-only installation, clone and enter the checkout as above, then run:

```sh
uv sync --locked --python 3.13
uv run --no-sync python scripts/bootstrap.py --only blender
```

Configure `TRIPO_API_KEY` in the process environment or put only the key in the ignored runtime file `.secrets/tripo_api_key`. `TRIPO_API_KEY_FILE` can point to another private key file. Do not paste the key into a chat, spec, command argument or tracked configuration. No Tripo SDK or separate cloud service is installed by this adapter.

Read [docs/TRIPO.md](docs/TRIPO.md) for supported PNG/JPEG inputs, single-image/multiview specs, `tripo-plan`, read-only balance verification and charged submission. `doctor` cannot prove the key is valid or the account has credit. Missing TRELLIS or local models does not block explicitly selected Tripo, but Blender is still needed for output processing and render review. An existing default installation can add credentials without reinstalling its tools.

An explicit request to generate with Tripo covers one standard generation per requested asset. The optional `tripo.max_credits` defaults to 100; standard generation is estimated at 30 credits. Do not pause for a separate credit confirmation within that scope. Honor a smaller user limit and keep unrequested paid retries, upgrades and variants outside the default scope.

The same Tripo-only installation supports explicitly selected Tripo rigging, preset animation and semantic segmentation of completed revisions, including TRELLIS/import assets. Read [docs/TRIPO.md](docs/TRIPO.md#리깅애니메이션부품-분리) for paid processing and [docs/CHARACTERS.md](docs/CHARACTERS.md) for shared review/import rules. This cloud option needs no local postprocessing weights; the default local backends are installed separately above.

## Optional project checks and viewer

Choose an engine check from the destination project's needs; for an unknown destination, keep the result portable. Godot and Three.js do not both need to run. Unperformed optional checks are untested, not a core failure.

For a relevant Godot check, reuse that project's installed Godot through local configuration, or install the adapter:

```sh
uv run --no-sync python scripts/bootstrap.py --only godot
uv run --no-sync python -m asset_auto.cli godot ASSET_ID REVISION
```

For an explicitly requested interactive viewer or browser rendering check, prefer an existing project app. To use this optional viewer, install Node.js/npm and then run:

```sh
npm --prefix web ci
npm --prefix web run build
```

Start with `./start-viewer.cmd` in PowerShell or `sh start-viewer.sh` on Linux, then open http://127.0.0.1:8765/. Windows runs a hidden background server with logs in `.work/viewer/`; Linux keeps a foreground terminal. No boot/login service is installed. Do not start or build a web app merely to let the agent inspect a model; local PNG review is the default.

## 4. Connect the agent skill

Use [.agents/skills/3d-assets/SKILL.md](.agents/skills/3d-assets/SKILL.md) in the checkout. Its Python wrapper finds the runtime's `.venv` by resolving its own real path. **Link the entire skill folder to this checkout; do not copy it to an unrelated folder.** An environment variable alone does not relocate the wrapper's Python environment.

For an agent with repository skill discovery, work in this checkout. For use from other game projects, create a personal skill link. The following Codex layout is the one used in this project; other agents can read the skill directly and invoke its absolute script path.

Windows PowerShell, from the repository root:

```powershell
$assetRepo = (Get-Location).Path
$assetCodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$assetSkills = Join-Path $assetCodexHome 'skills'
$assetSkillLink = Join-Path $assetSkills '3d-assets'
New-Item -ItemType Directory -Path $assetSkills -Force | Out-Null
if (Test-Path -LiteralPath $assetSkillLink) {
    Get-Item -LiteralPath $assetSkillLink | Select-Object FullName, LinkType, Target
} else {
    New-Item -ItemType Junction -Path $assetSkillLink -Target (Join-Path $assetRepo '.agents\skills\3d-assets')
}
```

If a link already exists, verify it targets this checkout. Preserve an existing different skill instead of silently replacing it.

Linux, from the repository root:

```sh
asset_repo="$(pwd -P)"
asset_skills="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$asset_skills"
ln -sT "$asset_repo/.agents/skills/3d-assets" "$asset_skills/3d-assets"
```

`ln -sT` intentionally refuses to replace an existing destination or create a nested link inside it. Inspect that destination when it exists.

Verify the wrapper from a **different working directory**, using absolute paths. Windows example for this checkout (adapt on another machine):

```powershell
& 'D:\#programming\3d-asset-auto\.venv\Scripts\python.exe' 'D:\#programming\3d-asset-auto\.agents\skills\3d-assets\scripts\assetctl.py' doctor
```

On Linux, the interpreter is `<checkout>/.venv/bin/python`. The JSON `root` must identify the intended runtime. Skill discovery may require a new agent session; if it is not listed, supply the skill file's absolute path explicitly. Do not claim a personal skill is connected solely because the repository was cloned.

## 5. Optional MCP client connection

Install the extra before launching the client:

```sh
uv sync --locked --extra mcp
```

Generic stdio launch configuration (adapt the enclosing structure to the client):

```json
{
  "command": "uv",
  "args": [
    "--directory", "D:/#programming/3d-asset-auto",
    "run", "--no-sync", "python", "-m", "asset_auto.cli", "mcp"
  ],
  "env": {"ASSET_AUTO_ROOT": "D:/#programming/3d-asset-auto"}
}
```

Replace both paths with the actual checkout. Use an absolute `uv` executable path if the client does not inherit PATH. This is not a complete client-specific config file and is not automatically registered by installation.

Core tool names: `asset_capabilities`, `generate_asset`, `edit_asset`, `asset_job_status`, `list_assets`, `inspect_asset`, `validate_in_godot`. Generation, edits and Godot checks return a submitted job; query its status to obtain results. Read [mcp_server.py](src/asset_auto/mcp_server.py) for the full current tool list. The visual `review` operation remains a CLI command. MCP does not supply browser or image-inspection tools. A client using Tripo must inherit the key environment or use the same private key file; never place the secret in a shared MCP config.

Tripo additions are `tripo_plan`, `tripo_balance` and `resume_tripo_asset`; the last returns a job ID to query with `asset_job_status`.

Default local processing uses `process_plan`, `process_asset`, `prepare_local_segmentation` and `resume_asset_processing`. Preparation, processing and recovery return jobs; plan is read-only. `tripo_process_plan`, `process_tripo_asset` and `resume_tripo_processing` retain the explicitly paid path. Read [PostprocessRequest](src/asset_auto/models.py) and the [character guide](docs/CHARACTERS.md) for exact inputs.

## 6. Existing tools and configuration

Optional `asset-system.local.json` in the runtime root:

```json
{
  "blender": "D:/tools/blender/blender.exe",
  "trellis": "D:/tools/trellis/trellis-cli.exe",
  "godot": "D:/tools/godot/Godot_console.exe",
  "models": "D:/models/trellis2-gguf"
}
```

These are placeholders; omit keys for tools managed by the installer. Tool lookup order is environment override → local config → portable `.runtime` discovery → PATH. Model lookup is environment → local config → `.runtime/models`. Environment names are `ASSET_AUTO_BLENDER`, `ASSET_AUTO_TRELLIS`, `ASSET_AUTO_GODOT`, `ASSET_AUTO_MODELS`. Relative tool/model paths resolve against the runtime root.

Runtime root selection for the CLI is `--root` (before the subcommand) → `ASSET_AUTO_ROOT` → current working directory. For example, `python -m asset_auto.cli --root /absolute/runtime doctor`. Input paths resolve against that runtime root, not the JSON file's directory. Use absolute paths for files in another project, including Tripo `image` and named `views`.

## 7. Installation acceptance and updates

Report the chosen profile, absolute checkout path, actual versions/paths, generated asset/revision, provider execution evidence, numeric/visual findings and skill/MCP connection status. Include a viewer URL or engine result only when requested/relevant and actually tested. Default installation acceptance requires real TRELLIS generation and Blender output inspection, not Godot or Three.js. For explicit Tripo, distinguish local setup/read-only account checks from an authorized paid generation and inspect its Blender outputs after completion. A successful `doctor` or submitted job alone is insufficient.

For updates, inspect the worktree and use a fast-forward pull when clean and appropriate. Stop verified active worker/viewer processes before changing their Python environment; on Windows, reinstallation can fail while executables are in use. Run `uv sync --locked` (with `--extra mcp` if used). Rebuild/restart the viewer only if that optional component is in use. Re-run bootstrap only for tool/model components that need installation or a changed pin.

Preserve `.assets/` and local configuration. Do not use `git clean -fdx` or remove `.runtime/` as a general repair step. See [troubleshooting](docs/TROUBLESHOOTING.md) for process, download and job failures.
