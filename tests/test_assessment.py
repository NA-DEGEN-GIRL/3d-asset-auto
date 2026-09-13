import asyncio
import hashlib
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from asset_auto import assessment, cli, jobs, usage
from asset_auto.models import AssessmentRequest, AssetUsage
from asset_auto.store import read_json, write_json


def asset(root, name="prop", revision="r1", clips=()):
    out = root / ".assets" / name / revision
    out.mkdir(parents=True)
    payload = json.dumps({"asset": {"version": "2.0"}}).encode()
    payload += b" " * (-len(payload) % 4)
    raw = struct.pack("<4sII", b"glTF", 2, 20 + len(payload)) + struct.pack("<I4s", len(payload), b"JSON") + payload
    (out / "asset.glb").write_bytes(raw)
    (out / "source.blend").write_bytes(b"unchanged scene")
    report = {"asset_id": name, "revision": revision, "files": {"asset.glb": {"sha256": hashlib.sha256(raw).hexdigest()}},
              "inspection": {"passed": True, "animations": {"clips": [
                  {"name": clip, "start_seconds": 0, "end_seconds": 1} for clip in clips]}}}
    write_json(out / "manifest.json", report)
    return out, report


def test_static_usage_does_not_start_blender_and_keeps_feature_claims_pending(tmp_path, monkeypatch):
    out, manifest = asset(tmp_path)
    original = {name: (out / name).read_bytes() for name in ("source.blend", "asset.glb", "manifest.json")}
    monkeypatch.setattr(assessment, "executable", lambda *args: pytest.fail("Static intent needs no Blender"))
    request = AssessmentRequest(asset_id="prop", revision="r1", usage=AssetUsage.model_validate({
        "purpose": "Decorative wall fitting", "features": [{"name": "surface", "representation": "thin shell",
        "intended_behavior": "viewed from the front", "acceptance": ["No visible gaps at intended angles"]}]}))
    result = assessment.assess(tmp_path, request)
    assert result["feature_review"] == "pending" and result["visual_review"] == "pending"
    assert result["rendered_frames"] == 0 and result["clips"] == {}
    assert all((out / name).read_bytes() == raw for name, raw in original.items())
    assert usage.load_usage(out, manifest["files"]["asset.glb"]["sha256"])["features"][0]["representation"] == "thin shell"


def test_unconfigured_clips_are_not_inferred_or_approved(tmp_path):
    asset(tmp_path, clips=["arbitrary"])
    result = assessment.assess(tmp_path, AssessmentRequest(asset_id="prop", revision="r1"))
    assert result["unassessed_clips"] == ["arbitrary"]
    assert result["integration_review"] == "untested"


def test_wrong_clip_usage_and_stale_glb_contract_are_rejected(tmp_path):
    out, manifest = asset(tmp_path, clips=["move"])
    with pytest.raises(ValueError, match="missing"):
        assessment.assess(tmp_path, AssessmentRequest(asset_id="prop", revision="r1", usage={"clips": {"other": {}}}))
    write_json(out / "usage.json", {"source_sha256": "stale", "usage": {}})
    with pytest.raises(ValueError, match="different GLB"):
        usage.load_usage(out, manifest["files"]["asset.glb"]["sha256"])
    result = assessment.assess(tmp_path, AssessmentRequest(asset_id="prop", revision="r1", usage={}))
    assert result["unassessed_clips"] == ["move"]


def test_failed_assessment_preserves_previous_contract_and_completed_files(tmp_path, monkeypatch):
    out, manifest = asset(tmp_path, clips=["move"])
    stored = {"source_sha256": manifest["files"]["asset.glb"]["sha256"], "usage": {"purpose": "old"}}
    write_json(out / "usage.json", stored)
    monkeypatch.setattr(assessment, "executable", lambda *args: "blender")

    def fail(*args, **kwargs):
        raise RuntimeError("Renderer failed")

    monkeypatch.setattr(assessment.pipeline, "run_logged", fail)
    with pytest.raises(RuntimeError, match="Renderer"):
        assessment.assess(tmp_path, AssessmentRequest(asset_id="prop", revision="r1", usage={"clips": {"move": {}}}))
    assert read_json(out / "usage.json") == stored and not (out / "assessment.json").exists()
    assert read_json(out / "manifest.json") == manifest


