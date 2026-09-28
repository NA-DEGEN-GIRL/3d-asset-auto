"""Exercise CLI and pipeline resource routing without launching engines or models."""

import json
import os
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from asset_auto import (
    cli,
    jobs,
    kimodo_runtime,
    local_parts,
    local_rig,
    pipeline,
    resources,
    runtime_execution,
)
from asset_auto.models import AssetSpec
from asset_auto.store import read_json, write_json

SAFE_GPU = "GPU-11111111-1111-1111-1111-111111111111"
MOTION_GPU = "GPU-22222222-2222-2222-2222-222222222222"
PROTECTED_GPU = "GPU-33333333-3333-3333-3333-333333333333"


@pytest.fixture(autouse=True)
def private_configuration(tmp_path, monkeypatch):
    # These tests cover routing, not Linux process-group lifetime (covered by
    # test_runtime_execution). Keep the launch branch portable and fully mocked.
    monkeypatch.setattr(runtime_execution, "sys", SimpleNamespace(platform="win32", stderr=sys.stderr))
    monkeypatch.setattr(runtime_execution.subprocess, "Popen", lambda *args, **kwargs: pytest.fail(
        "Integration fixtures must never launch a real process"))
    path = tmp_path / "private-resources.json"
    write_json(path, {})
    monkeypatch.setenv("ASSET_AUTO_RESOURCES_FILE", str(path))
    for key in ("ASSET_AUTO_GPU", "ASSET_AUTO_CPUS", "ASSET_AUTO_THREADS", "TEXT_ENCODER_DEVICE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(resources, "inventory", lambda: {"available": True, "gpus": [
        {"uuid": identifier, "name": "mock GPU", "memory_total_mib": 24576}
        for identifier in (SAFE_GPU, MOTION_GPU, PROTECTED_GPU)]})
    monkeypatch.setattr(runtime_execution, "gpu_busy", lambda _: [])
    locks = tmp_path / "locks"
    locks.mkdir()
    monkeypatch.setattr(runtime_execution, "lock_directory", lambda: locks)
    return path


def selected_policy(path):
    write_json(path, {
        "gpu": [SAFE_GPU], "threads": 4, "protected_gpus": [PROTECTED_GPU], "max_parallel_blender": 1,
        "runtimes": {"kimodo": {"gpu": [MOTION_GPU], "threads": 2, "text_encoder_device": "cpu"},
                     "blender": {"threads": 1}},
    })


def test_cli_resource_report_does_not_apply_process_controls(
        tmp_path, monkeypatch, private_configuration, capsys):
    write_json(private_configuration, {"gpu": [SAFE_GPU], "threads": 3})
    monkeypatch.setattr(resources, "apply_process_resources", lambda *args, **kwargs: pytest.fail(
        "Read-only CLI resource report must not modify the process"))
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), "resources"])
    assert cli.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["policy"]["gpu"] == [SAFE_GPU]
    assert report["runtimes"]["kimodo"]["selected_gpus"][0]["uuid"] == SAFE_GPU
    assert report["sources"]["gpu"] == str(private_configuration)


def test_cli_exec_routes_runtime_override_without_mutating_parent_environment(
        tmp_path, monkeypatch, private_configuration, capsys):
    selected_policy(private_configuration)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", PROTECTED_GPU)
    before = os.environ.copy()
    launches = []

    def run(command, **kwargs):
        launches.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime_execution.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), "resources", "--runtime", "kimodo",
                                      "--exec", "--", "mock-python", "a script.py", "literal argument"])
    assert cli.main() == 0
    assert launches[0][0] == ["mock-python", "a script.py", "literal argument"]
    env = launches[0][1]["env"]
    assert env["CUDA_VISIBLE_DEVICES"] == MOTION_GPU
    assert env["OMP_NUM_THREADS"] == "2"
    assert env["TEXT_ENCODER_DEVICE"] == "cpu"
    assert dict(os.environ) == before
    assert capsys.readouterr().err == ""


def test_cli_exec_policy_failure_never_starts_command(tmp_path, monkeypatch, private_configuration, capsys):
    write_json(private_configuration, {"gpu": [PROTECTED_GPU], "protected_gpus": [PROTECTED_GPU]})
    monkeypatch.setattr(runtime_execution.subprocess, "run", lambda *args, **kwargs: pytest.fail(
        "Protected GPU must be refused before launch"))
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), "resources", "--runtime", "trellis",
                                      "--exec", "--", "mock-trellis"])
    assert cli.main() == 1
    assert "protected GPU" in json.loads(capsys.readouterr().err)["error"]


