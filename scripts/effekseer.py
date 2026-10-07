"""Pinned portable Effekseer setup and CPU-only project conversion on Windows.

This does not launch the editor, render frames, author effects or bundle their
external resources. D3D/WebGL device selection is outside CUDA resource policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

VERSION = "1.80.7"
COMMIT = "b87d1a2e3ff3731ba25cad34f8d8abeae382b21f"
RELEASE = "https://github.com/effekseer/Effekseer/releases/download/1807/"
ARTIFACTS = {
    "editor": ("Effekseer1.80.7Win.zip", "6f059b9cce3a79c5bfe3df9c970cfe62fd72acf130083c7b81832d90f8d1335f"),
    "webgl": ("EffekseerForWebGL1.80.7.zip", "4d6f1d399b661e509231d1fcb375377e79bb02561022f892a8acb2f5eee93a8b"),
}
LICENSE_URL = f"https://raw.githubusercontent.com/effekseer/Effekseer/{COMMIT}/LICENSE"
LICENSE_SHA256 = "9686573243a6e4732edef9e39ac1356371dc7f4a17d995bea32777e36463cb29"
EDITOR_DIR = "editor/Effekseer1.80.7Win"
REQUIRED = {
    "editor": [f"{EDITOR_DIR}/Tool/bin/Effekseer.exe", f"{EDITOR_DIR}/LICENSE_TOOL",
               f"{EDITOR_DIR}/Tool/bin/tools/EffekseerResourceConverter.exe"],
    "webgl": ["webgl/effekseer.js", "webgl/effekseer.wasm", "webgl/LICENSE"],
}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def runtime_dir(root):
    return Path(root).resolve() / ".runtime" / "effekseer" / VERSION


def download(url, destination, expected):
    """Do not accept an unverified cached file or replace a corrupt one silently."""
    destination = Path(destination)
    if destination.exists():
        if sha256(destination) != expected:
            raise ValueError(f"Cached download checksum mismatch: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".partial", delete=False) as output:
        temporary = Path(output.name)
        request = urllib.request.Request(url, headers={"User-Agent": "3d-asset-auto-effekseer"})
        with urllib.request.urlopen(request, timeout=60) as response:
            count = 0
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > 512 * 1024**2:
                    raise ValueError("Download exceeds the portable release's bounded size")
                output.write(block)
    if sha256(temporary) != expected:
        raise ValueError(f"Download checksum mismatch; retained for diagnosis: {temporary}")
    temporary.replace(destination)


def safe_members(archive, destination):
    """Validate the complete ZIP before writing, including Windows path aliases."""
    destination = Path(destination).resolve()
    seen = set()
    total = 0
    for item in archive.infolist():
        name = item.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if (path.is_absolute() or not path.parts or ":" in name
                or any(p in ("..", ".") or p.endswith((" ", ".")) for p in path.parts)
                or stat.S_ISLNK(item.external_attr >> 16)):
            raise ValueError(f"Unsafe archive member: {item.filename}")
        key = name.rstrip("/").casefold()
        if key in seen:
            raise ValueError(f"Duplicate archive member: {item.filename}")
        seen.add(key)
        target = destination.joinpath(*path.parts).resolve()
        if not target.is_relative_to(destination):
            raise ValueError(f"Archive member escapes destination: {item.filename}")
        total += item.file_size
        if total > 2 * 1024**3 or len(seen) > 20000:
            raise ValueError("Archive exceeds bounded extraction size/count")
        yield item, target


def extract_verified(archive_path, destination):
    """Reuse matching extracted files; reject different existing files in place."""
    with zipfile.ZipFile(archive_path) as archive:
        members = list(safe_members(archive, destination))
        for item, target in members:
            if item.is_dir():
                continue
            if target.exists():
                with archive.open(item) as stream:
                    expected = hashlib.file_digest(stream, "sha256").hexdigest()
                if not target.is_file() or sha256(target) != expected:
                    raise ValueError(f"Existing installation differs from pinned archive: {target}")
        for item, target in members:
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)


def install(root, component="all"):
    chosen = tuple(ARTIFACTS) if component == "all" else (component,)
    if "editor" in chosen and sys.platform != "win32":
        raise ValueError("This portable editor installer currently supports Windows only; WebGL is portable")
    base = runtime_dir(root)
    for name in chosen:
        filename, digest = ARTIFACTS[name]
        archive = base / "downloads" / filename
        download(RELEASE + filename, archive, digest)
        extract_verified(archive, base / name)
        if name == "webgl":
            download(LICENSE_URL, base / "webgl/LICENSE", LICENSE_SHA256)
        receipt = {
            "version": VERSION, "source_commit": COMMIT,
            "url": RELEASE + filename, "archive_sha256": digest,
            "files": {p: sha256(base / p) for p in REQUIRED[name]},
        }
        (base / f"{name}.install.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return doctor(root)


def doctor(root):
    base = runtime_dir(root)
    components = {}
    for name, paths in REQUIRED.items():
        receipt_path = base / f"{name}.install.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
        missing = [p for p in paths if not (base / p).is_file()]
        hashes_match = bool(receipt) and all(
            (base / p).is_file() and sha256(base / p) == receipt.get("files", {}).get(p) for p in paths)
        components[name] = {"ready": not missing and hashes_match, "missing": missing,
                            "receipt_hashes_match": hashes_match}
    return {
        "version": VERSION, "source_commit": COMMIT, "runtime": str(base), "components": components,
        "editor_cli": str(base / EDITOR_DIR / "Tool/bin/Effekseer.exe"),
        "model_converter": str(base / EDITOR_DIR / "Tool/bin/tools/EffekseerResourceConverter.exe"),
        "webgl_runtime": str(base / "webgl"),
        "capabilities": {"cui_conversion": "CPU; no GUI/material-cache rendering",
                         "editor_preview": "Direct3D on Windows; GPU adapter not controlled by CUDA masks",
                         "webgl_preview": "Browser-selected graphics adapter; verify renderer separately"},
    }


def validate_output(path):
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() == ".efkmodel":
        if len(data) < 24:
            raise ValueError("Truncated Effekseer model")
        version, scale, model_count, frame_count = struct.unpack_from("<ifii", data)
        if version != 6 or not math.isfinite(scale) or scale <= 0 or model_count < 1 or frame_count < 1:
            raise ValueError("Unexpected Effekseer 1.80.7 model header")
    elif Path(path).suffix.lower() == ".efk":
        if len(data) < 12 or data[:4] != b"SKFE":
            raise ValueError("Effekseer did not write a valid runtime binary header")
    else:
        if len(data) < 24 or data[:4] != b"EFKE":
            raise ValueError("Effekseer did not write a valid effect container header")
        pos, chunks = 8, set()
        while pos + 8 <= len(data):
            name, size = struct.unpack_from("<4sI", data, pos)
            pos += 8
            if pos + size > len(data):
                raise ValueError("Truncated Effekseer container")
            if name == b"BIN_" and (size < 12 or data[pos:pos + 4] != b"SKFE"):
                raise ValueError("Effekseer container has an invalid runtime binary")
            chunks.add(name)
            pos += size
        if pos != len(data) or not {b"EDIT", b"BIN_"}.issubset(chunks):
            raise ValueError("Effekseer container lacks editable source or runtime binary")


def dependencies(path):
    """Inspect the pinned exporter's INFO table; this does not package resources."""
    path = Path(path)
    data = path.read_bytes()
    position, info = 8, None
    while position + 8 <= len(data):
        name, size = struct.unpack_from("<4sI", data, position)
        position += 8
        if name == b"INFO":
            info = data[position:position + size]
            break
        position += size
    if info is None or len(info) < 8:
        raise ValueError("Effekseer container lacks a dependency inventory")
    version, count = struct.unpack_from("<ii", info)
    if version != 1810 or count < 0 or count > 100000:
        raise ValueError("Unexpected pinned Effekseer dependency table")
    position, found = 8, []
    for _ in range(count):
        if position + 12 > len(info):
            raise ValueError("Truncated Effekseer dependency record")
        file_type, flags, units = struct.unpack_from("<iii", info, position)
        position += 12
        end = position + units * 2
        if units < 1 or end > len(info):
            raise ValueError("Truncated Effekseer dependency path")
        relative = info[position:end].decode("utf-16-le")
        position = end
        if not relative.endswith("\0") or "\0" in relative[:-1]:
            raise ValueError("Invalid Effekseer dependency path terminator")
        relative = relative[:-1].replace("\\", "/")
        target = path.parent / relative
        present = target.is_file()
        found.append({"path": relative, "file_type": file_type, "flags": flags, "exists": present,
                      "sha256": sha256(target) if present else None})
    if position != len(info):
        raise ValueError("Unexpected trailing Effekseer dependency data")
    return found


