"""Optional bounded assessment of a completed asset, without changing its files."""

import hashlib
import shutil
import uuid
from pathlib import Path

from filelock import FileLock

from . import pipeline
from .models import AssessmentRequest, AssetUsage
from .settings import executable
from .store import now, read_json, write_json
from .usage import load_usage


def assess(root, request: AssessmentRequest):
    source, manifest, digest = pipeline.completed_source(root, request.asset_id, request.revision)
    directory = source.parent
    with FileLock(directory / "assessment.lock", timeout=0):
        usage = request.usage.model_dump() if request.usage is not None else load_usage(directory, digest)
        usage = usage or AssetUsage().model_dump()
        clips = manifest["inspection"].get("animations", {}).get("clips", [])
        inventory = {clip["name"]: clip for clip in clips}
        if len(inventory) != len(clips):
            raise ValueError("Ambiguous duplicate clip names; rename them in a new revision before assessment")
        missing = set(usage["clips"]) - set(inventory)
        if missing:
            raise ValueError(f"Usage names missing from final GLB: {sorted(missing)}")
        selected = request.clips if request.clips is not None else list(usage["clips"])
        if len(selected) > 16:
            raise ValueError("Select at most 16 clips per assessment; unselected clips remain untested")
        if set(selected) - set(usage["clips"]):
            raise ValueError("Each selected clip requires an explicit or inherited usage entry")
        if selected:
            executable(root, "blender")
        assessment_id = "q" + uuid.uuid4().hex[:12]
        out = directory / "assessments" / assessment_id
        out.mkdir(parents=True)
        worker_request = {"source": str(source), "output": str(out), "usage": usage,
                          "clips": {name: inventory[name] for name in selected},
                          "sample_rate": request.sample_rate, "max_samples_per_clip": request.max_samples_per_clip,
                          "render": request.render, "max_render_frames": request.max_render_frames,
                          "views": request.views}
        write_json(out / "request.json", request.model_dump())
        report = {"clips": {}, "targets": [], "rendered_frames": 0}
        if selected:
            # Isolate any importer behavior and record the actual assessed bytes.
            shutil.copy2(source, out / "input.glb")
            worker_request["source"] = str(out / "input.glb")
            if hashlib.sha256((out / "input.glb").read_bytes()).hexdigest() != digest:
                raise ValueError("Assessment input changed while being copied")
            write_json(out / "worker-request.json", worker_request)
            pipeline.run_logged([executable(root, "blender"), "--background", "--factory-startup", "--disable-autoexec",
                                 "--python-exit-code", "1", "--python", str(Path(__file__).with_name("blender_assessment_worker.py")),
                                 "--", str(out / "worker-request.json")], out / "blender.log", cwd=root)
            report = read_json(out / "report.json")
        _, _, final_digest = pipeline.completed_source(root, request.asset_id, request.revision)
        if final_digest != digest:
            raise ValueError("Completed GLB changed during assessment")
        report.update(asset_id=request.asset_id, revision=request.revision, assessment_id=assessment_id,
                      created_at=now(), source_sha256=digest, usage=usage, evidence_directory=str(out),
                      unassessed_clips=sorted(set(inventory) - set(selected)),
                      geometry_checks={"status": "passed" if manifest["inspection"]["passed"] else "failed",
                                       "evidence": "../../inspection.json", "scope": "Existing geometry inspection only"},
                      visual_review="pending", feature_review="pending" if usage["features"] else "not_applicable",
                      integration_review="untested",
                      requested_views=request.views,
                      limitations=["Sampling can miss changes between samples; increase rate for fast motion.",
                                   "No automatic contact/sliding, collision, center-of-mass or artistic quality verdict.",
                                   "Playback policies and target speed are intent, not engine configuration.",
                                   "Feature representation and free-text acceptance criteria require observed evidence."])
        write_json(out / "report.json", report)
        write_json(directory / "usage.json", {"version": 1, "source_sha256": digest, "usage": usage,
                                              "status": "declared", "assessment_id": assessment_id})
        write_json(directory / "assessment.json", report)
        return report
