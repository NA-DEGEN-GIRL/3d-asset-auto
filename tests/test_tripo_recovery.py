"""Recovery identifiers survive paid-provider failures at the CLI/job boundary."""

import json
import struct
import sys

import pytest

from asset_auto import cli, jobs, pipeline, tripo
from asset_auto.models import AssetSpec
from asset_auto.store import Store, read_json, write_json


@pytest.fixture
def spec():
    return AssetSpec(
        asset_id="recoverable-prop", provider="tripo", image="reference.png", tripo={"max_credits": 30}
    )


def queue(root, job_id, operation, payload):
    write_json(
        jobs.job_dir(root, job_id) / "job.json",
        {"job_id": job_id, "operation": operation, "payload": payload, "state": "queued"},
    )


def mock_blender(root, request, out):
    (out / "asset.glb").write_bytes(struct.pack("<4sII", b"glTF", 2, 12))
    (out / "source.blend").write_bytes(b"local source")
    write_json(out / "inspection.json", {"passed": True})


def test_failed_job_exposes_revision_and_resumes_without_new_paid_generation(tmp_path, spec, monkeypatch):
    queue(tmp_path, "first", "generate", spec.model_dump())
    calls = []

    def remote(root, request, out, *, resume=False):
        calls.append(resume)
        if not resume:
            running = read_json(jobs.job_dir(root, "first") / "job.json")
            assert running["state"] == "running"
            assert running["recovery"] == {
                "asset_id": request.asset_id, "revision": out.name, "operation": "resume-tripo"
            }
            write_json(out / "tripo.json", {"task_id": "retained-task", "state": "waiting"})
            raise tripo.TripoError("Tripo is still processing; use resume-tripo")
        assert read_json(out / "tripo.json")["task_id"] == "retained-task"
        (out / "generated.glb").write_bytes(struct.pack("<4sII", b"glTF", 2, 12))

    monkeypatch.setattr(tripo, "generate", remote)
    monkeypatch.setattr(pipeline, "executable", lambda *args: "blender")
    monkeypatch.setattr(pipeline, "blender", mock_blender)
    failed = jobs.run(tmp_path, "first")
    assert failed["state"] == "failed"
    assert Store(tmp_path).list() == []
    recovery = jobs.status(tmp_path, "first")["recovery"]
    assert recovery["asset_id"] in failed["error"]
    assert recovery["revision"] in failed["error"]

    queue(tmp_path, "second", "resume-tripo", {key: recovery[key] for key in ("asset_id", "revision")})
    resumed = jobs.run(tmp_path, "second")
    assert resumed["state"] == "succeeded"
    assert resumed["result"]["revision"] == recovery["revision"]
    assert calls == [False, True]

    def denied(*args, **kwargs):
        raise AssertionError("A completed revision needs no remote call or Blender installation")

    monkeypatch.setattr(tripo, "generate", denied)
    monkeypatch.setattr(pipeline, "executable", denied)
    monkeypatch.setattr(pipeline, "blender", denied)
    assert pipeline.resume_tripo(tmp_path, recovery["asset_id"], recovery["revision"]) == resumed["result"]


def test_worker_interruption_keeps_recovery_link_before_remote_submission(tmp_path, spec, monkeypatch):
    queue(tmp_path, "interrupted", "generate", spec.model_dump())

    def interrupted(*args, **kwargs):
        record = read_json(jobs.job_dir(tmp_path, "interrupted") / "job.json")
        assert record["recovery"]["asset_id"] == spec.asset_id
        raise KeyboardInterrupt

    monkeypatch.setattr(tripo, "generate", interrupted)
    monkeypatch.setattr(pipeline, "executable", lambda *args: "blender")
    with pytest.raises(KeyboardInterrupt):
        jobs.run(tmp_path, "interrupted")
    path = jobs.job_dir(tmp_path, "interrupted") / "job.json"
    record = read_json(path)
    recovery = record["recovery"]
    # Model the process having exited after the checkpoint, without spawning a worker.
    record["process_created_at"] = 0.1
    write_json(path, record)
    status = jobs.status(tmp_path, "interrupted")
    assert status["state"] == "interrupted"
    assert status["recovery"] == recovery


def test_direct_cli_failure_reports_created_asset_and_revision(tmp_path, spec, monkeypatch, capsys):
    path = tmp_path / "request.json"
    write_json(path, spec.model_dump())

    def fail(*args, **kwargs):
        raise tripo.TripoError("Submission outcome is unknown; inspect the vendor dashboard")

    monkeypatch.setattr(pipeline, "executable", lambda *args: "blender")
    monkeypatch.setattr(tripo, "generate", fail)
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), "generate", str(path)])
    assert cli.main() == 1
    error = json.loads(capsys.readouterr().err)["error"]
    generation = next((tmp_path / ".assets" / spec.asset_id).glob("*/generation.json"))
    assert spec.asset_id in error
    assert generation.parent.name in error
    assert "vendor dashboard" in error
