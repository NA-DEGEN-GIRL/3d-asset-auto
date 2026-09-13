import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from asset_auto import cli, jobs, pipeline
from asset_auto.store import read_json, write_json


def test_real_stdio_handshake_and_tools(tmp_path):
    (tmp_path / "reference.png").write_bytes(b"local-planning-reference")

    async def run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "asset_auto.cli", "--root", str(tmp_path), "mcp"]
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert {
                "generate_asset", "edit_asset", "asset_job_status", "tripo_plan", "tripo_balance", "resume_tripo_asset",
                "tripo_process_plan", "process_tripo_asset", "resume_tripo_processing",
                "process_plan", "process_asset", "prepare_local_segmentation", "resume_asset_processing",
            } <= {t.name for t in listing.tools}
            result = await session.call_tool("asset_capabilities", {})
            assert not result.isError
            invalid = await session.call_tool("generate_asset", {"spec": {"asset_id": "../escape"}})
            assert invalid.isError
            planned = await session.call_tool("tripo_plan", {"spec": {
                "asset_id": "cloud-prop", "provider": "tripo", "image": "reference.png",
            }})
            assert not planned.isError
            plan = json.loads(planned.content[0].text)
            assert plan["estimated_credits"] == 30 and plan["max_credits"] == 100 and plan["within_budget"]
            # Omitted provider must use the local prompt workflow, before submitting a job.
            local = await session.call_tool("process_asset", {"request": {
                "asset_id": "character", "revision": "r1", "operation": "segment",
            }})
            assert local.isError
            assert "Local segmentation requires" in local.content[0].text
            conflict = await session.call_tool("tripo_process_plan", {"spec": {
                "asset_id": "character", "revision": "r1", "operation": "rig", "provider": "local",
            }})
            assert conflict.isError
            assert "Tripo-specific command requires" in conflict.content[0].text
            assert not (tmp_path / ".assets").exists()
            # Agents need cost/provenance and frame paths to review a completed character job.
            completed = tmp_path / ".assets" / "jobs" / "completed-character"
            completed.mkdir(parents=True)
            asset = {
                "asset_id": "character", "revision": "r2", "parent": "r1", "state": "numeric-pass",
                "asset_type": "character", "inspection": {"passed": True},
                "remote_processing": {"operation": "animate", "credits_consumed": 10},
                "local_processing": {"operation": "animate", "provider": "local"},
                "provenance": {"source_sha256": "fixture-source"},
                "animation_previews": {"clips": [{"name": "walk", "samples": [{"file": "walk.png"}]}]},
            }
            (completed / "job.json").write_text(json.dumps({
                "state": "succeeded", "payload": {"private_request": True}, "result": asset,
            }), encoding="utf-8")
            result = await session.call_tool("asset_job_status", {"job_id": "completed-character"})
            assert not result.isError
            status = json.loads(result.content[0].text)
            assert "payload" not in status
            assert status["result"] == asset
            # Preparation returns observations and paths, not a completed asset manifest.
            context = {
                "asset_id": "character", "revision": "r1", "context": "context.json",
                "views": [{"image": "front.png", "width": 512, "height": 512}],
                "source_sha256": "source-hash", "state": "prepared",
            }
            write_json(tmp_path / ".assets/jobs/prepared-parts/job.json", {
                "state": "succeeded", "payload": {"asset_id": "character"}, "result": context,
            })
            result = await session.call_tool("asset_job_status", {"job_id": "prepared-parts"})
            assert not result.isError
            assert json.loads(result.content[0].text)["result"] == context

    asyncio.run(run())


@pytest.mark.parametrize("command,provider", [("process", "local"), ("tripo-process", "tripo")])
@pytest.mark.parametrize("background", [False, True])
def test_processing_cli_selects_provider_without_changing_requested_revision(
    tmp_path, monkeypatch, capsys, command, provider, background
):
    request = {"asset_id": "character", "revision": "r-exact", "operation": "rig"}
    spec = tmp_path / "request.json"
    write_json(spec, request)
    calls = []

    def direct(root, payload):
        calls.append((root, "direct", payload.model_dump()))
        return {"revision": "r-new"}

    def submit(root, operation, payload):
        calls.append((root, operation, payload))
        return {"job_id": "job-new"}

    monkeypatch.setattr(cli, "postprocess", direct)
    monkeypatch.setattr(cli.jobs, "submit", submit)
    monkeypatch.setattr(sys, "argv", [
        "assetctl", "--root", str(tmp_path), command, str(spec), *(["--async"] if background else []),
    ])
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out) == ({"job_id": "job-new"} if background else {"revision": "r-new"})
    assert calls[0][:2] == (tmp_path, command if background else "direct")
    assert calls[0][2]["provider"] == provider
    assert calls[0][2]["revision"] == "r-exact"


