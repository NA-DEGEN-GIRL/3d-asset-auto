"""Text-motion request, immutable checkpoint and interface contracts; no inference/API."""

import asyncio
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from asset_auto import authoring, cli, jobs, kimodo_runtime, pipeline, text_motion
from asset_auto.models import AssetSpec, KimodoMotionRequest
from asset_auto.store import read_json, write_json


def request(**changes):
    return KimodoMotionRequest.model_validate({
        "asset_id": "person", "revision": "r-original", "prompt": "A person waves with one arm.",
        "clip_name": "wave", "bone_map": {name: name for name in text_motion.REQUIRED_JOINTS},
    } | changes)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    out = tmp_path / ".assets/person/r-original"
    out.mkdir(parents=True)
    data = json.dumps({"asset": {"version": "2.0"}}).encode()
    data += b" " * (-len(data) % 4)
    (out / "asset.glb").write_bytes(struct.pack("<4sII", b"glTF", 2, 20 + len(data)) +
                                  struct.pack("<I4s", len(data), b"JSON") + data)
    (out / "source.blend").write_bytes(b"source scene")
    parents = {"Hips": None, "Chest": "Hips", "Head": "Chest"}
    for side in ("Left", "Right"):
        parents.update({side + "Arm": "Chest", side + "ForeArm": side + "Arm", side + "Hand": side + "ForeArm",
                        side + "Leg": "Hips", side + "Shin": side + "Leg", side + "Foot": side + "Shin"})
    write_json(out / "manifest.json", {
        "asset_id": "person", "revision": "r-original", "provider": "trellis",
        "spec": AssetSpec(asset_id="person", image="ref.png").model_dump(),
        "files": {name: {"sha256": authoring.sha256(out / name)} for name in ("asset.glb", "source.blend")},
        "inspection": {"triangle_budget": 12000, "animations": {"clips": [{"name": "idle"}]},
                       "rigging": {"weighted_vertices": 8, "unweighted_vertices": 0,
                                   "armatures": [{"name": "rig", "bones": [{"name": name, "parent": parent}
                                                                            for name, parent in parents.items()]}]}},
    })
    script = tmp_path / "scripts/kimodo/infer.py"
    script.parent.mkdir(parents=True)
    script.write_text("# mock worker", encoding="utf-8")
    installed = {"source_revision": kimodo_runtime.SOURCE_REV,
                 "models": {name: {"repository": repo, "revision": rev}
                            for name, (repo, rev) in kimodo_runtime.MODEL_PINS.items()},
                 "dependency_freeze_sha256": "pinned-dependencies"}
    monkeypatch.setattr(kimodo_runtime, "installation", lambda root: installed)
    monkeypatch.setattr(kimodo_runtime, "capability", lambda root: {"available": True})
    monkeypatch.setattr(kimodo_runtime, "worker_command", lambda root, script, spec, installed: ["fake", str(spec)])
    monkeypatch.setattr(text_motion, "executable", lambda *args: "blender")
    return tmp_path


@pytest.mark.parametrize("change", [{"duration_seconds": 1}, {"prompt": "  "}, {"seed": -1},
                                    {"provider": "tripo"}, {"bone_map": {"Hips": "x", "Chest": "x"}}])
def test_invalid_request_rejected(change):
    with pytest.raises(ValueError):
        request(**change)


@pytest.mark.parametrize("change,reason", [
    ({"clip_name": "idle"}, "already exists"),
    ({"bone_map": {"Hips": "Hips"}}, "observed"),
    ({"bone_map": request().bone_map | {"Invented": "missing"}}, "Unknown SOMA"),
    ({"bone_map": request().bone_map | {"LeftArm": "absent"}}, "do not exist"),
    ({"bone_map": request().bone_map | {"LeftArm": "LeftHand", "LeftHand": "LeftArm"}}, "hierarchy"),
])
def test_plan_rejects_bad_mapping_or_clip_before_inference(runtime, change, reason):
    with pytest.raises(ValueError, match=reason):
        text_motion.plan(runtime, request(**change))
    assert len(list((runtime / ".assets/person").iterdir())) == 1


