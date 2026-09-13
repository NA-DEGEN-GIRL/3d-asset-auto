"""Add or replace one local preset while retaining the source GLB's other clips."""

import hashlib
from pathlib import Path

from .settings import executable
from .store import read_json, write_json


def generate(root, request, out, source_glb):
    from .pipeline import run_logged, validate_glb

    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": str(source_glb), "output": str(out),
        "animation": request.animation,
        "bone_map": getattr(request, "bone_map", None) or {},
        "rig_forward_axis": request.rig_forward_axis,
        "animate_in_place": request.animate_in_place,
    }
    path = out / "local-motion-request.json"
    write_json(path, payload)
    run_logged([
        executable(root, "blender"), "--background", "--factory-startup", "--disable-autoexec",
        "--python-exit-code", "1", "--python",
        str(Path(__file__).with_name("blender_motion_worker.py")), "--", str(path),
    ], out / "local-motion.log", cwd=root)
    validate_glb(out / "generated.glb")
    report = read_json(out / "local-motion.json")
    report["source_sha256"] = hashlib.sha256(source_glb.read_bytes()).hexdigest()
    report["generated_sha256"] = hashlib.sha256((out / "generated.glb").read_bytes()).hexdigest()
    write_json(out / "local-motion.json", report)
    return report