@pytest.mark.parametrize("command,provider", [("process-plan", "local"), ("tripo-process-plan", "tripo")])
def test_plan_cli_uses_same_explicit_provider_rules(tmp_path, monkeypatch, capsys, command, provider):
    spec = tmp_path / "request.json"
    write_json(spec, {"asset_id": "character", "revision": "r1", "operation": "rig"})
    monkeypatch.setattr(cli, "postprocess_plan", lambda root, request: {"provider": request.provider})
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), command, str(spec)])
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out) == {"provider": provider}


@pytest.mark.parametrize("command", ["tripo-process", "tripo-process-plan"])
def test_tripo_cli_alias_rejects_local_instead_of_overriding_user_choice(tmp_path, monkeypatch, capsys, command):
    spec = tmp_path / "request.json"
    write_json(spec, {"asset_id": "character", "revision": "r1", "operation": "rig", "provider": "local"})
    monkeypatch.setattr(sys, "argv", ["assetctl", "--root", str(tmp_path), command, str(spec)])
    assert cli.main() == 1
    assert "Tripo-specific command requires" in json.loads(capsys.readouterr().err)["error"]
    assert not (tmp_path / ".assets").exists()


@pytest.mark.parametrize("operation,provider", [("process", "local"), ("tripo-process", "tripo")])
def test_processing_job_records_explicit_provider_before_worker_launch(tmp_path, monkeypatch, operation, provider):
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=123))
    result = jobs.submit(tmp_path, operation, {"asset_id": "character", "revision": "r1", "operation": "rig"})
    saved = read_json(jobs.job_dir(tmp_path, result["job_id"]) / "job.json")
    assert saved["payload"]["provider"] == provider
    assert saved["payload"]["revision"] == "r1"


@pytest.mark.parametrize("operation,provider", [("process", "local"), ("tripo-process", "tripo")])
def test_queued_job_without_provider_uses_its_original_operation(tmp_path, monkeypatch, operation, provider):
    path = jobs.job_dir(tmp_path, "legacy-job") / "job.json"
    write_json(path, {
        "state": "queued", "operation": operation,
        "payload": {"asset_id": "character", "revision": "r1", "operation": "rig"},
    })
    observed = []

    def process(root, request, *, on_revision):
        observed.append(request.provider)
        on_revision({"asset_id": "character", "revision": "r-new", "operation": "resume-process"})
        return {"asset_id": "character", "revision": "r-new"}

    monkeypatch.setattr(jobs, "postprocess", process)
    result = jobs.run(tmp_path, "legacy-job")
    assert result["state"] == "succeeded"
    assert observed == [provider]
    assert result["recovery"]["revision"] == "r-new"


def test_resume_alias_rejects_saved_local_work_but_generic_resume_accepts_it(tmp_path, monkeypatch, capsys):
    payload = {"asset_id": "character", "revision": "r-pending"}
    checkpoint = tmp_path / ".assets/character/r-pending/processing.json"
    write_json(checkpoint, {"request": payload | {"operation": "rig", "provider": "local"}})
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=123))
    with pytest.raises(ValueError, match="Tripo-specific command requires"):
        jobs.submit(tmp_path, "resume-tripo-process", payload)
    assert not (tmp_path / ".assets/jobs").exists()
    assert jobs.submit(tmp_path, "resume-process", payload)["state"] == "submitted"
    monkeypatch.setattr(sys, "argv", [
        "assetctl", "--root", str(tmp_path), "resume-tripo-process", "character", "r-pending",
    ])
    assert cli.main() == 1
    assert "Tripo-specific command requires" in json.loads(capsys.readouterr().err)["error"]
    write_json(checkpoint, {"request": payload | {"operation": "rig"}})
    assert jobs.validate_processing_resume(tmp_path, payload).provider == "tripo"


@pytest.mark.parametrize("background", [False, True])
def test_prepare_cli_and_job_preserve_context_result(tmp_path, monkeypatch, capsys, background):
    context = {"asset_id": "character", "revision": "r1", "context": "context.json", "views": ["front.png"]}
    observed = []

    def prepare(root, asset_id, revision):
        observed.append((root, asset_id, revision))
        return context

    monkeypatch.setattr(pipeline, "prepare_segmentation", prepare, raising=False)
    monkeypatch.setattr(sys, "argv", [
        "assetctl", "--root", str(tmp_path), "prepare-segment", "character", "r1",
        *(["--async"] if background else []),
    ])
    if background:
        write_json(tmp_path / ".assets/character/r1/manifest.json", {"asset_id": "character", "revision": "r1"})
        monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=123))
    assert cli.main() == 0
    response = json.loads(capsys.readouterr().out)
    if background:
        assert not observed
        result = jobs.run(tmp_path, response["job_id"])
        assert result["state"] == "succeeded"
        assert result["result"] == context
    else:
        assert response == context
    assert observed == [(tmp_path, "character", "r1")]
