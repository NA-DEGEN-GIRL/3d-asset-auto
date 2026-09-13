"""Learned text motion on an existing rig, with resumable immutable revisions."""

import shutil
from itertools import pairwise
from pathlib import Path

from filelock import FileLock

from . import authoring, kimodo_runtime, pipeline
from .models import AssetSpec, KimodoMotionRequest
from .settings import executable
from .store import Store, child, read_json, write_json

REQUIRED_JOINTS = {"Hips", "Chest", "Head", "LeftArm", "LeftForeArm", "LeftHand", "RightArm",
                   "RightForeArm", "RightHand", "LeftLeg", "LeftShin", "LeftFoot", "RightLeg",
                   "RightShin", "RightFoot"}


def plan(root, request: KimodoMotionRequest):
    _source, manifest, digest = pipeline.completed_source(root, request.asset_id, request.revision)
    rigging = manifest["inspection"].get("rigging", {})
    rigs = rigging.get("armatures", [])
    if len(rigs) != 1 or not rigging.get("weighted_vertices"):
        raise ValueError("Text motion requires one existing humanoid armature with weighted mesh vertices")
    if rigging.get("unweighted_vertices"):
        raise ValueError("Repair unweighted mesh vertices before generating text motion")
    names = {bone["name"] for bone in rigs[0]["bones"]}
    if missing := REQUIRED_JOINTS - set(request.bone_map):
        raise ValueError(f"Supply observed SOMA-to-target mapping for {sorted(missing)}")
    if unknown := set(request.bone_map) - kimodo_runtime.SOMA_JOINTS:
        raise ValueError(f"Unknown SOMA joints in mapping: {sorted(unknown)}")
    if missing := set(request.bone_map.values()) - names:
        raise ValueError(f"Mapped target bones do not exist: {sorted(missing)}")
    parents = {bone["name"]: bone.get("parent") for bone in rigs[0]["bones"]}
    chains = [("Hips", "Chest", "Head")] + [
        ("Chest", side + "Arm", side + "ForeArm", side + "Hand") for side in ("Left", "Right")
    ] + [("Hips", side + "Leg", side + "Shin", side + "Foot") for side in ("Left", "Right")]
    for chain in chains:
        for ancestor, descendant in pairwise(chain):
            current, seen = parents[request.bone_map[descendant]], set()
            while current is not None and current != request.bone_map[ancestor]:
                if current in seen or current not in parents:
                    raise ValueError("Target rig hierarchy is incomplete or cyclic")
                seen.add(current)
                current = parents[current]
            if current is None:
                raise ValueError(f"Mapped {ancestor}/{descendant} order does not follow target hierarchy")
    clips = {clip["name"] for clip in manifest["inspection"].get("animations", {}).get("clips", [])}
    if request.clip_name in clips:
        raise ValueError("Clip name already exists; choose a new name or explicitly edit the existing clip")
    backend = kimodo_runtime.capability(root)
    executable(root, "blender")
    return {"asset_id": request.asset_id, "revision": request.revision, "source_sha256": digest,
            "backend": backend, "ready": backend["available"], "model": kimodo_runtime.MODEL_NAME,
            "target_rig": rigs[0]["name"], "bone_map": request.bone_map,
            "unmapped_target_bones": sorted(names - set(request.bone_map.values())),
            "preserved_clips": sorted(clips), "new_clip": request.clip_name,
            "limitations": ["Humanoid rotation transfer with reference alignment; not a general IK retarget solver.",
                            "Looping, object contact and target foot placement need separate review/correction."]}


def validate_resume(root, asset_id, revision):
    out = child(root / ".assets", asset_id, revision)
    record = read_json(out / "motion-request.json")
    request = KimodoMotionRequest.model_validate(record["request"])
    if request.asset_id != asset_id or record.get("revision") != revision or record.get("operation") != "text-motion":
        raise ValueError("Saved text motion does not match this asset/revision")
    if record.get("binding_sha256") != authoring.binding(record):
        raise ValueError("Saved text motion request binding changed")
    authoring.verify_inputs(root, out, record)
    return record


