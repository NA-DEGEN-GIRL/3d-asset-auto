"""Invoke the shared runtime from any game project or personal-skill junction.

On a non-Windows host a registered workspace-skill-bridge descriptor that enables this
skill forwards the same arguments to the bridge client, which runs the runtime on the
Windows host that owns the installed checkout. Without a descriptor the wrapper keeps its
native local runtime contract, including `<root>/.venv/bin/python` on Linux. See
references/windows-bridge.md.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SKILL_NAME = "3d-assets"
CLIENT_NAME = "client.py"
CONNECTION_NAME = "connection.json"


def descriptor_path(environ):
    """Return the registered descriptor to use, or None when no implicit descriptor exists.

    An explicit CODEX_WORKSPACE_SKILL_BRIDGE that does not exist is a configuration error.
    """
    explicit = environ.get("CODEX_WORKSPACE_SKILL_BRIDGE")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise SystemExit(
                f"Bridge configuration error: CODEX_WORKSPACE_SKILL_BRIDGE points at {path}, "
                "which is not an existing descriptor file"
            )
        return absolute(path)
    candidates = []
    if environ.get("CODEX_HOME"):
        candidates.append(Path(environ["CODEX_HOME"]).expanduser() / "workspace-skill-bridge" / CONNECTION_NAME)
    home = environ.get("HOME") or environ.get("USERPROFILE")
    if home:
        candidates.append(Path(home).expanduser() / ".codex" / "workspace-skill-bridge" / CONNECTION_NAME)
    for candidate in candidates:
        if candidate.is_file():
            return absolute(candidate)
    return None


def absolute(path):
    """Return an absolute path without following a symlink in the final component."""
    return path.parent.resolve() / path.name


def file_problem(path, os_module):
    """Describe why a POSIX bridge file is untrusted, or return None when it is private."""
    try:
        info = os_module.stat(path, follow_symlinks=False)
    except (OSError, ValueError):
        return "cannot be inspected"
    if stat.S_ISLNK(info.st_mode):
        return "must not be a symlink"
    if not stat.S_ISREG(info.st_mode):
        return "must be a regular file"
    getuid = getattr(os_module, "getuid", None)
    if getuid is not None and info.st_uid != getuid():
        return "must be owned by the current user"
    if info.st_mode & 0o077:
        return "must not be group- or world-accessible; set mode 600"
    return None


def bridge_command(os_name, environ, arguments):
    """Return the bridge client argv when a descriptor enables this skill, else None."""
    if os_name == "nt":
        return None
    path = descriptor_path(environ)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise SystemExit(f"Bridge configuration error: {path} cannot be read ({error})") from None
    try:
        descriptor = json.loads(text)
    except ValueError as error:
        raise SystemExit(f"Bridge configuration error: {path} is not valid JSON ({error})") from None
    if not isinstance(descriptor, dict):
        raise SystemExit(f"Bridge configuration error: {path} must contain a JSON object")
    enabled = descriptor.get("enabled_skills")
    if not isinstance(enabled, list) or SKILL_NAME not in enabled:
        return None
    problem = file_problem(path, os)
    if problem is not None:
        raise SystemExit(f"Bridge configuration error: {path} {problem}")
    raw_client = descriptor.get("client")
    if raw_client is None:
        client = path.parent / CLIENT_NAME
    else:
        client = Path(str(raw_client)).expanduser()
        if not client.is_absolute():
            raise SystemExit(
                f"Bridge configuration error: client {raw_client} in {path} must be an absolute path"
            )
        if client.parent != path.parent:
            raise SystemExit(f"Bridge configuration error: client {client} must be a sibling of {path}")
    problem = file_problem(client, os)
    if problem is not None:
        raise SystemExit(f"Bridge configuration error: client {client} {problem}")
    return [sys.executable, str(client), "--connection", str(path), "run", SKILL_NAME, "--", *arguments]


def main(argv=None, *, os_name=None, environ=None, root=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    os_name = os.name if os_name is None else os_name
    environ = os.environ if environ is None else environ
    command = bridge_command(os_name, environ, arguments)
    if command is not None:
        return subprocess.run(command, check=False).returncode
    runtime_root = Path(__file__).resolve().parents[4] if root is None else Path(root)
    environment = dict(environ)
    environment.setdefault("ASSET_AUTO_ROOT", str(runtime_root))
    python = runtime_root / ".venv" / ("Scripts/python.exe" if os_name == "nt" else "bin/python")
    if not python.exists():
        raise SystemExit(f"Runtime environment missing; run uv sync in {runtime_root}")
    result = subprocess.run([str(python), "-m", "asset_auto.cli", *arguments], env=environment, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
