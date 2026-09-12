from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
from pathlib import Path

from filelock import FileLock

from .models import AssetSpec, EditRequest, PostprocessRequest
from .settings import executable, model_dir
from .store import Store, child, now, read_json, write_json


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
    worker = Path(__file__).with_name(
        "blender_character_worker.py" if request.get("character") else "blender_worker.py"
    )
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


def finalize(root, spec, revision, out, parent=None, edits=None, processing=None):
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
        "asset_type": "character" if report.get("rigging", {}).get("armatures") else "static",
    }
    if spec.provider == "tripo":
        checkpoint = out / "tripo.json"
        if parent:
            original = read_json(Store(root).revision(spec.asset_id, parent) / "manifest.json")
            manifest["remote_generation"] = original.get("remote_generation")
        elif checkpoint.exists():
            remote = read_json(checkpoint)
            manifest["remote_generation"] = {
                key: remote[key]
                for key in (
                    "api_version", "model", "task_id", "estimated_credits", "credits_consumed",
                    "max_credits", "budget_scope", "price_checked", "reported_over_budget",
                )
                if key in remote
            }
    if processing is not None:
        manifest["remote_processing"] = processing
    elif parent:
        original = read_json(Store(root).revision(spec.asset_id, parent) / "manifest.json")
        if original.get("remote_processing"):
            manifest["remote_processing"] = original["remote_processing"]
    for name in ("animation-previews.json", "part-previews.json"):
        if (out / name).is_file():
            manifest[name.removesuffix(".json").replace("-", "_")] = read_json(out / name)
    write_json(out / "manifest.json", manifest)
    return manifest


def generate(root: Path, spec: AssetSpec, *, on_revision=None):
    store = Store(root)
    revision, out = store.new_revision(spec.asset_id)
    if spec.provider == "tripo":
        write_json(out / "generation.json", {"provider": "tripo", "spec": spec.model_dump(), "started_at": now()})
        if on_revision is not None:
            on_revision({"asset_id": spec.asset_id, "revision": revision, "operation": "resume-tripo"})
        try:
            return finish_tripo(root, spec, revision, out)
        except Exception as error:
            raise RuntimeError(f"{error} (asset_id={spec.asset_id}, revision={revision})") from error
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
        if spec.asset_kind == "character":
            request.update(character=True, require_rig=True)
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
        lock_path = root / ".assets" / ".locks" / "trellis.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(lock_path, timeout=3600):
            run_logged(command, out / "trellis.log", timeout=3600, cwd=root)
        validate_glb(raw)
        request.update(operation="import", source=str(raw))
    blender(root, request, out)
    return finalize(root, spec, revision, out)


def finish_tripo(root, spec, revision, out, *, resume=False):
    from .tripo import generate as remote_generate

    with FileLock(out / "tripo.lock", timeout=0):
        if (out / "manifest.json").exists():
            return read_json(out / "manifest.json")
        # Check Blender availability before any paid submission.
        executable(root, "blender")
        remote_generate(root, spec, out, resume=resume)
        raw = out / "generated.glb"
        validate_glb(raw)
        blender(
            root,
            {"operation": "import", "source": str(raw), "output": str(out),
             "triangle_budget": spec.triangle_budget, "target_height": spec.target_height},
            out,
        )
        return finalize(root, spec, revision, out)


def resume_tripo(root, asset_id, revision):
    # Incomplete revisions intentionally have no manifest, so Store.revision cannot resolve them.
    out = child(root / ".assets", asset_id, revision)
    generation = read_json(out / "generation.json")
    if generation.get("provider") != "tripo":
        raise ValueError("Only an existing Tripo generation can be resumed")
    spec = AssetSpec.model_validate(generation["spec"])
    if spec.asset_id != asset_id or spec.provider != "tripo":
        raise ValueError("Stored Tripo request does not match this revision")
    return finish_tripo(root, spec, revision, out, resume=True)


def processing_source(root, request):
    source = Store(root).revision(request.asset_id, request.revision)
    manifest = read_json(source / "manifest.json")
    raw = source / "asset.glb"
    validate_glb(raw)
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    if manifest["files"]["asset.glb"]["sha256"] != digest:
        raise ValueError("Source GLB changed after completion; import changes as a new revision first")
    rigged = bool(manifest.get("inspection", {}).get("rigging", {}).get("armatures"))
    remote = manifest.get("remote_processing", {})
    if request.operation == "animate":
        if not rigged or remote.get("operation") not in ("rig", "animate") or not remote.get("rig_task_id"):
            raise ValueError("Animation requires a completed Tripo rig revision; run rig first")
    elif rigged:
        raise ValueError("Rigging and segmentation require a static source; use the preserved pre-rig revision")
    return raw, manifest, digest


