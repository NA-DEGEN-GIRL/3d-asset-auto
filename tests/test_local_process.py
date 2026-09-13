"""Local-default processing contracts; no remote service, Blender or learned model runs."""

import hashlib
import json
import socket
import struct
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from asset_auto import cli, jobs, pipeline, tripo, tripo_process
from asset_auto.models import AssetSpec, PostprocessRequest
from asset_auto.store import Store, read_json, write_json

MOCK_BONE_MAP = {"left_foot": "Foot.L", "right_foot": "Foot.R"}


@pytest.fixture(autouse=True)
def no_remote_calls(monkeypatch):
    # Key presence must never select the paid provider, even in a configured installation.
    monkeypatch.setenv("TRIPO_API_KEY", "test-key-must-never-be-read")
    monkeypatch.delenv("TRIPO_API_KEY_FILE", raising=False)

    def denied(*args, **kwargs):
        raise AssertionError("Local processing must not construct a Tripo client or access the network")

    monkeypatch.setattr(tripo, "api_key", denied)
    monkeypatch.setattr(tripo, "TripoClient", denied)
    monkeypatch.setattr(tripo_process, "TripoClient", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def request_payload(operation="rig", **changes):
    payload = {"asset_id": "local-character", "revision": "r-source", "operation": operation}
    if operation == "segment":
        payload.update(segmentation_context=".work/parts/context.json", segmentation_parts=[
            {"name": "lid", "positive_points": [[32, 20]], "negative_points": [[32, 60]]},
        ])
    return payload | changes


@pytest.fixture
def local_source(tmp_path):
    directory = tmp_path / ".assets/local-character/r-source"
    directory.mkdir(parents=True)
    document = json.dumps({"asset": {"version": "2.0"}}).encode()
    document += b" " * (-len(document) % 4)
    raw = struct.pack("<4sII", b"glTF", 2, 20 + len(document)) + struct.pack("<I4s", len(document), b"JSON") + document
    (directory / "asset.glb").write_bytes(raw)
    (directory / "source.blend").write_bytes(b"original-local-source")
    manifest = {
        "asset_id": "local-character", "revision": "r-source", "created_at": "2026-09-13T00:00:00Z",
        "provider": "trellis", "spec": AssetSpec(asset_id="local-character", image="reference.png").model_dump(),
        "files": {"asset.glb": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}},
        "inspection": {"triangle_budget": 12000, "dimensions": [1, 1, 2], "parts": [{"name": "body"}]},
    }
    write_json(directory / "manifest.json", manifest)
    return directory, manifest