def export(root, source, output, timeout=120, *, model_scale=None):
    """Headless save/export; exit zero alone is insufficient in upstream's CLI."""
    if sys.platform != "win32":
        raise ValueError("The configured editor converter supports Windows only")
    root, source, output = Path(root).resolve(), Path(source).resolve(), Path(output).resolve()
    is_model = model_scale is not None
    input_types = (".obj", ".glb") if is_model else (".efkproj", ".efkefc")
    output_types = (".efkmodel",) if is_model else (".efkefc", ".efk")
    if not source.is_file() or source.suffix.lower() not in input_types:
        raise ValueError(f"Input must be an existing {' or '.join(input_types)} file")
    if output.suffix.lower() not in output_types:
        raise ValueError(f"Output must be {' or '.join(output_types)}")
    if is_model and (not math.isfinite(model_scale) or model_scale <= 0):
        raise ValueError("Model scale must be positive and finite")
    receipt_path = output.with_suffix(output.suffix + ".provenance.json")
    if output.exists() or receipt_path.exists():
        raise ValueError("Output/provenance already exists; choose a new revision path")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be positive and finite")
    status = doctor(root)
    if not status["components"]["editor"]["ready"]:
        raise ValueError("Pinned editor installation is missing/unverified; run install first")
    from asset_auto import resources

    # CUI conversion does not use CUDA or render. Apply shared CPU policy, not
    # a fictitious Blender runtime, GPU lease, or D3D adapter restriction.
    resolved = resources.resolve(root)
    applied = resources.apply_process_resources(root, resolved=resolved)
    env = os.environ.copy()
    threads = resolved["effective"].get("threads")
    if threads is not None:
        env.update({key: str(threads) for key in resources.THREAD_ENV})
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ([status["model_converter"], str(source), "-o", str(output), "-s", str(model_scale)]
               if is_model else [status["editor_cli"], "-cui", "-in", str(source),
                                 "-o" if output.suffix.lower() == ".efkefc" else "-e", str(output)])
    report = {"version": VERSION, "source_commit": COMMIT, "input": str(source),
              "input_sha256": sha256(source), "output": str(output), "command": command,
              "resources": applied, "state": "running", "rendered": False,
              "operation": "model_conversion" if is_model else "effect_conversion",
              "resource_notes": ["CPU-only conversion; no inference/GPU render was requested",
                                 "Thread environment settings are advisory; no native CUI thread flag",
                                 "GUI/WebGL adapter selection is not enforced by this converter"]}
    try:
        result = subprocess.run(command, cwd=runtime_dir(root) / EDITOR_DIR / "Tool",
                                env=env, capture_output=True, timeout=timeout, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        report.update(returncode=result.returncode, stdout=result.stdout.decode("utf-8", errors="replace"),
                      stderr=result.stderr.decode("utf-8", errors="replace"))
        if result.returncode != 0:
            raise ValueError(f"Effekseer conversion failed with code {result.returncode}")
        if not output.is_file():
            raise ValueError("Effekseer returned without creating output; see private provenance")
        validate_output(output)
        if output.suffix.lower() == ".efkefc":
            report["dependencies"] = dependencies(output)
            missing = [item["path"] for item in report["dependencies"] if not item["exists"]]
            if missing:
                raise ValueError(f"Converted effect has missing dependencies: {', '.join(missing)}")
            report["dependencies_checked"] = True
        else:
            report["dependencies_checked"] = False
        report.update(state="completed", output_sha256=sha256(output), output_bytes=output.stat().st_size)
    except Exception as error:
        report.update(state="failed", error=str(error))
        raise
    finally:
        receipt_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {key: report[key] for key in ("state", "output", "output_sha256", "output_bytes", "rendered")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install")
    setup.add_argument("--component", choices=("all", *ARTIFACTS), default="all")
    commands.add_parser("doctor")
    convert = commands.add_parser("export")
    convert.add_argument("--input", type=Path, required=True)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--timeout", type=float, default=120)
    model = commands.add_parser("model", help="Convert an existing OBJ/GLB mesh into Effekseer's model format")
    model.add_argument("--input", type=Path, required=True)
    model.add_argument("--output", type=Path, required=True)
    model.add_argument("--scale", type=float, default=1.0)
    model.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            result = install(args.root, args.component)
        elif args.command == "doctor":
            result = doctor(args.root)
        elif args.command == "export":
            result = export(args.root, args.input, args.output, args.timeout)
        else:
            result = export(args.root, args.input, args.output, args.timeout, model_scale=args.scale)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