def postprocess_plan(root, request):
    from .tripo_process import plan

    raw, manifest, digest = processing_source(root, request)
    return plan(request, manifest) | {
        "asset_id": request.asset_id, "source_revision": request.revision,
        "source_file": str(raw), "source_sha256": digest,
        "triangle_budget": request.triangle_budget or manifest["inspection"]["triangle_budget"],
    }


def postprocess(root, request: PostprocessRequest, *, on_revision=None):
    _, _, digest = processing_source(root, request)
    executable(root, "blender")
    revision, out = Store(root).new_revision(request.asset_id)
    write_json(out / "processing.json", {"request": request.model_dump(), "source_sha256": digest})
    if on_revision:
        on_revision({"asset_id": request.asset_id, "revision": revision, "operation": "resume-tripo-process"})
    try:
        return finish_postprocess(root, request, revision, out)
    except Exception as error:
        raise RuntimeError(f"{error} (asset_id={request.asset_id}, revision={revision})") from error


def finish_postprocess(root, request, revision, out, *, resume=False):
    from .tripo_process import process

    with FileLock(out / "postprocess.lock", timeout=0):
        if (out / "manifest.json").exists():
            return read_json(out / "manifest.json")
        source, parent, digest = processing_source(root, request)
        if read_json(out / "processing.json")["source_sha256"] != digest:
            raise ValueError("Processing source changed; cannot resume against different geometry")
        executable(root, "blender")
        remote = process(root, request, out, source, parent, resume=resume)
        spec = AssetSpec.model_validate(parent["spec"])
        budget = request.triangle_budget or parent["inspection"]["triangle_budget"]
        spec.triangle_budget = budget
        character = request.operation in ("rig", "animate")
        worker_request = {
            "operation": "import", "source": str(out / "generated.glb"), "output": str(out),
            "triangle_budget": budget, "target_height": parent["inspection"]["dimensions"][2],
            "character": character, "require_rig": character,
            "require_animation": request.operation == "animate", "part_previews": not character,
        }
        if character:
            worker_request["input_yaw_degrees"] = remote.get("output_yaw_degrees", 0)
        if request.operation == "animate":
            worker_request["animation_name"] = request.animation
        blender(root, worker_request, out)
        report = read_json(out / "inspection.json")
        if request.operation == "segment":
            report["segmentation"] = {
                "model": "v2.0-20260430", "parts": len(report["parts"]),
                "semantic_review": "pending", "source_revision": request.revision,
            }
            if len(report["parts"]) < 2:
                report["errors"].append("Segmentation returned fewer than two mesh parts")
                report["passed"] = False
            write_json(out / "inspection.json", report)
        return finalize(root, spec, revision, out, parent=request.revision, processing=remote)


def resume_postprocess(root, asset_id, revision):
    out = child(root / ".assets", asset_id, revision)
    request = PostprocessRequest.model_validate(read_json(out / "processing.json")["request"])
    if request.asset_id != asset_id:
        raise ValueError("Stored processing request does not match asset")
    return finish_postprocess(root, request, revision, out, resume=True)


def edit_asset(root: Path, change: EditRequest):
    store = Store(root)
    source = store.revision(change.asset_id, change.revision)
    parent = read_json(source / "manifest.json")
    if parent.get("inspection", {}).get("rigging", {}).get("armatures"):
        raise ValueError("Static part edits cannot modify a rigged asset; edit its static parent and rig a new revision")
    spec = AssetSpec.model_validate(parent["spec"])
    revision, out = store.new_revision(change.asset_id)
    request = {
        "operation": "edit",
        "source": str(source / "source.blend"),
        "output": str(out),
        "triangle_budget": spec.triangle_budget,
        "changes": [c.model_dump() for c in change.changes],
        "part_previews": bool(parent.get("inspection", {}).get("segmentation") or parent.get("part_previews")),
    }
    blender(root, request, out)
    if parent.get("inspection", {}).get("segmentation"):
        report = read_json(out / "inspection.json")
        report["segmentation"] = parent["inspection"]["segmentation"] | {
            "semantic_review": "pending", "parts": len(report["parts"]),
        }
        write_json(out / "inspection.json", report)
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