def generate(root, request: KimodoMotionRequest, *, on_revision=None):
    checked = plan(root, request)
    installed = kimodo_runtime.installation(root)
    source, parent, digest = pipeline.completed_source(root, request.asset_id, request.revision)
    revision, out = Store(root).new_revision(request.asset_id)
    origin = {"asset_id": request.asset_id, "revision": request.revision, "file": "asset.glb"}
    inputs = [authoring.snapshot(source, out, "input.glb", origin=origin, expected=digest),
              authoring.snapshot(source.parent / "source.blend", out, "input.blend",
                                 origin=origin | {"file": "source.blend"}, expected=parent["files"]["source.blend"]["sha256"]),
              authoring.snapshot(Path(__file__).with_name("blender_kimodo_retarget.py"), out, "retarget.py"),
              authoring.snapshot(root / "scripts/kimodo/infer.py", out, "infer.py")]
    record = {"operation": "text-motion", "asset_id": request.asset_id, "revision": revision,
              "request": request.model_dump(), "inputs": inputs, "plan": checked,
              "installation": {key: installed[key] for key in ("source_revision", "models", "dependency_freeze_sha256")}}
    record["binding_sha256"] = authoring.binding(record)
    write_json(out / "motion-request.json", record)
    if on_revision:
        on_revision({"asset_id": request.asset_id, "revision": revision, "operation": "resume-text-motion"})
    try:
        return resume(root, request.asset_id, revision)
    except Exception as error:
        raise RuntimeError(f"{error} (asset_id={request.asset_id}, revision={revision}; resume-text-motion)") from error


def inference_record(out, binding):
    record = read_json(out / "kimodo-inference.json")
    if record.get("binding_sha256") != binding or record.get("backend") != "kimodo" or not record.get("learned_inference"):
        raise ValueError("Saved Kimodo inference is not bound to this request")
    if {item["file"] for item in record["files"]} != {"motion-data.json", "motion.npz", "motion.bvh"}:
        raise ValueError("Kimodo output inventory is incomplete")
    for item in record["files"]:
        if kimodo_runtime.sha256(child(out, item["file"])) != item["sha256"]:
            raise ValueError("Saved Kimodo output changed; start a new revision for changes")
    return record


def merge_generated_clip(out, clip_name):
    """Keep original GLB samplers even when its editable Blend uses another FPS."""
    from .animation_merge import merge

    shutil.copyfile(out / "asset.glb", out / "retargeted.glb")
    result = merge(out / "input.glb", [{"path": str(out / "retargeted.glb"), "clips": [clip_name]}],
                   out / "generated.glb")
    write_json(out / "animation-merge.json", result)
    return result


def resume(root, asset_id, revision):
    out = child(root / ".assets", asset_id, revision)
    with FileLock(out / "motion.lock", timeout=0):
        record = validate_resume(root, asset_id, revision)
        if (out / "manifest.json").exists():
            return read_json(out / "manifest.json")
        request = KimodoMotionRequest.model_validate(record["request"])
        if not (out / "kimodo-inference.json").exists():
            installed = kimodo_runtime.installation(root)
            if record["installation"] != {key: installed[key] for key in record["installation"]}:
                raise ValueError("Kimodo installation changed since submission; reconcile before resuming")
            lock = root / ".assets/.locks/trellis.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            command = kimodo_runtime.worker_command(root, out / "infer.py", out / "motion-request.json", installed)
            with FileLock(lock, timeout=3600):
                pipeline.run_logged(command, out / "kimodo.log", timeout=3600, cwd=root)
        inference = inference_record(out, record["binding_sha256"])
        _, parent, _ = pipeline.completed_source(root, asset_id, request.revision)
        spec = AssetSpec.model_validate(parent["spec"])
        worker = {"authoring": True, "source": str(out / "input.blend"), "output": str(out),
                  "script": str(out / "retarget.py"), "parameters": request.model_dump(),
                  "preserve_animations": True, "require_animation": True, "require_rig": True,
                  "character": True, "target_height": None, "rename_animation": False,
                  "preview_clips": [request.clip_name], "triangle_budget": parent["inspection"]["triangle_budget"],
                  "binding_sha256": record["binding_sha256"]}
        pipeline.blender(root, worker, out)
        merged = merge_generated_clip(out, request.clip_name)
        if (out / "blender.log").is_file():
            shutil.copyfile(out / "blender.log", out / "retarget-blender.log")
        # The authoring checkpoint remains available for export recovery. Inspect
        # the merged bytes without baking the parent's clips a second time.
        delivery = {"operation": "import", "source": str(out / "generated.glb"), "output": str(out),
                    "character": True, "require_rig": True, "require_animation": True,
                    "target_height": None, "rename_animation": False, "preserve_input_glb": True,
                    "preview_clips": [request.clip_name], "triangle_budget": parent["inspection"]["triangle_budget"]}
        pipeline.blender(root, delivery, out)
        if authoring.sha256(out / "asset.glb") != merged["output_sha256"]:
            raise ValueError("Final Kimodo GLB differs from the validated clip merge")
        authoring.verify_inputs(root, out, record)
        inference_record(out, record["binding_sha256"])
        processing = read_json(out / "authoring.json")
        processing.update(provider="local", backend="kimodo", operation="text-motion",
                          description=request.description, motion_request=request.model_dump(),
                          learned_inference=inference, retarget=read_json(out / "retarget-map.json"),
                          animation_merge=merged,
                          inputs=record["inputs"], binding_sha256=record["binding_sha256"])
        return pipeline.finalize(root, spec, revision, out, parent=request.revision, processing=processing)