def glb_fixture(path):
    data = b'{"asset":{"version":"2.0"}}'
    data += b" " * (-len(data) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 20 + len(data)) +
                     struct.pack("<I4s", len(data), b"JSON") + data)


@pytest.mark.parametrize("configured", [False, True])
def test_generation_routes_trellis_then_blender_with_matching_flags_env_and_manifest(
        tmp_path, monkeypatch, private_configuration, configured):
    if configured:
        selected_policy(private_configuration)
    (tmp_path / "reference.png").write_bytes(b"image fixture; no engine reads it")
    monkeypatch.setattr(pipeline, "executable", lambda root, kind: f"mock-{kind}")
    launches = []

    def run(command, **kwargs):
        launches.append((command, kwargs))
        if command[0] == "mock-trellis":
            glb_fixture(Path(command[2]))
        elif command[0] == "mock-blender":
            request = read_json(Path(command[command.index("--") + 1]))
            out = Path(request["output"])
            glb_fixture(out / "asset.glb")
            for name in ("source.blend", "front.png", "back.png", "left.png", "right.png", "perspective.png"):
                (out / name).write_bytes(b"mock output")
            write_json(out / "inspection.json", {"passed": True, "triangle_budget": 12000})
        else:
            pytest.fail(f"Unexpected child command {command[0]}")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime_execution.subprocess, "run", run)
    result = pipeline.generate(tmp_path, AssetSpec(asset_id="resource-fixture", image="reference.png"))
    trellis, blender = launches
    assert [trellis[0][0], blender[0][0]] == ["mock-trellis", "mock-blender"]
    if configured:
        assert trellis[0][trellis[0].index("--gpu") + 1] == "0"
        assert trellis[0][trellis[0].index("--threads") + 1] == "4"
        assert trellis[1]["env"]["CUDA_VISIBLE_DEVICES"] == SAFE_GPU
        assert blender[0][1:3] == ["--threads", "1"]
        assert blender[1]["env"]["ASSET_AUTO_BLENDER_CPU"] == "1"
        assert blender[1]["env"]["OMP_NUM_THREADS"] == "1"
    else:
        assert "--gpu" not in trellis[0] and "--threads" not in trellis[0]
        assert "--threads" not in blender[0]
        assert "env" not in trellis[1] and "env" not in blender[1]
    assert "resource_runs" not in result
    assert result["resource_reports"] == ["blender.resources.json", "trellis.resources.json"]
    manifest_text = json.dumps(result)
    for private_value in (SAFE_GPU, MOTION_GPU, PROTECTED_GPU, str(private_configuration)):
        assert json.dumps(private_value)[1:-1] not in manifest_text
    out = tmp_path / ".assets/resource-fixture" / result["revision"]
    runs = {name: read_json(out / name) for name in result["resource_reports"]}
    assert runs["trellis.resources.json"]["runtime"] == "trellis"
    assert runs["blender.resources.json"]["runtime"] == "blender"
    assert all(record["state"] == "completed" for record in runs.values())
    if configured:
        trellis_report = runs["trellis.resources.json"]
        assert trellis_report["child_environment"]["CUDA_VISIBLE_DEVICES"] == SAFE_GPU
        assert trellis_report["resolved"]["sources"]["gpu"] == str(private_configuration)


def test_parts_blender_context_uses_blender_policy(tmp_path, monkeypatch, private_configuration):
    selected_policy(private_configuration)
    monkeypatch.setattr(local_parts, "executable", lambda *args: "mock-blender")
    launched = []
    monkeypatch.setattr(runtime_execution.subprocess, "run", lambda command, **kwargs: (
        launched.append((command, kwargs)) or SimpleNamespace(returncode=0)))
    local_parts._blender(tmp_path, {"action": "prepare"}, tmp_path, "prepare")
    command, options = launched[0]
    assert command[1:3] == ["--threads", "1"]
    assert options["env"]["ASSET_AUTO_BLENDER_CPU"] == "1"
    assert read_json(tmp_path / "prepare.resources.json")["runtime"] == "blender"


