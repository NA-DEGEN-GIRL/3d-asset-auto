from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
from pathlib import Path

from .models import AssetSpec, EditRequest
from .settings import executable, model_dir
from .store import Store, now, read_json, write_json


def run_logged(command, log, timeout=900, cwd=None):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with log.open("wb") as stream:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=flags,
            check=False,
        )
    if result.returncode:
        tail = log.read_text(encoding="utf-8", errors="replace")[-5000:]
        raise RuntimeError(f"Process failed ({result.returncode}); log: {log}\n{tail}")


def validate_glb(path):
    with path.open("rb") as stream:
        header = stream.read(12)
    if len(header) != 12:
        raise ValueError("Truncated GLB")
    magic, version, length = struct.unpack("<4sII", header)
    if magic != b"glTF" or version != 2 or length != path.stat().st_size:
        raise ValueError("Invalid GLB 2.0 header or length")


def input_path(root, value, suffixes):
    path = Path(value).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_file() or path.suffix.lower() not in suffixes:
        raise ValueError(f"Expected an existing {sorted(suffixes)} input: {path}")
    return path


def blender(root, request, out):
    write_json(out / "worker-request.json", request)
    worker = Path(__file__).with_name("blender_worker.py")
    run_logged(
        [
            executable(root, "blender"),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            str(worker),
            "--",
            str(out / "worker-request.json"),
        ],
        out / "blender.log",
        cwd=root,
    )
    validate_glb(out / "asset.glb")
    for name in (
        "source.blend",
        "inspection.json",
        "front.png",
        "back.png",
        "left.png",
        "right.png",
        "perspective.png",
    ):
        if not (out / name).is_file():
            raise RuntimeError(f"Worker did not produce {name}")


def finalize(root, spec, revision, out, parent=None, edits=None):
    report = read_json(out / "inspection.json")
    files = {}
    for name in ("asset.glb", "source.blend"):
        with (out / name).open("rb") as stream:
            files[name] = {
                "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                "bytes": (out / name).stat().st_size,
            }
    installed = {}
    for name in ("blender", "trellis", "models"):
        path = root / ".runtime" / "installed" / f"{name}.json"
        if path.exists() and (name == "blender" or spec.provider == "trellis"):
            installed[name] = read_json(path)
    manifest = {
        "asset_id": spec.asset_id,
        "revision": revision,
        "parent": parent,
        "created_at": now(),
        "provider": spec.provider,
        "prompt": spec.prompt,
        "state": "numeric_checks_passed" if report["passed"] else "needs_repair",
        "visual_review": "pending",
        "engine_validation": "pending",
        "spec": spec.model_dump(),
        "edits": edits,
        "inspection": report,
        "files": files,
        "toolchain": installed,
        "coordinate_system": "glTF Y-up, meters",
        "renders": [f"{v}.png" for v in ("front", "back", "left", "right", "perspective")],
    }
    write_json(out / "manifest.json", manifest)
    return manifest


def generate(root: Path, spec: AssetSpec):
    store = Store(root)
    revision, out = store.new_revision(spec.asset_id)
    request = {
        "output": str(out),
        "triangle_budget": spec.triangle_budget,
        "target_height": spec.target_height,
    }
    if spec.provider == "procedural":
        request.update(operation="create", recipe=spec.recipe.model_dump())
    elif spec.provider == "import":
        source = input_path(root, spec.source, {".glb", ".blend"})
        shutil.copy2(source, out / ("input" + source.suffix.lower()))
        request.update(operation="import", source=str(out / ("input" + source.suffix.lower())))
    else:
        source = input_path(root, spec.image, {".png", ".jpg", ".jpeg", ".webp"})
        reference = out / ("reference" + source.suffix.lower())
        shutil.copy2(source, reference)
        raw = out / "generated.glb"
        command = [
            executable(root, "trellis"),
            str(reference),
            str(raw),
            "--models",
            str(model_dir(root)),
            "--res",
            str(spec.resolution),
            "--atlas",
            str(spec.atlas),
            "--seed",
            str(spec.seed),
            "--require-gpu",
            "--webp",
            "off",
        ]
        write_json(out / "generation.json", {"command": command, "started_at": now()})
        run_logged(command, out / "trellis.log", timeout=3600, cwd=root)
        validate_glb(raw)
        request.update(operation="import", source=str(raw))
    blender(root, request, out)
    return finalize(root, spec, revision, out)


def edit_asset(root: Path, change: EditRequest):
    store = Store(root)
    source = store.revision(change.asset_id, change.revision)
    parent = read_json(source / "manifest.json")
    spec = AssetSpec.model_validate(parent["spec"])
    revision, out = store.new_revision(change.asset_id)
    request = {
        "operation": "edit",
        "source": str(source / "source.blend"),
        "output": str(out),
        "triangle_budget": spec.triangle_budget,
        "changes": [c.model_dump() for c in change.changes],
    }
    blender(root, request, out)
    return finalize(root, spec, revision, out, parent=change.revision, edits=change.model_dump())


def review(root, asset_id, revision, passed, notes):
    if not notes.strip():
        raise ValueError("Visual review requires specific observations")
    directory = Store(root).revision(asset_id, revision)
    record = {"passed": passed, "notes": notes, "reviewed_at": now()}
    write_json(directory / "review.json", record)
    return record


def validate_godot(root, asset_id, revision):
    directory = Store(root).revision(asset_id, revision)
    project = directory / "godot"
    project.mkdir(exist_ok=True)
    shutil.copy2(directory / "asset.glb", project / "asset.glb")
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Asset validation"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
        encoding="utf-8",
    )
    script = Path(__file__).with_name("godot_validate.gd")
    shutil.copy2(script, project / "validate.gd")
    godot = executable(root, "godot")
    run_logged(
        [godot, "--headless", "--path", str(project), "--editor", "--import"],
        directory / "godot-import.log",
        timeout=180,
    )
    run_logged(
        [godot, "--headless", "--path", str(project), "--script", "res://validate.gd"],
        directory / "godot-test.log",
        timeout=120,
    )
    result = read_json(project / "validation.json")
    result["tested_at"] = now()
    result["scope"] = "GLB import, instantiation, mesh/material and convex-collision checks; not gameplay"
    write_json(directory / "godot.json", result)
    return result
