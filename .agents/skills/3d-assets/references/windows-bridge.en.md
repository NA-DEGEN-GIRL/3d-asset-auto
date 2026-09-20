# Windows bridge routing

[한국어](windows-bridge.md) | **English**

Read this before running this skill's wrapper from a non-Windows host, or before changing how the wrapper selects a runtime.

## Why the wrapper routes

`scripts/assetctl.py` normally runs the linked runtime checkout on the same machine: it resolves the checkout four parents above itself and runs `<root>/.venv/bin/python -m asset_auto.cli` (`.venv/Scripts/python.exe` on Windows). The installed environment — Python environment, Blender, TRELLIS tools, model weights, WSL learned backends and private keys — stays in that checkout. Copying the skill folder into another project carries the instructions but not that environment. A native Linux runtime is fully supported by the wrapper (`<root>/.venv/bin/python`); it needs its own `uv sync` plus tool and model setup rather than a copy of this skill.

When a Windows machine already holds a working checkout, a registered bridge lets the same commands run there instead.

## When the wrapper delegates

Delegation requires all of:

- execution is explicitly `--execution windows`, or `auto` with no registered native runtime; see [execution-setup.md](execution-setup.md),
- the host is not Windows (`os.name != "nt"`); Windows always uses the local runtime,
- a descriptor file exists, is private and same-user owned, and parses as a JSON object,
- its `enabled_skills` list contains `3d-assets`,
- the client it names is an absolute sibling of the descriptor that exists as a private, symlink-free file.

Descriptor lookup order:

1. `$CODEX_WORKSPACE_SKILL_BRIDGE` — an explicit path to `connection.json`. A path that does not exist is a configuration error.
2. `$CODEX_HOME/workspace-skill-bridge/connection.json`.
3. `~/.codex/workspace-skill-bridge/connection.json` — the original user profile when `CODEX_HOME` points at a managed profile.

The wrapper reads only `client` and `enabled_skills`. `client` may be omitted; the wrapper then expects `client.py` next to the descriptor. The descriptor itself is created on the remote account by the installer — it is the remote half of the connection and holds a scoped bearer credential, so keep it mode 600 there.

When the Windows route is selected, configuration errors stop the run with a message naming the file and the fix; they are never downgraded to a local install hint. Explicit local execution and registered-native auto do not require the bridge:

- an explicit override that points at a missing file,
- a descriptor that exists but cannot be read, is not valid JSON, or is not a JSON object,
- a descriptor that enables this skill but is not a private (mode 600), same-user, non-symlink file,
- a client that is missing, relative, outside the descriptor directory, a symlink, or not a private same-user file.

A descriptor that parses correctly but does not list this skill is not an error: the wrapper runs the local runtime, which is how one descriptor serves several skills. When no descriptor is found at all the wrapper keeps its native local behavior, which on Linux is `<root>/.venv/bin/python -m asset_auto.cli` and needs its own `uv sync` plus tool/model setup. A client that fails returns its own message and exit code unchanged.

## Bridge client protocol

The installer projects each enabled skill to `~/.agents/skills/<name>` and writes the client next to `connection.json` under `~/.codex/workspace-skill-bridge/` on the remote account, both bridge files mode 600; this repository does not ship the client. It talks to the Windows worker through an SSH-forwarded authenticated loopback endpoint, so the forward must be up.

```sh
python3 <client> [--connection <connection.json>] catalog
python3 <client> --connection <connection.json> read 3d-assets skill:/SKILL.md
python3 <client> --connection <connection.json> read 3d-assets runtime:/docs/BLENDER.md
python3 <client> --connection <connection.json> upload <local-path>
python3 <client> --connection <connection.json> run 3d-assets --request-id <uuid> --wait 30 -- <command> [args...]
python3 <client> --connection <connection.json> job <bridge-job-id>
python3 <client> --connection <connection.json> fetch 3d-assets runtime:/.assets/<asset>/<revision>/asset.glb <new-local-file>
```

- `catalog` lists the registered skills with their Windows runtime root.
- `read` serves documentation only: `skill:/SKILL.md`, `skill:/references/<name>.md` and `runtime:/docs/<name>.md`. Every other path is refused, so `read` cannot expose logs, keys or project files.
- `upload` streams a local file to the worker in 1 MiB chunks and prints its upload record; the record's `path` is the staged Windows path to use in requests. The file must stay unchanged while it uploads.
- `run` requires `--` followed by the skill command, with bridge options before it. `--wait` defaults to 30 seconds and caps at 300. The worker accepts only this wrapper's own commands; `--root`, `serve`, `mcp` and worker entrypoints are refused. It records the request id and reuses the same job for an identical retry of that id.
- `job` reports `queued`, `running` or a terminal `complete`, `failed` or `interrupted`, with `exit_code`, `error` and truncated `stdout`/`stderr`.
- `fetch` copies one artifact back and verifies its SHA-256 against the worker's `stat`. Use `upload:/<upload-id>/<name>` for a file this session uploaded, `runtime:/.assets/...` or `runtime:/.work/...` for a runtime artifact, or an absolute path inside those directories. The destination must not already exist.

## Paths

The wrapper forwards arguments verbatim; nothing translates paths. Order matters:

