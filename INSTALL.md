# Installation guide for humans and coding agents

Install one shared runtime checkout, then point the agent skill or an optional MCP client at it. This is a repository-based installation, not a published standalone skill/plugin package. Read [AGENTS.md](AGENTS.md) before modifying the repository.

## 1. Choose the installation scope

| Profile | Install | Enables |
| --- | --- | --- |
| Basic | Python environment, web bundle, Blender, Godot | Procedural props, static imports/edits, engine and browser checks; no NVIDIA GPU required |
| GPU addition | trellis.cpp CUDA bundle and F16 GGUF models | Single-image TRELLIS.2 inference |
| MCP addition | Python `mcp` extra and client configuration | The same runtime operations through stdio tools |

Requirements: Windows/Linux x64, Git, uv and Node.js/npm. The commands below select Python 3.13 through uv; CI uses Python 3.13 and Node.js 22. The Python package declares 3.11+, but 3.13 is the exercised setup. GPU generation needs a compatible NVIDIA GPU/driver and enough VRAM for the selected workload. It has been exercised on an RTX 5090; no universal minimum VRAM is asserted.

The model download is about 16.5 GB, plus tool archives, extracted tools, Python/npm dependencies and generated outputs. Keep additional disk space for revisions. Model weights, installed tools and local assets are not in Git. A fresh clone starts with an empty library.

If Git, uv or Node.js are missing, install them through the host's established package manager or official distribution. Inspect existing versions first. Do not replace a working system Python or install GPU drivers as part of this repository setup without a demonstrated need.

## 2. Basic installation

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
uv run --no-sync python scripts/bootstrap.py --only blender
uv run --no-sync python scripts/bootstrap.py --only godot
npm --prefix web ci
npm --prefix web run build
uv run --no-sync python -m asset_auto.cli doctor
```

Expected: `providers.procedural` and `tools.godot.available` are true. `providers.trellis` may be false for a basic installation. `doctor` discovers paths and expected filenames; it does not prove that binaries launch, weights are usable or CUDA inference works.

Run an actual first asset and engine check using [QUICKSTART.md](QUICKSTART.md). Start the viewer with `./start-viewer.cmd` in PowerShell or `sh start-viewer.sh` on Linux. Open http://127.0.0.1:8765/ and verify a selected model visibly renders. Windows runs a hidden background server with logs in `.work/viewer/`; Linux's launcher runs in the foreground. This does not install a boot/login service.

The pinned portable tool versions are defined in [scripts/bootstrap.py](scripts/bootstrap.py). Downloads go under `.runtime/`, and checksums/source metadata under `.runtime/installed/`. For release API rate limits, the installer accepts an existing `GITHUB_TOKEN` environment variable for HTTPS requests to `api.github.com` only. It does not require a token on an ordinary successful public download. Never put a token in a committed file or printed command.

## 3. Add TRELLIS GPU generation (optional)

From the configured checkout:

```sh
uv run --no-sync python scripts/bootstrap.py --only trellis
uv run --no-sync python scripts/bootstrap.py --only models
uv run --no-sync python -m asset_auto.cli doctor
```

Expected: `models.missing` is empty and `providers.trellis` is true. Use `nvidia-smi` to inspect the actual GPU, driver and available VRAM, then run one real reference-image request at resolution 512 as described in QUICKSTART. Report GPU installation verified only after this succeeds. The CLI requires GPU execution; it does not silently fall back to CPU inference.

`uv run --no-sync python scripts/bootstrap.py` installs all four components if a full installation is wanted from the start. The installer does not load a resident model server, configure image-generation credentials, or install rigging components. Different runtime roots have separate GPU locks, so use one shared root for clients targeting the same GPU.

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

Report the chosen profile, absolute checkout path, actual versions/paths, selected generated asset/revision, checks executed, viewer URL, skill/MCP connection status and any unavailable capability. Installation is complete for the **requested profile** after a real generation/import and requested engine/browser checks pass. A successful `doctor` or submitted job alone is insufficient.

For updates, inspect the worktree and use a fast-forward pull when clean and appropriate. Stop the verified viewer/worker processes before changing their Python environment; on Windows, reinstallation can fail while executables are in use. Run `uv sync --locked` (with `--extra mcp` if used), rebuild with `npm --prefix web ci` and `npm --prefix web run build`, then restart the viewer. Re-run bootstrap only for tool/model components that need installation or a changed pin.

Preserve `.assets/` and local configuration. Do not use `git clean -fdx` or remove `.runtime/` as a general repair step. See [troubleshooting](docs/TROUBLESHOOTING.md) for process, download and job failures.