def inference(command, log, **kwargs):
    saved = read_json(Path(command[-1]))
    out = Path(command[-1]).parent
    files = []
    for name in ("motion-data.json", "motion.npz", "motion.bvh"):
        (out / name).write_bytes(b"test fixture, not learned output")
        files.append({"file": name, "sha256": authoring.sha256(out / name)})
    write_json(out / "kimodo-inference.json", {"backend": "kimodo", "learned_inference": True,
               "binding_sha256": saved["binding_sha256"], "files": files})


@pytest.mark.parametrize("failure_stage", ["authoring", "delivery"])
def test_recovery_reuses_inference_and_preserves_bound_source(runtime, monkeypatch, failure_stage):
    calls, revisions = [], []

    def infer(*args, **kwargs):
        calls.append("inference")
        inference(*args, **kwargs)

    def blender(root, worker, out):
        calls.append("blender")
        assert worker["preview_clips"] == ["wave"]
        if not worker.get("authoring"):
            assert worker["preserve_input_glb"] and worker["source"] == str(out / "generated.glb")
            if failure_stage == "delivery" and calls.count("blender") == 2:
                raise RuntimeError("render interrupted")
            (out / "asset.glb").write_bytes(b"merged fixture")
            return
        assert worker["preserve_animations"]
        if failure_stage == "authoring" and calls.count("blender") == 1:
            raise RuntimeError("render interrupted")
        write_json(out / "authoring.json", {"input_animations": {"clips": ["idle"]}})
        write_json(out / "retarget-map.json", {"visual_review": "pending"})

    def merge(out, clip_name):
        calls.append("merge")
        assert clip_name == "wave"
        return {"output_sha256": hashlib.sha256(b"merged fixture").hexdigest()}

    def finish(root, spec, revision, out, **kwargs):
        assert kwargs["parent"] == "r-original"
        assert kwargs["processing"]["backend"] == "kimodo"
        assert spec.provider == "trellis"
        result = {"asset_id": "person", "revision": revision, "local_processing": kwargs["processing"]}
        write_json(out / "manifest.json", result)
        return result

    monkeypatch.setattr(pipeline, "run_logged", infer)
    monkeypatch.setattr(pipeline, "blender", blender)
    monkeypatch.setattr(text_motion, "merge_generated_clip", merge)
    monkeypatch.setattr(pipeline, "finalize", finish)
    with pytest.raises(RuntimeError, match="resume-text-motion"):
        text_motion.generate(runtime, request(), on_revision=revisions.append)
    revision = revisions[0]["revision"]
    out = runtime / ".assets/person" / revision
    assert not (out / "manifest.json").exists()
    # Blender export recovery remains possible if GPU models are unavailable.
    monkeypatch.setattr(kimodo_runtime, "installation", lambda root: pytest.fail("inference must not restart"))
    final = text_motion.resume(runtime, "person", revision)
    assert text_motion.resume(runtime, "person", revision) == final
    expected = ["inference", "blender", *(["merge", "blender"] if failure_stage == "delivery" else []),
                "blender", "merge", "blender"]
    assert calls == expected
    (out / "input.blend").write_bytes(b"changed source")
    with pytest.raises(ValueError, match="snapshot changed"):
        text_motion.resume(runtime, "person", revision)


@pytest.mark.parametrize("file", ["motion-data.json", "motion.npz", "motion.bvh"])
def test_changed_motion_blocks_export(runtime, monkeypatch, file):
    revisions = []
    monkeypatch.setattr(pipeline, "run_logged", inference)
    monkeypatch.setattr(pipeline, "blender", lambda *args: (_ for _ in ()).throw(RuntimeError("interrupted")))
    with pytest.raises(RuntimeError):
        text_motion.generate(runtime, request(), on_revision=revisions.append)
    revision = revisions[0]["revision"]
    (runtime / ".assets/person" / revision / file).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="output changed"):
        text_motion.resume(runtime, "person", revision)


