import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from asset_auto import cli, jobs, settings
from asset_auto.store import read_json, write_json

REQUESTS = {
    "blender-edit": {
        "asset_id": "character", "revision": "r-parent", "script": ".work/author #01.py",
        "parameters": {"clip": "wave", "loops": 2}, "preview_clips": ["wave"],
    },
    "merge-animations": {
        "asset_id": "character", "revision": "r-parent",
        "sources": [{"asset_id": "character", "revision": "r-walk", "clips": ["walk"]}],
        "on_conflict": "error", "preview_clips": ["idle", "walk"],
    },
}


@pytest.fixture
def authoring_api(monkeypatch):
    """Exercise interface dispatch without Blender, source files or runtime side effects."""
    calls = []
    module = ModuleType("asset_auto.authoring")

    def author(operation):
        def run(root, request, *, on_revision=None):
            calls.append((operation, root, request.model_dump()))
            if on_revision is not None:
                on_revision({"asset_id": request.asset_id, "revision": "r-new", "operation": f"resume-{operation}"})
            return {"asset_id": request.asset_id, "revision": "r-new", "operation": operation}

        return run

    def validate(root, asset_id, revision, *, operation=None):
        calls.append(("validate", root, asset_id, revision, operation))
        return {"operation": operation}

    def resume(root, asset_id, revision, *, operation=None):
        calls.append(("resume", root, asset_id, revision, operation))
        return {"asset_id": asset_id, "revision": revision, "operation": operation}

    module.edit_in_blender = author("blender-edit")
    module.merge_animations = author("merge-animations")
    module.validate_resume = validate
    module.resume_authoring = resume
    monkeypatch.setitem(sys.modules, "asset_auto.authoring", module)
    return module, calls


@pytest.mark.parametrize("operation", REQUESTS)
@pytest.mark.parametrize("background", [False, True])
def test_cli_authoring_uses_exact_request_and_new_revision(
    tmp_path, monkeypatch, capsys, authoring_api, operation, background
):
    _, calls = authoring_api
    root = tmp_path / "runtime # one"
    root.mkdir()
    spec = tmp_path / "request.json"
    write_json(spec, REQUESTS[operation])
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=123))
    monkeypatch.setattr(sys, "argv", [
        "assetctl", "--root", str(root), operation, str(spec), *(["--async"] if background else []),
    ])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    if background:
        assert calls == []
        saved = read_json(jobs.job_dir(root, result["job_id"]) / "job.json")
        assert saved["operation"] == operation
        assert saved["payload"]["revision"] == "r-parent"
        result = jobs.run(root, result["job_id"])
        assert result["state"] == "succeeded"
        assert result["recovery"] == {
            "asset_id": "character", "revision": "r-new", "operation": f"resume-{operation}",
        }
        result = result["result"]
    assert result == {"asset_id": "character", "revision": "r-new", "operation": operation}
    assert calls == [(operation, root, jobs.AUTHORING_MODELS[operation].model_validate(REQUESTS[operation]).model_dump())]


@pytest.mark.parametrize("operation", REQUESTS)
def test_invalid_authoring_request_never_spawns_worker(tmp_path, monkeypatch, operation):
    def denied(*args, **kwargs):
        raise AssertionError("Invalid request must not launch a worker")

    monkeypatch.setattr(jobs.subprocess, "Popen", denied)
    with pytest.raises(ValueError):
        jobs.submit(tmp_path, operation, REQUESTS[operation] | {"provider": "tripo"})
    assert not (tmp_path / ".assets").exists()


@pytest.mark.parametrize("operation", REQUESTS)
def test_failed_authoring_job_retains_recovery_revision(tmp_path, monkeypatch, authoring_api, operation):
    module, _ = authoring_api

    def interrupted(root, request, *, on_revision):
        on_revision({"asset_id": request.asset_id, "revision": "r-pending", "operation": f"resume-{operation}"})
        raise RuntimeError("Local worker interrupted after checkpoint creation")

    monkeypatch.setattr(module, "edit_in_blender" if operation == "blender-edit" else "merge_animations", interrupted)
    write_json(jobs.job_dir(tmp_path, "failed-author") / "job.json", {
        "state": "queued", "operation": operation, "payload": REQUESTS[operation],
    })
    result = jobs.run(tmp_path, "failed-author")
    assert result["state"] == "failed"
    assert result["recovery"] == {
        "asset_id": "character", "revision": "r-pending", "operation": f"resume-{operation}",
    }
    assert jobs.status(tmp_path, "failed-author")["recovery"] == result["recovery"]