1. Upload the dependency files first — reference images, source meshes, anything the request points at — and keep the Windows paths the worker returns.
2. Rewrite the paths inside a local copy of the request JSON to those Windows paths; the bridge never rewrites JSON.
3. Upload that final JSON and pass the returned Windows path to `run`.
4. Ask for outputs as Windows paths (the runtime writes under its own `.assets/`/`.work/`) and fetch them back with a `runtime:` or `upload:` path.

Relative paths inside a request are resolved by the Windows CLI against the runtime root, not against the JSON file's folder, and `run` cannot override that root.

## Two job layers

The bridge job ID and the runtime's own job ID are different objects:

- `run` returns a bridge job ID; the client polls it for up to `--wait`, then prints the job's `stdout`/`stderr` and returns the skill's exit code on `complete`. `failed` or `interrupted` prints the job record and exits 1.
- The client journals the request under `requests/<request-id>.json` in the bridge directory before contacting the worker and prints `Skill bridge request: <id>` on stderr. The worker returns the same job for an identical retry with that id and rejects it for a different command.
- The runtime writes its own job record, printed by the CLI (`--async`) and queried with `job <runtime-job-id>` through the same route.

Query the job that matches the state you need, and never submit a replacement while a job is running or an outcome is unknown. An uncertain paid Tripo submission is reconciled through the saved task record and `resume-tripo`; a lost bridge connection is not evidence that the submission failed.

## Example: generate an asset from a Linux game project

```sh
CLIENT="${CLIENT:-$HOME/.codex/workspace-skill-bridge/client.py}"   # installer default on the remote

python3 "$CLIENT" catalog

# 1. Upload dependencies first and keep the returned Windows paths.
python3 "$CLIENT" upload ./references/oak-chest.png

# 2. Rewrite .work/chest.json to those paths, then upload the final JSON.
python3 "$CLIENT" upload .work/chest.json

# 3. Run it; bridge options come before --.
python3 "$CLIENT" run 3d-assets --request-id "$REQUEST_ID" --wait 30 -- generate <spec> --async
python3 "$CLIENT" job "$BRIDGE_JOB_ID"
# Then query the runtime job id that the CLI printed.

# 4. Fetch deliverables and sidecars.
python3 "$CLIENT" fetch 3d-assets runtime:/.assets/oak-chest/<revision>/asset.glb ./assets/oak-chest.glb
python3 "$CLIENT" fetch 3d-assets runtime:/.assets/oak-chest/<revision>/manifest.json ./assets/oak-chest.manifest.json
```

Omit `--connection` and the client uses its own discovery: `$CODEX_WORKSPACE_SKILL_BRIDGE`, then `$CODEX_HOME/workspace-skill-bridge/connection.json`, then `~/.codex/workspace-skill-bridge/connection.json`. Pass `--connection <path>` explicitly only when the descriptor sits somewhere else.

## Review after fetching

Fetch deliverables with their sidecars before judging them: `asset.glb` plus `manifest.json`, `inspection.json`, the render PNGs and `usage.json` when present. `fetch` verifies SHA-256, so hash-bound checks (manifest hashes, `verify`) still apply to the local copies. Visual review requires actually inspecting the fetched images; a successful transfer, a viewer draw or a numeric pass is not visual approval.

## What stays on the Windows host

- The runtime checkout, its Python environment, Blender, TRELLIS tools, model weights and WSL learned backends.
- Provider credentials — Tripo credentials and any Hugging Face token — stay on this host and are never uploaded. The transport descriptor is the deliberate exception: the installer creates it on the remote account, so keep it mode 600 there and never copy it into requests, logs or chat.
- One shared runtime root per GPU: the bridge must not create parallel roots, because GPU locks are per-root.

## Invariants this route does not change

- Provider and authorization rules: Tripo stays explicit-selection and paid, a missing local backend never selects it, and credit caps plus the estimate guard are unchanged.
- Job and recovery rules: no duplicate or automatic paid retry, and unknown outcomes are reconciled.
- Evidence rules: numeric measurement, visual review and listening remain separate, and `review` sidecars stay bound to the delivered file hash.

## Verified transport evidence (2026-09-20)

The actual Windows worker + SSH loopback transport was exercised end to end on 2026-09-20 in a live fixture session, not a user project:

- the projected wrapper on the remote host delegated to the Windows runtime and returned `doctor` output for this checkout;
- the descriptor checks, request journal and job polling described above were used as written;
- no generation, paid API or model inference ran, and no asset review was performed.

Model inference, Blender authoring/rendering and asset quality remain untested through this transport.

## Maintainer contract

- Keep the wrapper thin: descriptor discovery, validation and argument forwarding only. No path mapping, request rewriting, request IDs, provider logic or secret handling.
- New CLI commands need no wrapper change because arguments are forwarded verbatim, but the worker's per-skill command allowlist must include the new command or `run` refuses it.
- The Windows check keeps the local path authoritative on the host that owns the runtime and prevents recursion when the client runs the same wrapper remotely.
- If the client protocol changes, update both language versions of this file and the wrapper together, and keep the `client` / `enabled_skills` descriptor keys stable.
- `tests/test_skill_bridge_routing.py` pins discovery order, configuration errors, the file-trust checks (owner, mode, symlink, sibling path), enabled-skill gating, the Windows bypass and the no-fallback client error using mocked subprocess, injected platform/environment and a mocked POSIX metadata view.
