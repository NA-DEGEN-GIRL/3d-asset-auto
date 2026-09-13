"""Immutable local Blender authoring and compatible GLB animation assembly."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from filelock import FileLock

from . import pipeline
from .models import AssetSpec, BlenderEditRequest, MergeAnimationsRequest
from .settings import executable
from .store import Store, child, read_json, write_json

MODELS = {"blender-edit": BlenderEditRequest, "merge-animations": MergeAnimationsRequest}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def binding(record):
    return hashlib.sha256(json.dumps(
        {key: value for key, value in record.items() if key != "binding_sha256"},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def snapshot(path, out, name, *, origin=None, expected=None):
    digest = sha256(path)
    if expected is not None and digest != expected:
        raise ValueError("Completed input changed; import the changed file as a new revision")
    target = out / name
    shutil.copy2(path, target)
    if sha256(target) != digest:
        raise ValueError("Input changed while it was being snapshotted")
    return {"file": name, "sha256": digest, "origin": origin}


def verify_inputs(root, out, record):
    for item in record["inputs"]:
        path = child(out, item["file"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError(f"Saved input snapshot changed: {item['file']}")
        if origin := item.get("origin"):
            source, manifest, _ = pipeline.completed_source(root, origin["asset_id"], origin["revision"])
            original = source.parent / origin["file"]
            if manifest["files"][origin["file"]]["sha256"] != item["sha256"] or sha256(original) != item["sha256"]:
                raise ValueError("Completed input changed after authoring was started")


def validate_resume(root, asset_id, revision, *, operation=None):
    out = child(root / ".assets", asset_id, revision)
    record = read_json(out / "authoring-request.json")
    saved_operation = record.get("operation")
    if saved_operation not in MODELS or operation is not None and operation != saved_operation:
        raise ValueError("Saved revision does not match this authoring operation")
    request = MODELS[saved_operation].model_validate(record["request"])
    if record.get("asset_id") != asset_id or request.asset_id != asset_id or record.get("revision") != revision:
        raise ValueError("Saved authoring request does not match the revision")
    if record.get("binding_sha256") != binding(record):
        raise ValueError("Saved authoring request binding changed")
    verify_inputs(root, out, record)
    return record


def start(root, request, operation, *, on_revision=None):
    source, parent, digest = pipeline.completed_source(root, request.asset_id, request.revision)
    executable(root, "blender")
    # Resolve every input before creating a partial revision.
    resolved = []
    if operation == "blender-edit":
        script = pipeline.input_path(root, request.script, {".py"})
        scene = source.parent / "source.blend"
        if sha256(scene) != parent["files"]["source.blend"]["sha256"]:
            raise ValueError("Source Blend changed after completion; import changes as a new revision first")
    else:
        for item in request.sources:
            if item.path:
                path = pipeline.input_path(root, item.path, {".glb"})
                pipeline.validate_glb(path)
                resolved.append((path, None, None))
            else:
                path, _, source_digest = pipeline.completed_source(root, item.asset_id, item.revision)
                resolved.append((path, {"asset_id": item.asset_id, "revision": item.revision, "file": "asset.glb"}, source_digest))
    revision, out = Store(root).new_revision(request.asset_id)
    origin = {"asset_id": request.asset_id, "revision": request.revision, "file": "asset.glb"}
    inputs = [snapshot(source, out, "input.glb", origin=origin, expected=digest)]
    if operation == "blender-edit":
        inputs.append(snapshot(scene, out, "input.blend", origin=origin | {"file": "source.blend"},
                               expected=parent["files"]["source.blend"]["sha256"]))
        inputs.append(snapshot(script, out, "script.py"))
    else:
        inputs.extend(snapshot(path, out, f"animation-{index}.glb", origin=source_origin, expected=expected)
                      for index, (path, source_origin, expected) in enumerate(resolved))
    record = {"operation": operation, "request": request.model_dump(), "asset_id": request.asset_id,
              "revision": revision, "inputs": inputs}
    record["binding_sha256"] = binding(record)
    write_json(out / "authoring-request.json", record)
    if on_revision:
        on_revision({"asset_id": request.asset_id, "revision": revision, "operation": f"resume-{operation}"})
    try:
        return resume_authoring(root, request.asset_id, revision, operation=operation)
    except Exception as error:
        raise RuntimeError(f"{error} (asset_id={request.asset_id}, revision={revision}; resume-{operation})") from error


def edit_in_blender(root, request: BlenderEditRequest, *, on_revision=None):
    return start(root, request, "blender-edit", on_revision=on_revision)


def merge_animations(root, request: MergeAnimationsRequest, *, on_revision=None):
    return start(root, request, "merge-animations", on_revision=on_revision)


def resume_authoring(root, asset_id, revision, *, operation=None):
    out = child(root / ".assets", asset_id, revision)
    with FileLock(out / "authoring.lock", timeout=0):
        record = validate_resume(root, asset_id, revision, operation=operation)
        if (out / "manifest.json").exists():
            return read_json(out / "manifest.json")
        operation = record["operation"]
        request = MODELS[operation].model_validate(record["request"])
        _, parent, _ = pipeline.completed_source(root, asset_id, request.revision)
        spec = AssetSpec.model_validate(parent["spec"])
        spec.triangle_budget = getattr(request, "triangle_budget", None) or parent["inspection"]["triangle_budget"]
        worker = {"output": str(out), "triangle_budget": spec.triangle_budget, "target_height": None,
                  "character": True, "require_rig": False, "rename_animation": False,
                  "preview_clips": request.preview_clips, "binding_sha256": record["binding_sha256"]}
        if operation == "blender-edit":
            worker.update(authoring=True, source=str(out / "input.blend"), script=str(out / "script.py"),
                          parameters=request.parameters, preserve_animations=request.preserve_animations,
                          require_animation=request.require_animation)
            pipeline.blender(root, worker, out)
            processing = read_json(out / "authoring.json")
        else:
            from .animation_merge import merge

            sources = [{"path": str(out / f"animation-{index}.glb"), "clips": item.clips, "rename": item.rename}
                       for index, item in enumerate(request.sources)]
            processing = merge(out / "input.glb", sources, out / "generated.glb", on_conflict=request.on_conflict)
            write_json(out / "animation-merge.json", processing)
            worker.update(operation="import", source=str(out / "generated.glb"), require_animation=True,
                          require_rig=bool(parent["inspection"].get("rigging", {}).get("armatures")),
                          preserve_input_glb=True)
            pipeline.blender(root, worker, out)
            if sha256(out / "asset.glb") != processing["output_sha256"]:
                raise ValueError("Final delivery GLB differs from the validated animation merge")
        # Scripts are trusted local code; detect accidental edits to any source
        # before publishing a completed revision.
        verify_inputs(root, out, record)
        processing.update(provider="local", operation=operation, description=request.description,
                          binding_sha256=record["binding_sha256"], inputs=record["inputs"])
        return pipeline.finalize(root, spec, revision, out, parent=request.revision, processing=processing)