def test_merge_transfers_renamed_policy_but_not_evidence_and_drops_unknown_replacement(tmp_path):
    base, base_manifest = asset(tmp_path, clips=["move", "keep"])
    donor, donor_manifest = asset(tmp_path, "donor", clips=["slide"])
    new, new_manifest = asset(tmp_path, revision="r2", clips=["move", "keep", "renamed"])
    for folder, manifest, contract in (
        (base, base_manifest, {"purpose": "fixture", "clips": {"move": {"playback": "loop"}, "keep": {"playback": "hold"}}}),
        (donor, donor_manifest, {"clips": {"slide": {"playback": "once", "events": [{"name": "stop", "time_seconds": .5}]}}}),
    ):
        write_json(folder / "usage.json", {"source_sha256": manifest["files"]["asset.glb"]["sha256"], "usage": contract})
    processing = {"operation": "merge-animations", "sources": [
        {"clips": [{"source": "slide", "name": "renamed"}]}, {"clips": [{"source": "unknown", "name": "move"}]}],
        "inputs": [{}, {"origin": {"asset_id": "donor", "revision": "r1"}, "sha256": donor_manifest["files"]["asset.glb"]["sha256"]},
                   {"origin": None}]}
    usage.inherit(tmp_path, new, new_manifest, "r1", processing)
    inherited = read_json(new / "usage.json")
    assert set(inherited["usage"]["clips"]) == {"keep", "renamed"}
    assert inherited["usage"]["clips"]["renamed"]["playback"] == "once"
    assert inherited["status"] == "inherited_requires_reassessment"
    assert not (new / "assessment.json").exists()


@pytest.mark.parametrize("background", [False, True])
def test_cli_and_jobs_assess_same_validated_request(tmp_path, monkeypatch, capsys, background):
    asset(tmp_path)
    spec = tmp_path / "request.json"
    write_json(spec, {"asset_id": "prop", "revision": "r1", "usage": {"purpose": "test"}})
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=123))
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), "assess", str(spec)] + (["--async"] if background else []))
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    if background:
        result = jobs.run(tmp_path, result["job_id"])["result"]
    assert result["usage"]["purpose"] == "test" and result["source_sha256"]


def test_mcp_assessment_uses_job_api_and_keeps_full_evidence(tmp_path, monkeypatch):
    from asset_auto.mcp_server import build_server

    calls = []
    monkeypatch.setattr(jobs, "submit", lambda root, operation, payload: calls.append((root, operation, payload)) or {"job_id": "j"})
    server = build_server(tmp_path)
    payload = {"asset_id": "prop", "revision": "r1", "usage": {"purpose": "test"}}
    asyncio.run(server.call_tool("assess_asset", {"request": payload}))
    assert calls == [(tmp_path, "assess", payload)]


def test_motion_worker_uses_snapshot_and_explicit_budget(tmp_path, monkeypatch):
    out, _ = asset(tmp_path, clips=["move", "other"])
    monkeypatch.setattr(assessment, "executable", lambda *args: "blender")

    def worker(command, log, **kwargs):
        request = read_json(Path(command[-1]))
        directory = Path(request["output"])
        assert Path(request["source"]) == directory / "input.glb"
        assert request["max_render_frames"] == 3 and request["sample_rate"] == 24
        write_json(directory / "report.json", {"clips": {"move": {"numeric_status": "failed"}}, "rendered_frames": 3})

    monkeypatch.setattr(assessment.pipeline, "run_logged", worker)
    result = assessment.assess(tmp_path, AssessmentRequest(asset_id="prop", revision="r1", usage={"clips": {"move": {}}},
                                                          sample_rate=24, max_render_frames=3))
    assert result["clips"]["move"]["numeric_status"] == "failed"
    assert result["unassessed_clips"] == ["other"]
    assert (out / "manifest.json").exists()