def test_model_runner_uses_kimodo_override_independently_of_trellis(
        tmp_path, monkeypatch, private_configuration):
    selected_policy(private_configuration)
    monkeypatch.setattr(kimodo_runtime, "os", SimpleNamespace(name="posix"))
    command = kimodo_runtime.worker_command(tmp_path, tmp_path / "infer.py", tmp_path / "request.json", {})
    launched = []
    monkeypatch.setattr(runtime_execution.subprocess, "run", lambda argv, **kwargs: (
        launched.append((argv, kwargs)) or SimpleNamespace(returncode=0)))
    pipeline.run_logged(command, tmp_path / "kimodo.log", cwd=tmp_path, runtime="kimodo")
    assert launched[0][0][0] == str(tmp_path / ".runtime/kimodo/.venv/bin/python")
    assert launched[0][1]["env"]["CUDA_VISIBLE_DEVICES"] == MOTION_GPU
    assert launched[0][1]["env"]["TEXT_ENCODER_DEVICE"] == "cpu"
    assert read_json(tmp_path / "kimodo.resources.json")["runtime"] == "kimodo"


def test_job_records_resource_failure_before_starting_model(tmp_path, monkeypatch):
    directory = tmp_path / ".assets/jobs/resource-job"
    write_json(directory / "job.json", {"operation": "generate", "state": "queued", "payload": {}})

    def apply(root):
        raise resources.ResourcePolicyError("Configured CPU affinity is unavailable")

    monkeypatch.setattr(resources, "apply_process_resources", apply)
    monkeypatch.setattr(jobs, "generate", lambda *args, **kwargs: pytest.fail("Model must not launch"))
    result = jobs.run(tmp_path, "resource-job")
    assert result["state"] == "failed"
    assert "CPU affinity" in result["error"]
    assert read_json(directory / "job.json")["state"] == "failed"


@pytest.mark.parametrize("model_fails", [False, True])
def test_job_persists_waiting_progress_and_restores_observer_after_completion(
        tmp_path, monkeypatch, model_fails):
    directory = tmp_path / ".assets/jobs/waiting-job"
    write_json(directory / "job.json", {
        "operation": "generate", "state": "queued",
        "payload": AssetSpec(asset_id="waiting-fixture", image="reference.png").model_dump(),
    })
    monkeypatch.setattr(resources, "apply_process_resources", lambda root: {"enforcement": {}})
    waiting = {"runtime": "trellis", "state": "waiting_resources", "waited_seconds": 3,
               "waiting_reason": "Selected GPU has existing compute processes", "error": None}
    completed = waiting | {"state": "completed", "waiting_reason": None}

    def outer_observer(progress):
        pytest.fail("A job must restore its caller's observer without sending job updates to it")

    def generate(root, spec, **kwargs):
        observer = runtime_execution.progress_observer.get()
        assert observer is not None and observer is not outer_observer
        observer(waiting)
        saved = read_json(directory / "job.json")
        assert saved["state"] == "running"
        assert saved["resource_progress"] == waiting
        assert "error" not in saved and "finished_at" not in saved
        observer(waiting | {"state": "running", "waiting_reason": None})
        if model_fails:
            raise RuntimeError("Mock model failure after acquiring resources")
        observer(completed)
        return {"asset_id": spec.asset_id}

    monkeypatch.setattr(jobs, "generate", generate)
    token = runtime_execution.progress_observer.set(outer_observer)
    try:
        result = jobs.run(tmp_path, "waiting-job")
        assert runtime_execution.progress_observer.get() is outer_observer
    finally:
        runtime_execution.progress_observer.reset(token)
    assert result["state"] == ("failed" if model_fails else "succeeded")
    assert "finished_at" in result
    if model_fails:
        assert "Mock model failure" in result["error"]
    else:
        assert result["resource_progress"] == completed
        assert "error" not in result


@pytest.mark.parametrize("runtime", ["kimodo", "local_rig"])
def test_active_policy_blocks_wsl_before_path_translation_on_any_host(
        tmp_path, monkeypatch, private_configuration, runtime):
    selected_policy(private_configuration)
    monkeypatch.setattr(local_rig, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(local_rig, "wsl_path", lambda *args: pytest.fail("WSL path probe must not start"))
    installed = {"platform": "wsl", "wsl_distribution": "mock-distro"}
    with pytest.raises(resources.ResourcePolicyError, match="native"):
        if runtime == "kimodo":
            kimodo_runtime.worker_command(tmp_path, tmp_path / "infer.py", tmp_path / "request.json", installed)
        else:
            local_rig.command(tmp_path, tmp_path, tmp_path / "input.glb", installed)