@pytest.mark.parametrize("background", [False, True])
def test_cli_jobs_and_mcp_use_the_same_model(tmp_path, monkeypatch, capsys, background):
    from asset_auto.mcp_server import build_server

    server = build_server(tmp_path)
    spec = tmp_path / "motion.json"
    write_json(spec, request().model_dump())
    calls = []

    def generate(root, payload, *, on_revision=None):
        calls.append(payload)
        if on_revision:
            on_revision({"asset_id": "person", "revision": "r-new", "operation": "resume-text-motion"})
        return {"asset_id": "person", "revision": "r-new"}

    monkeypatch.setattr(text_motion, "generate", generate)
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=123))
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), "text-motion", str(spec),
                                     *(["--async"] if background else [])])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    if background:
        job = jobs.run(tmp_path, result["job_id"])
        assert job["recovery"]["operation"] == "resume-text-motion"
        result = job["result"]
    assert result["revision"] == "r-new" and calls == [request()]
    submissions = []
    monkeypatch.setattr(jobs, "submit", lambda root, op, body: submissions.append((op, body)) or {"job_id": "j"})
    asyncio.run(server.call_tool("generate_text_motion", {"request": request().model_dump()}))
    assert submissions == [("text-motion", request().model_dump())]


def test_runtime_never_advertises_an_incomplete_installation(tmp_path):
    assert not kimodo_runtime.capability(tmp_path)["available"]
    write_json(tmp_path / ".runtime/installed/kimodo.json", {"environment_ready": True, "ready": False})
    assert not kimodo_runtime.capability(tmp_path)["available"]
    assert len(kimodo_runtime.SOMA_JOINTS) == 77


def test_local_encoder_uses_pinned_base_without_changing_downloaded_metadata(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/kimodo/infer.py"
    spec = importlib.util.spec_from_file_location("kimodo_test_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = {"base_model_name_or_path": "meta-llama/Meta-Llama-3-8B-Instruct"}
    source = tmp_path / "models/mntp"
    write_json(source / "adapter_config.json", config)
    (source / "adapter_model.safetensors").write_bytes(b"adapter fixture")
    seen = []
    monkeypatch.setitem(sys.modules, "kimodo.model.llm2vec.llm2vec_wrapper", SimpleNamespace(
        LLM2VecEncoder=lambda *args, **kwargs: seen.append((args, kwargs))))
    module.local_encoder(tmp_path, "revision-one")
    first = Path(seen[0][0][0])
    assert read_json(first / "adapter_config.json")["base_model_name_or_path"] == str(tmp_path / "models/base")
    assert read_json(source / "adapter_config.json") == config
    (source / "adapter_model.safetensors").write_bytes(b"new pinned fixture")
    module.local_encoder(tmp_path, "revision-two")
    second = Path(seen[1][0][0])
    assert second != first and (second / "adapter_model.safetensors").read_bytes() == b"new pinned fixture"


def test_complete_runtime_accepts_nested_model_inventory_and_detects_missing_files(tmp_path):
    runtime = tmp_path / ".runtime/kimodo"
    for relative in (".venv/pyvenv.cfg", ".venv/bin/python", "source/kimodo/model/kimodo_model.py"):
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    files = []
    for name in kimodo_runtime.MODEL_PINS:
        path = runtime / "models" / name / "fixture.safetensors"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"weights fixture")
        files.append({"path": path.relative_to(runtime).as_posix(), "size_bytes": path.stat().st_size,
                      "sha256": authoring.sha256(path)})
    write_json(tmp_path / ".runtime/installed/kimodo.json", {
        "ready": True, "source_revision": kimodo_runtime.SOURCE_REV, "files": files,
        "models": {name: {"repository": repo, "revision": rev} for name, (repo, rev) in kimodo_runtime.MODEL_PINS.items()},
    })
    assert kimodo_runtime.capability(tmp_path)["available"]
    path.unlink()
    assert not kimodo_runtime.capability(tmp_path)["available"]
