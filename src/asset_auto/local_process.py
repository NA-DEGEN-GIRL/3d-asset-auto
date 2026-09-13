"""Local postprocessing dispatch, with immutable inputs and recoverable model outputs."""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path

from filelock import FileLock

from .store import now, read_json, write_json

BACKENDS = {"rig": "skintokens", "animate": "procedural-biped-ik-v1", "segment": "geosam2"}


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plan(root, request, source_manifest=None):
    if request.provider != "local":
        raise ValueError("Local processing requires provider: local")
    result = {
        "provider": "local", "operation": request.operation, "backend": BACKENDS[request.operation],
        "estimated_credits": 0, "paid": False, "inference_network_required": False,
        "model_installation_may_require_download": request.operation != "animate",
    }
    if request.operation == "rig":
        from .local_rig import capability

        result["installation"] = capability(root)
    elif request.operation == "segment":
        from .local_parts import _context, available

        result["installation"] = available(root)
        if source_manifest is not None:
            from .store import Store

            source = Store(root).revision(request.asset_id, request.revision) / "asset.glb"
            context_path, context = _context(request.segmentation_context, source, root=root)
            result["context_source_sha256"] = context["source_sha256"]
            result["context"] = str(context_path)
        result.update(seed_view=request.segmentation_view,
                      prompted_parts=[part.name for part in request.segmentation_parts])
        result.setdefault("context", request.segmentation_context)
    else:
        from .settings import executable

        try:
            result["installation"] = {"available": True, "blender": executable(root, "blender")}
        except FileNotFoundError as error:
            result["installation"] = {"available": False, "reason": str(error)}
        result.update(animation=request.animation, bone_map=request.bone_map,
                      bone_mapping="explicit observed map or recognized bone names",
                      motion_method="local procedural inverse kinematics; not captured motion")
    return result


def process(root, request, out, source_glb, source_manifest, *, resume=False):
    if request.provider != "local":
        raise ValueError("Local processing requires provider: local")
    root, out, source_glb = Path(root), Path(out), Path(source_glb)
    binding = {"source_sha256": _sha(source_glb), "request": request.model_dump()}
    if request.operation == "segment":
        from .local_parts import _context

        context_path, _ = _context(request.segmentation_context, source_glb, root=root)
        binding["context_sha256"] = _sha(context_path)
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    checkpoint = out / "local-process.json"
    if checkpoint.exists():
        record = read_json(checkpoint)
        if record.get("binding_sha256") != digest:
            raise ValueError("Local processing source, request or prepared context changed")
        if record.get("state") == "generated":
            name = record.get("generated_file")
            if name not in ("generated.glb", "generated.blend"):
                raise ValueError("Invalid recorded local output")
            if not (out / name).is_file() or _sha(out / name) != record.get("generated_sha256"):
                raise ValueError("Recorded local output changed or is missing")
            return record
        if not resume:
            raise ValueError("Local processing already started; use resume-process for this revision")
    record = {
        "provider": "local", "operation": request.operation, "backend": BACKENDS[request.operation],
        "binding_sha256": digest, "source_sha256": binding["source_sha256"],
        "credits_consumed": 0, "state": "running", "started_at": now(),
    }
    write_json(checkpoint, record)
    lock_path = root / ".assets" / ".locks" / "trellis.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(lock_path, timeout=3600) if request.operation in ("rig", "segment") else nullcontext()
    with lock:
        if request.operation == "rig":
            from .local_rig import generate

            result = generate(root, request, out, source_glb)
        elif request.operation == "animate":
            from .local_motion import generate

            result = generate(root, request, out, source_glb)
        else:
            from .local_parts import segment

            result = segment(root, request, out, source_glb)
    name = result.get("generated_file", "generated.glb")
    if name not in ("generated.glb", "generated.blend") or not (out / name).is_file():
        raise RuntimeError("Local backend did not produce its recorded output")
    if _sha(source_glb) != binding["source_sha256"]:
        raise RuntimeError("Local backend changed its completed source asset")
    record.update(result)
    record.update(provider="local", operation=request.operation, state="generated", credits_consumed=0,
                  binding_sha256=digest, source_sha256=binding["source_sha256"],
                  generated_file=name, generated_sha256=_sha(out / name), finished_at=now())
    write_json(checkpoint, record)
    return record