@pytest.mark.parametrize("operation", REQUESTS)
@pytest.mark.parametrize("background", [False, True])
def test_resume_cli_binds_operation_and_never_restarts_authoring(
    tmp_path, monkeypatch, capsys, authoring_api, operation, background
):
    _, calls = authoring_api
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=123))
    monkeypatch.setattr(sys, "argv", [
        "assetctl", "--root", str(tmp_path), f"resume-{operation}", "character", "r-pending",
        *(["--async"] if background else []),
    ])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    if background:
        assert calls == [("validate", tmp_path, "character", "r-pending", operation)]
        result = jobs.run(tmp_path, result["job_id"])
        assert result["state"] == "succeeded"
        result = result["result"]
    assert result == {"asset_id": "character", "revision": "r-pending", "operation": operation}
    assert calls[-2:] == [
        ("validate", tmp_path, "character", "r-pending", operation),
        ("resume", tmp_path, "character", "r-pending", operation),
    ]


@pytest.mark.parametrize("operation", REQUESTS)
def test_resume_checkpoint_conflict_stops_before_spawn(tmp_path, monkeypatch, authoring_api, operation):
    module, _ = authoring_api

    def conflict(*args, **kwargs):
        raise ValueError("Saved authoring operation differs from requested resume operation")

    def denied(*args, **kwargs):
        raise AssertionError("Conflicting checkpoint must not launch a worker")

    monkeypatch.setattr(module, "validate_resume", conflict)
    monkeypatch.setattr(jobs.subprocess, "Popen", denied)
    with pytest.raises(ValueError, match="operation differs"):
        jobs.submit(tmp_path, f"resume-{operation}", {"asset_id": "character", "revision": "r-pending"})
    assert not (tmp_path / ".assets").exists()


@pytest.mark.parametrize("blender_available", [False, True])
def test_capabilities_distinguish_general_authoring_from_biped_presets(tmp_path, monkeypatch, blender_available):
    from asset_auto import local_parts, local_rig

    def executable(root, kind):
        if kind == "blender" and blender_available:
            return "blender-fixture"
        raise FileNotFoundError(kind)

    monkeypatch.setattr(settings, "executable", executable)
    monkeypatch.setattr(settings, "key_configured", lambda root: False)
    monkeypatch.setattr(local_rig, "capability", lambda root: {"available": False})
    monkeypatch.setattr(local_parts, "available", lambda root: {"available": False})
    result = settings.capabilities(tmp_path)
    assert result["blender_authoring"]["available"] is blender_available
    assert result["rigging"]["local_rig_editing"]["available"] is blender_available
    assert result["rigging"]["available"] is False
    animation = result["animation"]
    assert "clips_per_request" not in animation
    assert animation["preset_clips_per_request"] == 1
    assert "preserving other clips" in animation["preset_behavior"]
    assert animation["custom_authoring"]["available"] is blender_available
    assert "rigid object animation" in animation["custom_authoring"]["supports"]
    assert animation["clip_merge"]["available"] is blender_available
    assert animation["clip_merge"]["retargeting"] is False
    assert animation["tripo_option"]["explicit_selection_required"] is True


def test_authoring_mcp_stdio_exposes_tools_and_rejects_invalid_requests(tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "asset_auto.cli", "--root", str(tmp_path), "mcp"],
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert {"edit_in_blender", "merge_asset_animations", "resume_blender_edit", "resume_animation_merge"} <= {
                tool.name for tool in listing.tools
            }
            for tool in ("edit_in_blender", "merge_asset_animations"):
                result = await session.call_tool(tool, {"request": {"asset_id": "character", "revision": "r1"}})
                assert result.isError
            assert not (tmp_path / ".assets").exists()

    asyncio.run(run())
