# Installation guide for humans and coding agents

Install one shared runtime checkout, then point the agent skill or an optional MCP client at it. This is a repository-based installation, not a published standalone skill/plugin package. Read [AGENTS.md](AGENTS.md) before modifying the repository.

## 1. Choose the installation scope

| Profile | Install | Enables |
| --- | --- | --- |
| Default core | Python environment, trellis.cpp CUDA bundle, F16 models, Blender | Reference image → TRELLIS.2 → Blender processing → local render review → GLB |
| Godot adapter | Godot binary | Import checks when relevant to the destination project |
| Interactive viewer | Node.js/npm and web bundle | A user-requested interactive preview or browser check |
| MCP addition | Python `mcp` extra and client configuration | The same runtime operations through stdio tools |

Default requirements: Windows/Linux x64, Git, uv and a compatible NVIDIA GPU/driver with enough VRAM for the workload. The commands below select Python 3.13 through uv; the package declares 3.11+, but 3.13 is the exercised setup. GPU generation has been exercised on an RTX 5090; no universal minimum VRAM is asserted. Node.js/npm (Node.js 22 in CI) is needed only for the optional viewer. Godot is not a core dependency.

The model download is about 16.5 GB, plus tool archives, extracted tools, Python/npm dependencies and generated outputs. Keep additional disk space for revisions. Model weights, installed tools and local assets are not in Git. A fresh clone starts with an empty library.

If a required prerequisite is missing, use the host's established package manager or official distribution. Inspect existing versions first. Do not replace a working system Python or install GPU drivers without a demonstrated need. If TRELLIS cannot run, report the blocker instead of calling a Blender-only installation the default system.

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

`uv run --no-sync python scripts/bootstrap.py --only all` also installs Godot. It does not build the viewer. The installer does not load a resident model server, configure image-generation credentials, or install rigging components. Different runtime roots have separate GPU locks, so use one shared root for clients targeting the same GPU.

For an explicitly requested procedural-only workflow or processing development, `--only blender` remains available. This is an alternative profile, not a silent downgrade when default TRELLIS generation is blocked. Existing named-part edits and supplied mesh imports use Blender without repeating inference.

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

Expected tool names: `asset_capabilities`, `generate_asset`, `edit_asset`, `asset_job_status`, `list_assets`, `inspect_asset`, `validate_in_godot`. Generation, edits and Godot checks return a submitted job; query its status to obtain results. The visual `review` operation remains a CLI command. MCP does not supply browser or image-inspection tools.

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

Runtime root selection for the CLI is `--root` (before the subcommand) → `ASSET_AUTO_ROOT` → current working directory. For example, `python -m asset_auto.cli --root /absolute/runtime doctor`. Input `image`/`source` paths in specs resolve against that runtime root, not the JSON file's directory. Use absolute paths for files in another project.

## 7. Installation acceptance and updates

Report the chosen profile, absolute checkout path, actual versions/paths, generated asset/revision, TRELLIS execution evidence, numeric/visual findings and skill/MCP connection status. Include a viewer URL or engine result only when requested/relevant and actually tested. Default installation acceptance requires real TRELLIS generation and Blender output inspection, not Godot or Three.js. A successful `doctor` or submitted job alone is insufficient.

For updates, inspect the worktree and use a fast-forward pull when clean and appropriate. Stop verified active worker/viewer processes before changing their Python environment; on Windows, reinstallation can fail while executables are in use. Run `uv sync --locked` (with `--extra mcp` if used). Rebuild/restart the viewer only if that optional component is in use. Re-run bootstrap only for tool/model components that need installation or a changed pin.

Preserve `.assets/` and local configuration. Do not use `git clean -fdx` or remove `.runtime/` as a general repair step. See [troubleshooting](docs/TROUBLESHOOTING.md) for process, download and job failures.