def prepared_context(tmp_path, source):
    context = tmp_path / ".work/parts/context.json"
    context.parent.mkdir(parents=True, exist_ok=True)
    names = ["canonical.npz", "prepared.blend", "meta.json"]
    names.extend(f"{prefix}_{view:04d}.{extension}" for view in range(12)
                 for prefix, extension in (("color", "png"), ("normal", "png"), ("depth", "exr")))
    for name in names:
        (context.parent / name).write_bytes(b"context-contract-fixture-only")
    write_json(context.parent / "meta.json", {"resolution": 1024, "transforms": [[1, 0, 0, 0] * 4] * 12})
    files = {name: {"bytes": (context.parent / name).stat().st_size,
                    "sha256": hashlib.sha256((context.parent / name).read_bytes()).hexdigest()} for name in names}
    write_json(context, {"schema": "asset-auto-geosam2-context-v1",
                         "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "files": files})
    return context


@pytest.mark.parametrize("operation", ["rig", "animate", "segment"])
def test_all_generic_postprocessing_defaults_to_local_even_when_key_exists(operation):
    request = PostprocessRequest.model_validate(request_payload(operation))
    assert request.provider == "local"
    assert jobs.processing_request(request_payload(operation)).provider == "local"


@pytest.mark.parametrize("missing", ["segmentation_context", "segmentation_parts"])
def test_local_segmentation_requires_prepared_context_and_observed_prompts(missing):
    payload = request_payload("segment")
    payload.pop(missing)
    with pytest.raises(ValidationError, match="prepare-segment"):
        PostprocessRequest.model_validate(payload)


@pytest.mark.parametrize("changes", [
    {"segmentation_view": 12}, {"segmentation_view": -1},
    {"segmentation_parts": [{"name": "lid", "positive_points": []}]},
    {"segmentation_parts": [{"name": "lid", "positive_points": [[-1, 10]]}]},
    {"segmentation_parts": [{"name": "lid", "positive_points": [[1, 10]], "negative_points": [[1, -1]]}]},
    {"segmentation_parts": [{"name": "lid", "positive_points": [[1, 10]]},
                            {"name": "lid", "positive_points": [[20, 10]]}]},
])
def test_local_segmentation_rejects_invalid_prompt_coordinates_and_duplicate_names(changes):
    with pytest.raises(ValidationError):
        PostprocessRequest.model_validate(request_payload("segment", **changes))


@pytest.mark.parametrize("field", ["positive_points", "negative_points"])
@pytest.mark.parametrize("coordinate", [1023, 1024])
def test_segmentation_prompt_pixel_coordinates_stay_within_pinned_view(field, coordinate):
    part = {"name": "lid", "positive_points": [[32, 20]], field: [[coordinate, coordinate]]}
    payload = request_payload("segment", segmentation_parts=[part])
    if coordinate == 1024:
        with pytest.raises(ValidationError, match="1024|pixel|coordinate"):
            PostprocessRequest.model_validate(payload)
    else:
        request = PostprocessRequest.model_validate(payload)
        assert getattr(request.segmentation_parts[0], field) == [(1023, 1023)]


@pytest.mark.parametrize("bone_map", [{}, {"hips": ""}, {"": "hips"}, {"hip": "pelvis", "spine": "pelvis"}])
def test_local_animation_bone_map_requires_distinct_actual_bone_names(bone_map):
    with pytest.raises(ValidationError, match="bone|motion role"):
        PostprocessRequest.model_validate(request_payload("animate", bone_map=bone_map))


def test_only_explicit_tripo_alias_selects_paid_provider():
    payload = request_payload()
    assert PostprocessRequest.model_validate(payload).provider == "local"
    assert PostprocessRequest.for_tripo(payload).provider == "tripo"
    assert jobs.processing_request(payload, tripo_only=True).provider == "tripo"
    with pytest.raises(ValueError, match="Tripo-specific"):
        PostprocessRequest.for_tripo(payload | {"provider": "local"})
    with pytest.raises(ValueError, match="Tripo-specific"):
        jobs.processing_request(payload | {"provider": "local"}, tripo_only=True)


@pytest.mark.parametrize("payload", [
    request_payload("segment", provider="tripo"),
    request_payload("animate", provider="tripo", bone_map={"hips": "pelvis"}),
])
def test_local_prompts_and_bone_mapping_cannot_be_sent_to_tripo(payload):
    with pytest.raises(ValidationError, match="cannot be sent"):
        PostprocessRequest.model_validate(payload)


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("operation", ["rig", "animate", "segment"])
def test_generic_cli_dispatches_default_local_request(tmp_path, monkeypatch, capsys, background, operation):
    path = tmp_path / "request.json"
    write_json(path, request_payload(operation))
    calls = []

    def process(root, request):
        calls.append(("direct", request.provider, request.operation))
        return {"state": "test-dispatch-only"}

    def submit(root, name, payload):
        calls.append((name, payload["provider"], payload["operation"]))
        return {"state": "test-dispatch-only"}

    monkeypatch.setattr(cli, "postprocess", process)
    monkeypatch.setattr(jobs, "submit", submit)
    arguments = ["assetctl", "--root", str(tmp_path), "process", str(path)]
    monkeypatch.setattr(sys, "argv", arguments + (["--async"] if background else []))
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["state"] == "test-dispatch-only"
    assert calls == [("process" if background else "direct", "local", operation)]


def test_async_job_submission_persists_local_provider_before_worker_start(tmp_path, monkeypatch):
    launches = []

    def launch(command, **kwargs):
        launches.append(command)
        return SimpleNamespace(pid=12345)

    monkeypatch.setattr(jobs.subprocess, "Popen", launch)
    result = jobs.submit(tmp_path, "process", request_payload())
    saved = read_json(tmp_path / ".assets/jobs" / result["job_id"] / "job.json")
    assert saved["operation"] == "process"
    assert saved["payload"]["provider"] == "local"
    assert len(launches) == 1


def test_generic_worker_calls_local_pipeline_once_and_keeps_failure_recovery(tmp_path, monkeypatch):
    directory = tmp_path / ".assets/jobs/local-job"
    write_json(directory / "job.json", {
        "job_id": "local-job", "operation": "process", "state": "queued", "payload": request_payload(),
    })
    calls = []

    def process(root, request, *, on_revision):
        calls.append(request.provider)
        on_revision({"asset_id": request.asset_id, "revision": "r-incomplete", "operation": "resume-process"})
        raise RuntimeError("local runtime unavailable in this offline dispatch test")

    monkeypatch.setattr(jobs, "postprocess", process)
    result = jobs.run(tmp_path, "local-job")
    assert result["state"] == "failed"
    assert result["recovery"]["operation"] == "resume-process"
    assert result["recovery"]["revision"] == "r-incomplete"
    assert calls == ["local"]
    assert "result" not in result


def test_paid_resume_alias_rejects_a_saved_local_job(tmp_path):
    directory = tmp_path / ".assets/local-character/r-pending"
    write_json(directory / "processing.json", {"request": PostprocessRequest.model_validate(request_payload()).model_dump()})
    payload = {"asset_id": "local-character", "revision": "r-pending"}
    assert jobs.validate_processing_resume(tmp_path, payload).provider == "local"
    with pytest.raises(ValueError, match="Tripo-specific"):
        jobs.validate_processing_resume(tmp_path, payload, tripo_only=True)


def test_modified_local_source_is_rejected_without_allocating_a_revision(tmp_path, local_source, monkeypatch):
    directory, _ = local_source
    raw = (directory / "asset.glb").read_bytes().replace(b"2.0", b"2.1")
    (directory / "asset.glb").write_bytes(raw)

    def denied(*args, **kwargs):
        raise AssertionError("A changed source must be rejected before allocating a new revision")

    monkeypatch.setattr(Store, "new_revision", denied)
    with pytest.raises(ValueError, match="Source GLB changed"):
        pipeline.postprocess(tmp_path, PostprocessRequest.model_validate(request_payload()))


@pytest.mark.parametrize("missing", ["canonical.npz", "prepared.blend", "meta.json"])
def test_local_segmentation_rejects_incomplete_prepared_context(tmp_path, local_source, missing):
    from asset_auto import local_parts

    source = local_source[0] / "asset.glb"
    context = prepared_context(tmp_path, source)
    (context.parent / missing).unlink()
    with pytest.raises(ValueError, match="changed or is incomplete"):
        local_parts._context(context, source)


def test_local_segmentation_context_is_bound_to_exact_source_before_runtime_access(tmp_path, local_source, monkeypatch):
    from asset_auto import local_parts

    context = tmp_path / ".work/parts/context.json"
    write_json(context, {"schema": "asset-auto-geosam2-context-v1", "source_sha256": "0" * 64})

    def denied(*args, **kwargs):
        raise AssertionError("Mismatched context must be rejected before checking or running inference")

    monkeypatch.setattr(local_parts, "installed", denied)
    request = PostprocessRequest.model_validate(request_payload("segment", segmentation_context=str(context)))
    with pytest.raises(ValueError, match="exact source GLB"):
        local_parts.segment(tmp_path, request, tmp_path / "new-revision", local_source[0] / "asset.glb")
    assert not (tmp_path / "new-revision").exists()


@pytest.mark.parametrize("name", ["canonical.npz", "prepared.blend", "color_0000.png", "normal_0005.png", "depth_0011.exr"])
def test_prepared_context_rejects_changed_geometry_or_observed_view_bytes(tmp_path, local_source, name):
    from asset_auto import local_parts

    source = local_source[0] / "asset.glb"
    context = prepared_context(tmp_path, source)
    file = context.parent / name
    raw = file.read_bytes()
    file.write_bytes(b"!" + raw[1:])
    with pytest.raises(ValueError, match="changed or is incomplete"):
        local_parts._context(context, source)


def test_existing_local_context_reuses_read_only_without_blender(tmp_path, local_source, monkeypatch):
    from asset_auto import local_parts

    source = local_source[0] / "asset.glb"
    context = prepared_context(tmp_path, source)

    def denied(*args, **kwargs):
        raise AssertionError("Reusing an existing context must not rerender or start inference")

    monkeypatch.setattr(local_parts, "_blender", denied)
    before = {path: path.read_bytes() for path in context.parent.iterdir()}
    result = local_parts.prepare(tmp_path, source, context.parent)
    assert result["context"] == str(context.resolve())
    assert {path: path.read_bytes() for path in context.parent.iterdir()} == before


def prepared_request(tmp_path, local_source, operation):
    payload = request_payload(operation)
    if operation == "segment":
        source = local_source[0] / "asset.glb"
        context = prepared_context(tmp_path, source)
        payload["segmentation_context"] = str(context)
    if operation == "animate":
        directory, manifest = local_source
        manifest["inspection"]["rigging"] = {"armatures": [{"name": "ImportedRig", "bones": 32}]}
        write_json(directory / "manifest.json", manifest)
    return PostprocessRequest.model_validate(payload)


def install_mock_local_backend(monkeypatch, operation, calls, *, native=False):
    from asset_auto import local_motion, local_parts, local_rig

    def backend(root, request, out, source):
        calls.append((request.operation, source, out))
        out.mkdir(parents=True, exist_ok=True)
        name = "generated.blend" if native else "generated.glb"
        (out / name).write_bytes(b"mock-native-blend" if native else source.read_bytes())
        result = {"provider": "local", "backend": "mock-worker-for-dispatch-test", "generated_file": name}
        if operation == "animate":
            result.update(bone_map=MOCK_BONE_MAP, authored_frames=25, ground_checks={
                "scope": "generated.glb mock stage", "samples": 49,
                "below_floor_samples": 0, "maximum_penetration_m": 0,
            })
            write_json(out / "local-motion.json", result)
        return result

    module, function = {
        "rig": (local_rig, "generate"), "animate": (local_motion, "generate"), "segment": (local_parts, "segment"),
    }[operation]
    monkeypatch.setattr(module, function, backend)


@pytest.mark.parametrize("operation", ["rig", "animate", "segment"])
def test_generic_pipeline_plan_is_local_and_read_only_without_credentials(tmp_path, local_source, monkeypatch, operation):
    from asset_auto import settings

    request = prepared_request(tmp_path, local_source, operation)
    monkeypatch.setattr(settings, "executable", lambda *args: "test-blender")
    before = set(tmp_path.rglob("*"))
    result = pipeline.postprocess_plan(tmp_path, request)
    assert result["provider"] == "local"
    assert result["estimated_credits"] == 0
    assert result["paid"] is False
    assert result["inference_network_required"] is False
    assert result["source_sha256"] == local_source[1]["files"]["asset.glb"]["sha256"]
    assert set(tmp_path.rglob("*")) == before


def test_local_animation_accepts_an_imported_rig_without_tripo_provenance(tmp_path, local_source):
    request = prepared_request(tmp_path, local_source, "animate")
    raw, manifest, digest = pipeline.processing_source(tmp_path, request)
    assert "remote_processing" not in manifest
    assert raw == local_source[0] / "asset.glb"
    assert digest == hashlib.sha256(raw.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="completed Tripo rig"):
        pipeline.processing_source(tmp_path, request.model_copy(update={"provider": "tripo"}))


def test_local_animation_rejects_static_source_before_any_model_runs(tmp_path, local_source):
    with pytest.raises(ValueError, match="completed rigged revision"):
        pipeline.processing_source(tmp_path, PostprocessRequest.model_validate(request_payload("animate")))


@pytest.mark.parametrize("operation", ["rig", "animate", "segment"])
def test_local_pipeline_keeps_parent_and_records_local_provenance(tmp_path, local_source, monkeypatch, operation):
    request = prepared_request(tmp_path, local_source, operation)
    directory, parent = local_source
    original = {path.name: path.read_bytes() for path in directory.iterdir()}
    backend_calls, worker_calls = [], []
    install_mock_local_backend(monkeypatch, operation, backend_calls, native=operation == "rig")
    monkeypatch.setattr(pipeline, "executable", lambda *args: "test-blender")

    def worker(root, worker_request, out):
        worker_calls.append(worker_request)
        assert worker_request["target_height"] is None
        assert worker_request["character"] is (operation != "segment")
        exported = original["asset.glb"]
        if operation == "animate":
            assert worker_request["dense_motion_check"] == {"bone_map": MOCK_BONE_MAP, "authored_frames": 25}
            document = json.loads(exported[20:])
            document["extras"] = {"test_export_stage": "final-delivery"}
            encoded = json.dumps(document).encode()
            encoded += b" " * (-len(encoded) % 4)
            exported = (struct.pack("<4sII", b"glTF", 2, 20 + len(encoded))
                        + struct.pack("<I4s", len(encoded), b"JSON") + encoded)
        (out / "asset.glb").write_bytes(exported)
        (out / "source.blend").write_bytes(b"mock-worker-export")
        report = {
            "passed": True, "errors": [], "warnings": [], "triangle_budget": 12000, "dimensions": [1, 1, 2],
            "parts": [{"name": "body"}, {"name": "lid"}] if operation == "segment" else [{"name": "body"}],
            "rigging": {"armatures": [] if operation == "segment" else [{"name": "TestRig", "bones": 32}]},
        }
        if operation == "animate":
            report["animation_quality"] = {"dense_ground_checks": {
                "scope": "final-delivery mock stage", "samples": 49, "below_floor_samples": 1,
                "maximum_penetration_m": 0.004,
                "artifact": {"file": "asset.glb", "stage": "final_delivery",
                             "sha256": hashlib.sha256(exported).hexdigest()},
            }}
        write_json(out / "inspection.json", report)

    monkeypatch.setattr(pipeline, "blender", worker)
    recovery = []
    result = pipeline.postprocess(tmp_path, request, on_revision=recovery.append)
    assert len(backend_calls) == len(worker_calls) == 1
    assert result["revision"] != parent["revision"]
    assert result["parent"] == parent["revision"]
    assert result["local_processing"]["provider"] == "local"
    assert result["local_processing"]["credits_consumed"] == 0
    assert "remote_processing" not in result
    assert result["visual_review"] == "pending"
    assert recovery[0]["operation"] == "resume-process"
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == original
    if operation == "segment":
        assert result["inspection"]["segmentation"]["semantic_review"] == "pending"
    if operation == "rig":
        assert worker_calls[0]["source"].endswith("generated.blend")
    if operation == "animate":
        processing = result["local_processing"]
        final_checks = result["inspection"]["animation_quality"]["dense_ground_checks"]
        generated_checks = processing["generated_ground_checks"]
        assert final_checks["below_floor_samples"] == 1
        assert generated_checks["below_floor_samples"] == 0
        assert final_checks["artifact"] == {
            "file": "asset.glb", "stage": "final_delivery", "sha256": result["files"]["asset.glb"]["sha256"],
        }
        assert generated_checks["artifact"] == {
            "file": "generated.glb", "stage": "generation", "sha256": processing["generated_sha256"],
        }
        assert final_checks["artifact"]["sha256"] != generated_checks["artifact"]["sha256"]
        assert processing["ground_checks"] == final_checks
        out = directory.parent / result["revision"]
        for filename in ("local-motion.json", "local-process.json"):
            saved = read_json(out / filename)
            assert saved["ground_checks"] == final_checks
            assert saved["generated_ground_checks"] == generated_checks
    assert pipeline.resume_postprocess(tmp_path, request.asset_id, result["revision"]) == result
    assert len(backend_calls) == len(worker_calls) == 1


@pytest.mark.parametrize("operation", ["rig", "animate", "segment"])
def test_cached_local_output_resumes_without_running_backend_again(tmp_path, local_source, monkeypatch, operation):
    from asset_auto import local_process

    request = prepared_request(tmp_path, local_source, operation)
    calls = []
    install_mock_local_backend(monkeypatch, operation, calls)
    directory, manifest = local_source
    out = tmp_path / "new-revision"
    result = local_process.process(tmp_path, request, out, directory / "asset.glb", manifest)
    recovered = local_process.process(tmp_path, request, out, directory / "asset.glb", manifest, resume=True)
    assert recovered == result
    assert len(calls) == 1


def test_local_animation_cannot_complete_from_generation_checks_without_final_delivery_checks(
    tmp_path, local_source, monkeypatch
):
    request = prepared_request(tmp_path, local_source, "animate")
    calls = []
    install_mock_local_backend(monkeypatch, "animate", calls)
    monkeypatch.setattr(pipeline, "executable", lambda *args: "test-blender")

    def worker_without_dense_result(root, worker_request, out):
        assert worker_request["dense_motion_check"] == {"bone_map": MOCK_BONE_MAP, "authored_frames": 25}
        (out / "asset.glb").write_bytes((local_source[0] / "asset.glb").read_bytes())
        (out / "source.blend").write_bytes(b"mock-worker-export")
        write_json(out / "inspection.json", {
            "passed": True, "errors": [], "warnings": [], "animation_quality": {},
        })

    monkeypatch.setattr(pipeline, "blender", worker_without_dense_result)
    recovery = []
    with pytest.raises(RuntimeError, match="dense_ground_checks"):
        pipeline.postprocess(tmp_path, request, on_revision=recovery.append)
    assert len(calls) == 1
    out = tmp_path / ".assets" / request.asset_id / recovery[0]["revision"]
    assert not (out / "manifest.json").exists()
    assert len(Store(tmp_path).list()) == 1


@pytest.mark.parametrize("mutation", ["source", "request", "output", "context"])
def test_local_recovery_rejects_changed_bound_input_or_output(tmp_path, local_source, monkeypatch, mutation):
    from asset_auto import local_process

    request = prepared_request(tmp_path, local_source, "segment")
    calls = []
    install_mock_local_backend(monkeypatch, "segment", calls)
    directory, manifest = local_source
    source, out = directory / "asset.glb", tmp_path / "new-revision"
    local_process.process(tmp_path, request, out, source, manifest)
    if mutation == "source":
        source.write_bytes(source.read_bytes().replace(b"2.0", b"2.1"))
    elif mutation == "request":
        request = request.model_copy(update={"segmentation_view": 1})
    elif mutation == "context":
        context = tmp_path / ".work/parts/context.json"
        write_json(context, read_json(context) | {"changed": True})
    else:
        (out / "generated.glb").write_bytes(b"changed-output")
    with pytest.raises(ValueError, match="changed|does not match"):
        local_process.process(tmp_path, request, out, source, manifest, resume=True)
    assert len(calls) == 1


def test_unavailable_local_backend_fails_without_falling_back_to_paid_provider(tmp_path, local_source, monkeypatch):
    from asset_auto import local_rig

    calls = []

    def unavailable(*args, **kwargs):
        calls.append("local")
        raise FileNotFoundError("test local rig model unavailable")

    monkeypatch.setattr(local_rig, "generate", unavailable)
    monkeypatch.setattr(pipeline, "executable", lambda *args: "test-blender")
    with pytest.raises(RuntimeError, match="local rig model unavailable"):
        pipeline.postprocess(tmp_path, PostprocessRequest.model_validate(request_payload()))
    assert calls == ["local"]
    assert len(Store(tmp_path).list()) == 1


def test_prepare_segmentation_writes_context_outside_completed_asset(tmp_path, local_source, monkeypatch):
    from asset_auto import local_parts

    directory, _ = local_source
    original = {path.name: path.read_bytes() for path in directory.iterdir()}
    calls = []

    def prepare(root, source, out):
        calls.append((source, out))
        assert out.is_relative_to(tmp_path / ".work/segment-contexts")
        write_json(out / "context.json", {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
        return {"context": str(out / "context.json"), "views": []}

    monkeypatch.setattr(local_parts, "prepare", prepare)
    monkeypatch.setattr(pipeline, "executable", lambda *args: "test-blender")
    result = pipeline.prepare_segmentation(tmp_path, "local-character", "r-source")
    assert result["source_asset_id"] == "local-character"
    assert result["source_revision"] == "r-source"
    assert len(calls) == 1
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == original
    assert len(Store(tmp_path).list()) == 1


def test_prepare_segmentation_rejects_rigged_source_before_rendering(tmp_path, local_source, monkeypatch):
    from asset_auto import local_parts

    prepared_request(tmp_path, local_source, "animate")

    def denied(*args, **kwargs):
        raise AssertionError("Rigged input must be rejected before preparing static segmentation context")

    monkeypatch.setattr(local_parts, "prepare", denied)
    with pytest.raises(ValueError, match="static revision"):
        pipeline.prepare_segmentation(tmp_path, "local-character", "r-source")


def test_local_backend_metadata_cannot_replace_caller_integrity_bindings(tmp_path, local_source, monkeypatch):
    from asset_auto import local_process, local_rig

    request = PostprocessRequest.model_validate(request_payload())
    directory, manifest = local_source
    source, out = directory / "asset.glb", tmp_path / "new-revision"
    expected_source = hashlib.sha256(source.read_bytes()).hexdigest()
    expected_binding = hashlib.sha256(json.dumps({
        "source_sha256": expected_source, "request": request.model_dump(),
    }, sort_keys=True).encode()).hexdigest()

    def backend(root, value, folder, input_file):
        (folder / "generated.glb").write_bytes(input_file.read_bytes())
        return {
            "provider": "tripo", "operation": "segment", "credits_consumed": 99,
            "binding_sha256": "unrelated-backend-binding", "source_sha256": "wrong-source",
            "generated_sha256": "wrong-output",
        }

    monkeypatch.setattr(local_rig, "generate", backend)
    result = local_process.process(tmp_path, request, out, source, manifest)
    assert result["provider"] == "local" and result["operation"] == "rig"
    assert result["credits_consumed"] == 0
    assert result["binding_sha256"] == expected_binding
    assert result["source_sha256"] == expected_source
    assert result["generated_sha256"] == expected_source
    assert local_process.process(tmp_path, request, out, source, manifest, resume=True) == result


def test_relative_segmentation_context_uses_runtime_root_from_another_project(tmp_path, local_source, monkeypatch):
    from asset_auto import local_process

    request = prepared_request(tmp_path, local_source, "segment").model_copy(update={
        "segmentation_context": ".work/parts/context.json",
    })
    other_project = tmp_path / "other-project"
    other_project.mkdir()
    monkeypatch.chdir(other_project)
    calls = []
    install_mock_local_backend(monkeypatch, "segment", calls)
    result = pipeline.postprocess_plan(tmp_path, request)
    assert result["context"] == str(tmp_path / ".work/parts/context.json")
    assert result["context_source_sha256"] == local_source[1]["files"]["asset.glb"]["sha256"]
    directory, manifest = local_source
    processed = local_process.process(tmp_path, request, tmp_path / "new-revision", directory / "asset.glb", manifest)
    assert processed["provider"] == "local"
    assert len(calls) == 1


def test_segmentation_backend_resolves_relative_context_before_installation_check(tmp_path, local_source, monkeypatch):
    from asset_auto import local_parts

    request = prepared_request(tmp_path, local_source, "segment").model_copy(update={
        "segmentation_context": ".work/parts/context.json",
    })
    other_project = tmp_path / "other-project"
    other_project.mkdir()
    monkeypatch.chdir(other_project)
    calls = []

    def stop_at_installation(root):
        calls.append(root)
        raise RuntimeError("test stopped at installation preflight")

    monkeypatch.setattr(local_parts, "installed", stop_at_installation)
    with pytest.raises(RuntimeError, match="installation preflight"):
        local_parts.segment(tmp_path, request, tmp_path / "new-revision", local_source[0] / "asset.glb")
    assert calls == [tmp_path.resolve()]
    assert not (tmp_path / "new-revision").exists()
