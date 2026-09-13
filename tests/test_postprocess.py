"""Offline contract and recovery checks for optional paid mesh processing."""

import hashlib
import json
import math
import socket
import struct
import sys

import pytest
from pydantic import ValidationError

from asset_auto import cli, jobs, pipeline, tripo, tripo_process
from asset_auto.models import AssetSpec, EditRequest, PostprocessRequest
from asset_auto.store import Store, read_json, write_json


def glb_bytes(document=None, binary=None):
    if binary is None:
        binary = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    if document is None:
        document = {
            "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"name": "original-mesh", "mesh": 0, "translation": [0.25, 0, -0.5]}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "buffers": [{"byteLength": len(binary)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(binary)}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                           "min": [0, 0, 0], "max": [1, 1, 0]}],
        }
    encoded = json.dumps(document).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<I4s", len(encoded), b"JSON") + encoded + struct.pack("<I4s", len(binary), b"BIN\0") + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def glb_chunks(raw):
    chunks = []
    offset = 12
    while offset < len(raw):
        length, chunk_type = struct.unpack_from("<I4s", raw, offset)
        chunks.append((chunk_type, raw[offset + 8:offset + 8 + length]))
        offset += 8 + length
    return chunks


@pytest.fixture(autouse=True)
def isolated_remote_environment(monkeypatch):
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY_FILE", raising=False)

    def denied(*args, **kwargs):
        raise AssertionError("Postprocessing tests must not access credentials or the network")

    monkeypatch.setattr(tripo, "api_key", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def source_asset(tmp_path):
    revision, directory = Store(tmp_path).new_revision("test-character")
    (directory / "asset.glb").write_bytes(glb_bytes())
    (directory / "source.blend").write_bytes(b"preserved original source")
    digest = hashlib.sha256(glb_bytes()).hexdigest()
    manifest = {
        "asset_id": "test-character", "revision": revision,
        "created_at": "2026-09-12T00:00:00Z", "provider": "trellis",
        "spec": AssetSpec(asset_id="test-character", image="reference.png").model_dump(),
        "files": {"asset.glb": {"sha256": digest, "bytes": len(glb_bytes())}},
        "inspection": {"triangle_budget": 12000, "dimensions": [1, 1, 2], "parts": [{"name": "body"}]},
    }
    write_json(directory / "manifest.json", manifest)
    return directory, manifest


def request_for(source_asset, operation="rig", **changes):
    _, manifest = source_asset
    values = {"asset_id": manifest["asset_id"], "revision": manifest["revision"], "operation": operation,
              "provider": "tripo"}
    return PostprocessRequest.model_validate(values | changes)


@pytest.mark.parametrize("operation", ["rig", "animate", "segment"])
def test_explicit_processing_defaults_to_100_credit_budget(operation):
    request = PostprocessRequest(asset_id="test-character", revision="r1", operation=operation, provider="tripo")
    assert request.max_credits == 100
    assert request.provider == "tripo"
    assert request.rig_type == "biped"
    assert request.rig_forward_axis == "+z"
    assert request.animation == "walk"
    assert request.animate_in_place is True


@pytest.mark.parametrize(
    "changes",
    [
        {"max_credits": 0}, {"max_credits": -1}, {"max_credits": 100001}, {"max_credits": 1.5},
        {"max_credits": None}, {"provider": "trellis"}, {"operation": "guess"}, {"animation": "jump"},
        {"rig_type": "quadruped"}, {"rig_model": "latest"}, {"segmentation_granularity": "unlimited"},
        {"triangle_budget": 11}, {"revision": "../parent"}, {"api_key": "forbidden-test-value"},
        {"rig_forward_axis": "+y"}, {"rig_forward_axis": "unknown"},
    ],
)
def test_processing_schema_rejects_unsupported_or_unsafe_requests(changes):
    with pytest.raises(ValidationError):
        PostprocessRequest.model_validate(
            {"asset_id": "test-character", "revision": "r1", "operation": "rig", "provider": "tripo"} | changes
        )


def test_modified_completed_source_is_rejected_before_paid_work(tmp_path, source_asset, monkeypatch):
    directory, _ = source_asset
    (directory / "asset.glb").write_bytes(glb_bytes() + b"tampered")
    # Preserve a valid GLB header so the provenance check, not basic parsing, catches the mutation.
    raw = bytearray((directory / "asset.glb").read_bytes())
    struct.pack_into("<I", raw, 8, len(raw))
    (directory / "asset.glb").write_bytes(raw)

    def denied(*args, **kwargs):
        raise AssertionError("A changed source must be rejected before allocating a revision or invoking tools")

    monkeypatch.setattr(pipeline, "executable", denied)
    monkeypatch.setattr(Store, "new_revision", denied)
    with pytest.raises(ValueError, match="Source GLB changed"):
        pipeline.postprocess(tmp_path, request_for(source_asset))


def test_animate_requires_verified_tripo_rig_parent(tmp_path, source_asset):
    directory, manifest = source_asset
    request = request_for(source_asset, "animate")
    with pytest.raises(ValueError, match="completed rigged revision"):
        pipeline.processing_source(tmp_path, request)
    manifest["inspection"]["rigging"] = {"armatures": [{"bones": 32}]}
    write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError, match="completed Tripo rig"):
        pipeline.processing_source(tmp_path, request)
    manifest["remote_processing"] = {"operation": "rig", "rig_task_id": "recorded-rig-123"}
    write_json(directory / "manifest.json", manifest)
    raw, _, digest = pipeline.processing_source(tmp_path, request)
    assert raw == directory / "asset.glb"
    assert digest == hashlib.sha256(raw.read_bytes()).hexdigest()


@pytest.mark.parametrize("operation", ["rig", "segment"])
def test_static_processing_does_not_destroy_existing_rig(tmp_path, source_asset, operation):
    directory, manifest = source_asset
    manifest["inspection"]["rigging"] = {"armatures": [{"bones": 32}]}
    write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError, match="static source"):
        pipeline.processing_source(tmp_path, request_for(source_asset, operation))
    with pytest.raises(ValueError, match="Static part edits cannot modify a rigged asset"):
        pipeline.edit_asset(tmp_path, EditRequest(
            asset_id=manifest["asset_id"], revision=manifest["revision"], changes=[{"part": "body", "scale": [2, 2, 2]}]
        ))


def test_processing_failure_exposes_recovery_revision_and_preserves_parent(tmp_path, source_asset, monkeypatch):
    directory, _ = source_asset
    originals = {name: (directory / name).read_bytes() for name in ("asset.glb", "source.blend", "manifest.json")}
    recovery = []
    monkeypatch.setattr(pipeline, "executable", lambda *args: "unused-test-blender")

    def fail(*args, **kwargs):
        raise RuntimeError("remote task still running")

    monkeypatch.setattr(pipeline, "finish_postprocess", fail)
    with pytest.raises(RuntimeError, match="revision="):
        pipeline.postprocess(tmp_path, request_for(source_asset), on_revision=recovery.append)
    assert len(recovery) == 1
    assert recovery[0]["operation"] == "resume-tripo-process"
    out = tmp_path / ".assets" / recovery[0]["asset_id"] / recovery[0]["revision"]
    record = read_json(out / "processing.json")
    assert record["source_sha256"] == hashlib.sha256(originals["asset.glb"]).hexdigest()
    assert record["request"]["max_credits"] == 100
    assert not (out / "manifest.json").exists()
    assert all((directory / name).read_bytes() == value for name, value in originals.items())
    assert len(Store(tmp_path).list()) == 1


def test_resume_rejects_processing_record_for_another_asset(tmp_path, source_asset):
    _, out = Store(tmp_path).new_revision("test-character")
    request = request_for(source_asset).model_dump() | {"asset_id": "other-character"}
    write_json(out / "processing.json", {"request": request, "source_sha256": "unused"})
    with pytest.raises(ValueError, match="does not match asset"):
        pipeline.resume_postprocess(tmp_path, "test-character", out.name)


class FakeProcessingProvider:
    """Fails closed for unexpected paid requests and supplies explicit task histories."""

    def __init__(self, out, *, balance=100, riggable=True, rig_type="biped", states=None, costs=None):
        self.out = out
        self.available = balance
        self.riggable = riggable
        self.rig_type = rig_type
        self.states = {key: iter(value) for key, value in (states or {}).items()}
        self.costs = {"rig-check": 0, "rig": 25, "animate": 10, "segment": 40} | (costs or {})
        self.calls = []
        self.create_error = None
        self.download_error = None

    def balance(self):
        self.calls.append(("balance",))
        return {"balance": self.available}

    def upload_model(self, source):
        self.calls.append(("upload", source.read_bytes()))
        return "private-upload-token"

    def request(self, method, endpoint, payload):
        assert method == "POST"
        name = {"/animations/rig-check": "rig-check", "/animations/rig": "rig",
                "/animations/retarget": "animate", "/mesh/segment": "segment"}[endpoint]
        self.calls.append(("create", name, payload))
        checkpoint = read_json(self.out / "postprocess-remote.json")
        stage = next(s for s in checkpoint["stages"] if s["name"] == name)
        assert stage["state"] == "submitting", "State must be durable before the paid POST"
        assert "task_id" not in stage
        if self.create_error:
            raise self.create_error
        return {"task_id": f"known-{name}-123"}

    def task(self, task_id):
        self.calls.append(("task", task_id))
        checkpoint = read_json(self.out / "postprocess-remote.json")
        stage = next(s for s in checkpoint["stages"] if s.get("task_id") == task_id)
        name = stage["name"]
        state = next(self.states[name]) if name in self.states else "success"
        result = {"status": state, "progress": 100, "credits_consumed": self.costs[name]}
        result["output"] = (
            {"riggable": self.riggable, "rig_type": self.rig_type} if name == "rig-check"
            else {"model_url": "https://cdn.example.com/mesh.glb?private=vendor-signature"}
        )
        return result

    def download(self, url, target):
        self.calls.append(("download",))
        if self.download_error:
            raise self.download_error
        target.write_bytes(glb_bytes())


def process_source(tmp_path, source_asset, request, client, *, resume=False, poll_timeout=300):
    directory, manifest = source_asset
    return tripo_process.process(
        tmp_path, request, client.out, directory / "asset.glb", manifest,
        client=client, resume=resume, poll_timeout=poll_timeout,
    )


def creates(client, name=None):
    return [call for call in client.calls if call[0] == "create" and (name is None or call[1] == name)]


@pytest.mark.parametrize("operation,cost", [("rig", 25), ("animate", 10), ("segment", 40)])
def test_processing_plan_is_local_and_honors_user_budget(operation, cost, tmp_path, source_asset, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Planning must not instantiate a remote client")

    monkeypatch.setattr(tripo_process, "TripoClient", denied)
    before = set(tmp_path.rglob("*"))
    plan = tripo_process.plan(request_for(source_asset, operation, max_credits=cost - 1))
    assert plan["estimated_credits"] == cost
    assert plan["max_credits"] == cost - 1
    assert plan["within_budget"] is False
    assert "not a server-enforced" in plan["budget_scope"]
    assert set(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("budget,balance", [(24, 100), (25, 24)])
def test_processing_budget_and_balance_stop_before_upload(tmp_path, source_asset, budget, balance):
    client = FakeProcessingProvider(tmp_path / "revision", balance=balance)
    with pytest.raises(tripo.TripoError, match="credits|max_credits"):
        process_source(tmp_path, source_asset, request_for(source_asset, max_credits=budget), client)
    assert not any(c[0] in ("create", "upload", "download") for c in client.calls)
    assert not client.out.exists()


@pytest.mark.parametrize("riggable,rig_type", [(False, "biped"), (True, "quadruped"), ("true", "biped")])
def test_free_rig_check_must_confirm_biped_before_paid_rig(tmp_path, source_asset, riggable, rig_type):
    client = FakeProcessingProvider(tmp_path / "revision", riggable=riggable, rig_type=rig_type)
    with pytest.raises(tripo.TripoError, match="no paid rig task"):
        process_source(tmp_path, source_asset, request_for(source_asset), client)
    assert [c[1] for c in creates(client)] == ["rig-check"]
    assert read_json(client.out / "postprocess-remote.json")["state"] == "not_riggable"
    assert not (client.out / "generated.glb").exists()
    with pytest.raises(tripo.TripoError, match="no paid rig task"):
        process_source(tmp_path, source_asset, request_for(source_asset), client, resume=True)
    assert len(creates(client)) == 1


def test_rig_then_animation_uses_recorded_rig_id_without_reupload(tmp_path, source_asset):
    directory, manifest = source_asset
    rig_client = FakeProcessingProvider(tmp_path / "rig")
    rig_result = process_source(tmp_path, source_asset, request_for(source_asset), rig_client)
    assert [c[1] for c in creates(rig_client)] == ["rig-check", "rig"]
    assert rig_result["rig_task_id"] == "known-rig-123"
    assert rig_result["credits_consumed"] == 25
    assert rig_result["credits_fully_reported"] is True
    assert creates(rig_client, "rig")[0][2] == {
        "input": "private-upload-token", "model": "v1.0-20240301", "rig_type": "biped",
        "spec": "tripo", "out_format": "glb",
    }
    manifest["remote_processing"] = rig_result
    animation_client = FakeProcessingProvider(tmp_path / "animation")
    animated = process_source(tmp_path, (directory, manifest), request_for(source_asset, "animate", animation="run"),
                              animation_client)
    assert [c[1] for c in creates(animation_client)] == ["animate"]
    assert not any(c[0] == "upload" for c in animation_client.calls)
    assert creates(animation_client)[0][2] == {
        "input": "known-rig-123", "animation": "preset:biped:run", "out_format": "glb",
        "bake_animation": True, "export_with_geometry": True, "animate_in_place": True,
    }
    assert animated["rig_task_id"] == "known-rig-123"
    assert animated["credits_consumed"] == 10
    # A second requested motion must still use the original rig, not the previous animation task.
    manifest["remote_processing"] = animated
    idle_client = FakeProcessingProvider(tmp_path / "idle")
    process_source(tmp_path, (directory, manifest), request_for(source_asset, "animate", animation="idle"), idle_client)
    assert creates(idle_client)[0][2]["input"] == "known-rig-123"


def test_semantic_segmentation_uses_model_v2_and_named_granularity(tmp_path, source_asset):
    client = FakeProcessingProvider(tmp_path / "segmented")
    result = process_source(tmp_path, source_asset,
                            request_for(source_asset, "segment", segmentation_granularity="detailed"), client)
    assert creates(client)[0][2] == {
        "input": "private-upload-token", "model": "v2.0-20260430",
        "segmentation_granularity": "detailed", "split_by_connectivity": True,
    }
    assert result["credits_consumed"] == 40
    assert result["model"] == "v2.0-20260430"
    assert result["state"] == "success"
    public = json.dumps(result)
    assert "private-upload-token" not in public
    assert "file_token" not in public
    assert "vendor-signature" not in public
    assert "model_url" not in public
    assert "vendor-signature" not in (client.out / "postprocess-remote.json").read_text()


@pytest.mark.parametrize("pending_stage", ["rig-check", "rig"])
def test_waiting_processing_resumes_each_known_stage_once(tmp_path, source_asset, pending_stage):
    client = FakeProcessingProvider(tmp_path / "revision", states={pending_stage: ["running", "success"]})
    request = request_for(source_asset)
    with pytest.raises(tripo.TripoError, match="still processing"):
        process_source(tmp_path, source_asset, request, client, poll_timeout=0)
    checkpoint = read_json(client.out / "postprocess-remote.json")
    stage = next(s for s in checkpoint["stages"] if s["name"] == pending_stage)
    assert stage["task_id"] == f"known-{pending_stage}-123"
    assert checkpoint["state"] == "waiting"
    with pytest.raises(tripo.TripoError, match="resume"):
        process_source(tmp_path, source_asset, request, client)
    result = process_source(tmp_path, source_asset, request, client, resume=True)
    assert result["state"] == "success"
    assert [c[1] for c in creates(client)] == ["rig-check", "rig"]
    assert sum(c[0] == "upload" for c in client.calls) == 1


def test_successful_rig_check_can_resume_before_paid_submission(tmp_path, source_asset):
    client = FakeProcessingProvider(tmp_path / "revision")
    original_task = client.task

    def balance_drops_after_check(task_id):
        result = original_task(task_id)
        if task_id == "known-rig-check-123":
            client.available = 0
        return result

    client.task = balance_drops_after_check
    request = request_for(source_asset)
    with pytest.raises(tripo.TripoError, match="Insufficient"):
        process_source(tmp_path, source_asset, request, client)
    assert [c[1] for c in creates(client)] == ["rig-check"]
    client.available = 100
    result = process_source(tmp_path, source_asset, request, client, resume=True)
    assert result["state"] == "success"
    assert [c[1] for c in creates(client)] == ["rig-check", "rig"]
    assert sum(c == ("task", "known-rig-check-123") for c in client.calls) == 1


def test_download_failure_resumes_known_task_without_paid_replacement(tmp_path, source_asset):
    client = FakeProcessingProvider(tmp_path / "revision")
    client.download_error = tripo.TripoError("temporary download failure")
    request = request_for(source_asset, "segment")
    with pytest.raises(tripo.TripoError, match="download"):
        process_source(tmp_path, source_asset, request, client)
    checkpoint = read_json(client.out / "postprocess-remote.json")
    assert checkpoint["stages"][0]["task_id"] == "known-segment-123"
    assert "download_sha256" not in checkpoint
    client.download_error = None
    result = process_source(tmp_path, source_asset, request, client, resume=True)
    assert result["state"] == "success"
    assert len(creates(client)) == 1
    assert sum(c[0] == "upload" for c in client.calls) == 1


def test_ambiguous_processing_post_is_never_retried(tmp_path, source_asset):
    client = FakeProcessingProvider(tmp_path / "revision")
    client.create_error = TimeoutError("private-upload-token secret diagnostic")
    request = request_for(source_asset, "segment")
    with pytest.raises(tripo.TripoError, match="outcome is unknown") as caught:
        process_source(tmp_path, source_asset, request, client)
    assert "private-upload-token" not in str(caught.value)
    assert "secret diagnostic" not in str(caught.value)
    checkpoint = read_json(client.out / "postprocess-remote.json")
    assert checkpoint["stages"][0]["state"] == "submission_unknown"
    for resume in (True, False):
        with pytest.raises(tripo.TripoError, match="unknown submission|resume"):
            process_source(tmp_path, source_asset, request, client, resume=resume)
    assert len(creates(client)) == 1


def test_killed_during_processing_post_cannot_be_treated_as_pending(tmp_path, source_asset):
    client = FakeProcessingProvider(tmp_path / "revision")
    request = request_for(source_asset, "segment")
    client.create_error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        process_source(tmp_path, source_asset, request, client)
    assert read_json(client.out / "postprocess-remote.json")["stages"][0]["state"] == "submitting"
    with pytest.raises(tripo.TripoError, match="unknown submission"):
        process_source(tmp_path, source_asset, request, client, resume=True)
    assert len(creates(client)) == 1


@pytest.mark.parametrize("mutation", ["request", "source", "stages", "budget"])
def test_resume_rejects_changed_source_request_or_checkpoint(tmp_path, source_asset, mutation):
    client = FakeProcessingProvider(tmp_path / "revision", states={"segment": ["running"]})
    request = request_for(source_asset, "segment")
    with pytest.raises(tripo.TripoError, match="still processing"):
        process_source(tmp_path, source_asset, request, client, poll_timeout=0)
    if mutation == "request":
        request = request_for(source_asset, "segment", segmentation_granularity="detailed")
    elif mutation == "source":
        source = source_asset[0] / "asset.glb"
        source.write_bytes(source.read_bytes().replace(b"2.0", b"2.1"))
    else:
        checkpoint = read_json(client.out / "postprocess-remote.json")
        if mutation == "stages":
            checkpoint["stages"][0]["endpoint"] = "/animations/rig"
        else:
            checkpoint["max_credits"] = 1000
        write_json(client.out / "postprocess-remote.json", checkpoint)
    calls = list(client.calls)
    with pytest.raises(tripo.TripoError, match="changed|does not match"):
        process_source(tmp_path, source_asset, request, client, resume=True)
    assert client.calls == calls


def test_reported_cost_blocks_next_stage_when_budget_would_be_exceeded(tmp_path, source_asset):
    client = FakeProcessingProvider(tmp_path / "revision", costs={"rig-check": 80})
    with pytest.raises(tripo.TripoError, match="prior cost.*exceeds max_credits"):
        process_source(tmp_path, source_asset, request_for(source_asset), client)
    assert [c[1] for c in creates(client)] == ["rig-check"]
    checkpoint = read_json(client.out / "postprocess-remote.json")
    assert checkpoint["credits_consumed"] == 80


def test_verified_processing_download_resumes_offline(tmp_path, source_asset, monkeypatch):
    client = FakeProcessingProvider(tmp_path / "revision")
    request = request_for(source_asset, "segment")
    first = process_source(tmp_path, source_asset, request, client)

    def denied(*args, **kwargs):
        raise AssertionError("Verified local raw output must not need credentials or network on recovery")

    monkeypatch.setattr(tripo_process, "TripoClient", denied)
    recovered = tripo_process.process(
        tmp_path, request, client.out, source_asset[0] / "asset.glb", source_asset[1], resume=True,
    )
    assert recovered == first
    assert recovered["download_sha256"] == hashlib.sha256(glb_bytes()).hexdigest()


@pytest.mark.parametrize("state", ["failed", "cancelled", "banned", "expired", "unrecognized"])
def test_terminal_processing_states_do_not_create_replacement_tasks(tmp_path, source_asset, state):
    client = FakeProcessingProvider(tmp_path / "revision", states={"segment": [state]})
    with pytest.raises(tripo.TripoError, match="status"):
        process_source(tmp_path, source_asset, request_for(source_asset, "segment"), client)
    assert len(creates(client)) == 1
    assert not any(c[0] == "download" for c in client.calls)
    assert read_json(client.out / "postprocess-remote.json")["stages"][0]["task_id"] == "known-segment-123"


@pytest.mark.parametrize("changes", [{"rig_type": "quadruped"}, {"rig_model": "v9-new-rig"}])
def test_animation_rejects_incompatible_recorded_rig_before_network(tmp_path, source_asset, changes):
    directory, manifest = source_asset
    manifest["remote_processing"] = {"rig_task_id": "known-rig-123"} | changes
    client = FakeProcessingProvider(tmp_path / "revision")
    with pytest.raises(tripo.TripoError, match="compatible"):
        process_source(tmp_path, (directory, manifest), request_for(source_asset, "animate"), client)
    assert client.calls == []


def test_model_upload_uses_exact_glb_and_fixed_multipart_name(tmp_path, monkeypatch):
    source = tmp_path / "private-local-filename.glb"
    source.write_bytes(glb_bytes())
    client = object.__new__(tripo.TripoClient)
    calls = []

    def upload(method, endpoint, body, content_type):
        calls.append((method, endpoint, body, content_type))
        return {"file_token": "private-test-upload-token"}

    monkeypatch.setattr(client, "request", upload)
    assert client.upload_model(source) == "private-test-upload-token"
    method, endpoint, body, content_type = calls[0]
    assert method == "POST" and endpoint == "/files"
    assert source.read_bytes() in body
    assert b'filename="model.glb"' in body and b"model/gltf-binary" in body
    assert b"private-local-filename" not in body
    assert content_type.startswith("multipart/form-data; boundary=")
    calls.clear()
    monkeypatch.setattr(tripo, "MAX_UPLOAD_MODEL_BYTES", len(glb_bytes()) - 1)
    with pytest.raises(ValueError, match="150 MB"):
        client.upload_model(source)
    assert calls == []


@pytest.mark.parametrize("part_count", [1, 2])
def test_completed_segmentation_keeps_parent_and_marks_semantic_review_pending(
    tmp_path, source_asset, monkeypatch, part_count
):
    source, parent = source_asset
    original = (source / "manifest.json").read_bytes()
    created_clients = []

    def client_factory(root):
        # The pipeline allocated its revision before asking for credentials.
        output = next(p.parent for p in (tmp_path / ".assets").glob("*/*/processing.json"))
        client = FakeProcessingProvider(output)
        created_clients.append(client)
        return client

    def worker(root, request, out):
        assert request["character"] is False and request["part_previews"] is True
        assert request["target_height"] == 2
        (out / "asset.glb").write_bytes(glb_bytes())
        (out / "source.blend").write_bytes(b"processed-test-source")
        write_json(out / "inspection.json", {
            "passed": True, "errors": [], "triangle_budget": 12000, "dimensions": [1, 1, 2],
            "parts": [{"name": f"part-{n}"} for n in range(part_count)],
        })

    monkeypatch.setattr(tripo_process, "TripoClient", client_factory)
    monkeypatch.setattr(pipeline, "executable", lambda *args: "test-blender")
    monkeypatch.setattr(pipeline, "blender", worker)
    result = pipeline.postprocess(tmp_path, request_for(source_asset, "segment"))
    assert result["parent"] == parent["revision"]
    assert result["revision"] != parent["revision"]
    assert result["visual_review"] == "pending"
    assert result["inspection"]["segmentation"]["semantic_review"] == "pending"
    assert result["inspection"]["passed"] is (part_count >= 2)
    assert (source / "manifest.json").read_bytes() == original
    assert "private-upload-token" not in json.dumps(result)
    assert "vendor-signature" not in json.dumps(result)
    assert "file_token" not in json.dumps(result)
    assert result["remote_processing"]["credits_consumed"] == 40
    assert len(created_clients) == 1
    assert len(Store(tmp_path).list()) == 2
    assert pipeline.resume_postprocess(tmp_path, result["asset_id"], result["revision"]) == result
    assert len(created_clients) == 1, "Completed revisions must not cause remote processing again"


@pytest.mark.parametrize("background", [False, True])
def test_cli_routes_processing_and_resume_without_losing_revision(tmp_path, source_asset, monkeypatch, capsys, background):
    request = request_for(source_asset, "segment")
    spec_path = tmp_path / "processing-request.json"
    write_json(spec_path, request.model_dump())
    calls = []

    def direct(root, payload):
        calls.append(("direct", root, payload.model_dump()))
        return {"revision": "r-new"}

    def submit(root, operation, payload):
        calls.append((operation, root, payload))
        return {"job_id": "test-job"}

    monkeypatch.setattr(cli, "postprocess", direct)
    monkeypatch.setattr(cli.jobs, "submit", submit)
    argv = ["assetctl", "--root", str(tmp_path), "tripo-process", str(spec_path)]
    monkeypatch.setattr(sys, "argv", argv + (["--async"] if background else []))
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result == ({"job_id": "test-job"} if background else {"revision": "r-new"})
    assert calls[0][0] == ("tripo-process" if background else "direct")
    assert calls[0][2]["max_credits"] == 100

    def resume(root, asset_id, revision):
        calls.append(("resume", root, {"asset_id": asset_id, "revision": revision}))
        return {"revision": revision}

    monkeypatch.setattr(cli, "resume_postprocess", resume)
    write_json(tmp_path / ".assets/test-character/r-new/processing.json", {"request": request.model_dump()})
    argv = ["assetctl", "--root", str(tmp_path), "resume-tripo-process", "test-character", "r-new"]
    monkeypatch.setattr(sys, "argv", argv + (["--async"] if background else []))
    assert cli.main() == 0
    assert calls[-1][0] == ("resume-tripo-process" if background else "resume")
    assert calls[-1][2] == {"asset_id": "test-character", "revision": "r-new"}


def test_failed_processing_job_persists_same_revision_for_resume(tmp_path, source_asset, monkeypatch):
    request = request_for(source_asset, "segment")
    directory = tmp_path / ".assets/jobs/test-processing-job"
    write_json(directory / "job.json", {
        "job_id": "test-processing-job", "operation": "tripo-process",
        "state": "queued", "payload": request.model_dump(),
    })

    def pending(root, payload, *, on_revision):
        recovery = {"asset_id": payload.asset_id, "revision": "r-pending", "operation": "resume-tripo-process"}
        on_revision(recovery)
        durable = read_json(directory / "job.json")
        assert durable["recovery"] == recovery
        raise tripo.TripoError("Tripo is still processing; resume the known revision")

    monkeypatch.setattr(jobs, "postprocess", pending)
    result = jobs.run(tmp_path, "test-processing-job")
    assert result["state"] == "failed"
    assert result["recovery"]["revision"] == "r-pending"
    assert jobs.status(tmp_path, "test-processing-job")["recovery"] == result["recovery"]
    assert "file_token" not in json.dumps(result)


def test_resume_job_runs_recovery_route_instead_of_new_paid_process(tmp_path, source_asset, monkeypatch):
    directory = tmp_path / ".assets/jobs/test-resume-job"
    write_json(directory / "job.json", {
        "job_id": "test-resume-job", "operation": "resume-tripo-process", "state": "queued",
        "payload": {"asset_id": "test-character", "revision": "r-pending"},
    })
    write_json(tmp_path / ".assets/test-character/r-pending/processing.json", {
        "request": request_for(source_asset, "segment").model_dump(),
    })
    calls = []

    def resume(root, asset_id, revision):
        calls.append((asset_id, revision))
        return {"asset_id": asset_id, "revision": revision, "state": "numeric_checks_passed"}

    def denied(*args, **kwargs):
        raise AssertionError("Recovery must never start a new processing request")

    monkeypatch.setattr(jobs, "resume_postprocess", resume)
    monkeypatch.setattr(jobs, "postprocess", denied)
    result = jobs.run(tmp_path, "test-resume-job")
    assert result["state"] == "succeeded"
    assert calls == [("test-character", "r-pending")]


@pytest.mark.parametrize(
    "axis,yaw,forward",
    [("+z", 90, (0, 0, 1)), ("-z", -90, (0, 0, -1)), ("-x", 180, (-1, 0, 0)), ("+x", 0, (1, 0, 0))],
)
def test_rig_preparation_rotates_declared_forward_axis_and_preserves_geometry(
    tmp_path, source_asset, axis, yaw, forward
):
    directory, _ = source_asset
    original = (directory / "asset.glb").read_bytes()
    client = FakeProcessingProvider(tmp_path / "rig")
    request = request_for(source_asset, rig_forward_axis=axis)
    result = process_source(tmp_path, source_asset, request, client)
    prepared = client.out / "rig-input.glb"
    assert prepared.is_file()
    assert result["rig_forward_axis"] == axis
    assert result["provider_forward_axis"] == "+x"
    assert result["input_rotation_y_degrees"] == yaw
    assert result["output_yaw_degrees"] == -yaw
    assert result["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["prepared_sha256"] == hashlib.sha256(prepared.read_bytes()).hexdigest()
    assert result["prepared_file"] == "rig-input.glb"
    assert (directory / "asset.glb").read_bytes() == original
    assert next(c for c in client.calls if c[0] == "upload")[1] == prepared.read_bytes()
    original_chunks = glb_chunks(original)
    prepared_chunks = glb_chunks(prepared.read_bytes())
    assert [c for c in original_chunks if c[0] != b"JSON"] == [c for c in prepared_chunks if c[0] != b"JSON"]
    document = json.loads(prepared_chunks[0][1])
    original_document = json.loads(original_chunks[0][1])
    assert document["meshes"] == original_document["meshes"]
    assert document["nodes"][:len(original_document["nodes"])] == original_document["nodes"]
    if yaw == 0:
        assert prepared.read_bytes() == original
    else:
        root = document["nodes"][document["scenes"][document.get("scene", 0)]["nodes"][0]]
        assert root["rotation"] == pytest.approx([0, math.sin(math.radians(yaw / 2)), 0, math.cos(math.radians(yaw / 2))])
        assert root["children"] == original_document["scenes"][0]["nodes"]
    x, y, z = forward
    radians = math.radians(result["input_rotation_y_degrees"])
    assert (x * math.cos(radians) + z * math.sin(radians), y,
            -x * math.sin(radians) + z * math.cos(radians)) == pytest.approx((1, 0, 0))


def test_scene_rotation_keeps_binary_unknown_chunks_and_animation_targets(tmp_path):
    from asset_auto.glb_transform import rotate_scene_y

    document = json.loads(glb_chunks(glb_bytes())[0][1])
    document["nodes"].append({"name": "second-root", "mesh": 0, "scale": [2, 1, 1]})
    document["scenes"] = [{"name": "first", "nodes": [0]}, {"name": "second", "nodes": [1]}]
    document["animations"] = [{"name": "original-action", "channels": [{"sampler": 0, "target": {"node": 0,
                               "path": "translation"}}], "samplers": [{"input": 0, "output": 0}]}]
    original = bytearray(glb_bytes(document=document))
    original += struct.pack("<I4s", 8, b"VEND") + b"metadata"
    struct.pack_into("<I", original, 8, len(original))
    source, target = tmp_path / "source.glb", tmp_path / "rotated.glb"
    source.write_bytes(original)
    rotate_scene_y(source, target, 90)
    transformed_chunks = glb_chunks(target.read_bytes())
    transformed = json.loads(transformed_chunks[0][1])
    assert source.read_bytes() == bytes(original)
    assert transformed["nodes"][:2] == document["nodes"]
    assert transformed["animations"] == document["animations"]
    assert transformed["accessors"] == document["accessors"]
    assert transformed["bufferViews"] == document["bufferViews"]
    for scene_index, expected_child in enumerate((0, 1)):
        root = transformed["nodes"][transformed["scenes"][scene_index]["nodes"][0]]
        assert root["children"] == [expected_child]
    assert [c for c in transformed_chunks if c[0] != b"JSON"] == [c for c in glb_chunks(original) if c[0] != b"JSON"]


@pytest.mark.parametrize("scene_roots", [[[0], [0]], [[0, 1], [1, 2]], [[0, 1], [1, 0]], [[0], [], [0, 2]]])
def test_shared_scene_roots_reuse_one_rotation_parent_per_original_node(tmp_path, scene_roots):
    from asset_auto.glb_transform import rotate_scene_y

    document = json.loads(glb_chunks(glb_bytes())[0][1])
    document["nodes"][0]["children"] = [3]
    document["nodes"].extend([
        {"name": "second-root", "mesh": 0, "translation": [2, 0, 0]},
        {"name": "third-root", "mesh": 0, "scale": [2, 1, 1]},
        {"name": "original-child", "mesh": 0, "translation": [0, 1, 0]},
    ])
    document["scenes"] = [{"name": f"scene-{index}", "nodes": roots} for index, roots in enumerate(scene_roots)]
    original = glb_bytes(document=document)
    source, target = tmp_path / "source.glb", tmp_path / "rotated.glb"
    source.write_bytes(original)
    rotate_scene_y(source, target, 90)
    transformed_chunks = glb_chunks(target.read_bytes())
    transformed = json.loads(transformed_chunks[0][1])
    nodes = transformed["nodes"]
    assert nodes[:len(document["nodes"])] == document["nodes"]
    expected_roots = {root for roots in scene_roots for root in roots}
    assert len(nodes) == len(document["nodes"]) + len(expected_roots)
    wrapper_by_original = {}
    parents = {index: [] for index in range(len(nodes))}
    for index, node in enumerate(nodes):
        for child_index in node.get("children", []):
            parents[child_index].append(index)
        if index >= len(document["nodes"]):
            assert len(node["children"]) == 1
            original_index = node["children"][0]
            assert original_index not in wrapper_by_original
            wrapper_by_original[original_index] = index
            assert node["rotation"] == pytest.approx([0, math.sqrt(0.5), 0, math.sqrt(0.5)])
    assert all(len(indices) <= 1 for indices in parents.values()), "glTF nodes may have at most one parent"
    assert set(wrapper_by_original) == expected_roots
    for scene, roots in zip(transformed["scenes"], scene_roots, strict=True):
        assert scene["nodes"] == [wrapper_by_original[root] for root in roots]
    assert source.read_bytes() == original
    assert transformed["meshes"] == document["meshes"]
    assert transformed["accessors"] == document["accessors"]
    assert [c for c in transformed_chunks if c[0] != b"JSON"] == [c for c in glb_chunks(original) if c[0] != b"JSON"]


@pytest.mark.parametrize("mutation", ["prepared-bytes", "prepared-hash", "source-axis", "output-yaw"])
def test_rig_resume_rejects_tampered_preparation_or_orientation(tmp_path, source_asset, mutation):
    client = FakeProcessingProvider(tmp_path / "rig", states={"rig": ["running"]})
    request = request_for(source_asset)
    with pytest.raises(tripo.TripoError, match="still processing"):
        process_source(tmp_path, source_asset, request, client, poll_timeout=0)
    if mutation == "prepared-bytes":
        prepared = client.out / "rig-input.glb"
        prepared.write_bytes(prepared.read_bytes().replace(b"original-mesh", b"modified-mesh"))
    else:
        checkpoint = read_json(client.out / "postprocess-remote.json")
        if mutation == "prepared-hash":
            checkpoint["prepared_sha256"] = "0" * 64
        elif mutation == "source-axis":
            checkpoint["rig_forward_axis"] = "-z"
        else:
            checkpoint["output_yaw_degrees"] = 90
        write_json(client.out / "postprocess-remote.json", checkpoint)
    before = list(client.calls)
    with pytest.raises(tripo.TripoError, match="changed|match|prepared|orientation"):
        process_source(tmp_path, source_asset, request, client, resume=True)
    assert client.calls == before


def test_animation_inherits_original_rig_orientation_instead_of_default_axis(tmp_path, source_asset):
    _, manifest = source_asset
    rig_client = FakeProcessingProvider(tmp_path / "rig")
    rigged = process_source(tmp_path, source_asset, request_for(source_asset, rig_forward_axis="-z"), rig_client)
    manifest["remote_processing"] = rigged
    request = request_for(source_asset, "animate")
    assert request.rig_forward_axis == "+z"
    proposed = tripo_process.plan(request, manifest)
    assert proposed["rig_forward_axis"] == "-z"
    assert proposed["input_rotation_y_degrees"] == -90
    assert proposed["output_yaw_degrees"] == 90
    client = FakeProcessingProvider(tmp_path / "walk")
    result = process_source(tmp_path, source_asset, request, client)
    assert result["rig_forward_axis"] == "-z"
    assert result["input_rotation_y_degrees"] == -90
    assert result["output_yaw_degrees"] == 90
    assert result["rig_task_id"] == "known-rig-123"
    assert creates(client)[0][2]["input"] == "known-rig-123"
    assert not any(c[0] == "upload" for c in client.calls)
    assert not (client.out / "rig-input.glb").exists()


def test_segmentation_uploads_original_mesh_without_rig_orientation_preparation(tmp_path, source_asset):
    original = (source_asset[0] / "asset.glb").read_bytes()
    client = FakeProcessingProvider(tmp_path / "segment")
    result = process_source(tmp_path, source_asset, request_for(source_asset, "segment", rig_forward_axis="-x"), client)
    assert next(c for c in client.calls if c[0] == "upload")[1] == original
    assert not (client.out / "rig-input.glb").exists()
    assert "input_rotation_y_degrees" not in result
    assert "output_yaw_degrees" not in result


def test_pipeline_animation_plan_reports_inherited_rig_orientation(tmp_path, source_asset):
    directory, manifest = source_asset
    manifest["inspection"]["rigging"] = {"armatures": [{"bones": 32}]}
    manifest["remote_processing"] = {
        "operation": "rig", "rig_task_id": "known-rig-123", "rig_forward_axis": "-z",
        "provider_forward_axis": "+x", "input_rotation_y_degrees": -90, "output_yaw_degrees": 90,
    }
    write_json(directory / "manifest.json", manifest)
    result = pipeline.postprocess_plan(tmp_path, request_for(source_asset, "animate"))
    assert result["rig_forward_axis"] == "-z"
    assert result["input_rotation_y_degrees"] == -90
    assert result["output_yaw_degrees"] == 90


@pytest.mark.parametrize("operation", ["rig", "animate"])
def test_pipeline_restores_source_orientation_for_rig_and_animated_export(
    tmp_path, source_asset, monkeypatch, operation
):
    directory, manifest = source_asset
    if operation == "animate":
        manifest["inspection"]["rigging"] = {"armatures": [{"bones": 32}]}
        manifest["remote_processing"] = {"operation": "rig", "rig_task_id": "known-rig-123"}
        write_json(directory / "manifest.json", manifest)

    def processed(root, request, out, source, parent, **kwargs):
        (out / "generated.glb").write_bytes(glb_bytes())
        return {"operation": operation, "rig_task_id": "known-rig-123", "output_yaw_degrees": -90}

    def worker(root, request, out):
        assert request["character"] is True
        assert request["input_yaw_degrees"] == -90
        assert request["require_animation"] is (operation == "animate")
        (out / "asset.glb").write_bytes(glb_bytes())
        (out / "source.blend").write_bytes(b"processed-character")
        write_json(out / "inspection.json", {
            "passed": True, "errors": [], "parts": [{"name": "body"}], "triangle_budget": 12000,
            "dimensions": [1, 1, 2], "rigging": {"armatures": [{"bones": 32}]},
        })

    monkeypatch.setattr(tripo_process, "process", processed)
    monkeypatch.setattr(pipeline, "executable", lambda *args: "test-blender")
    monkeypatch.setattr(pipeline, "blender", worker)
    result = pipeline.postprocess(tmp_path, request_for(source_asset, operation))
    assert result["remote_processing"]["output_yaw_degrees"] == -90
    assert result["asset_type"] == "character"


@pytest.mark.parametrize("operation", ["rig", "animate", "segment"])
def test_pre_local_defaults_tripo_checkpoint_resumes_without_resubmission(tmp_path, source_asset, operation):
    """New local-only schema defaults must not invalidate a known, already charged task."""
    if operation == "animate":
        source_asset[1]["remote_processing"] = {"operation": "rig", "rig_task_id": "original-rig-task"}
    request = request_for(source_asset, operation)
    client = FakeProcessingProvider(tmp_path / "processing", states={operation: ["running", "success"]})
    with pytest.raises(tripo.TripoError, match="still processing"):
        process_source(tmp_path, source_asset, request, client, poll_timeout=0)
    checkpoint = read_json(client.out / "postprocess-remote.json")
    legacy_fields = {
        "asset_id", "revision", "operation", "provider", "max_credits", "rig_type", "rig_model",
        "rig_forward_axis", "animation", "animate_in_place", "segmentation_granularity", "triangle_budget",
    }
    old_request = {key: value for key, value in request.model_dump().items() if key in legacy_fields}
    if operation != "rig":
        old_request.pop("rig_forward_axis")
    old_binding = {"request": old_request, "source_rig_task_id": "original-rig-task" if operation == "animate" else None}
    checkpoint["request_sha256"] = hashlib.sha256(
        json.dumps(old_binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    write_json(client.out / "postprocess-remote.json", checkpoint)
    created = list(creates(client))
    result = process_source(tmp_path, source_asset, request, client, resume=True)
    assert result["state"] == "success"
    assert creates(client) == created
    assert result["provider"] == "tripo"


def test_old_stored_tripo_request_remains_explicit_on_pipeline_recovery(tmp_path, source_asset, monkeypatch):
    request = request_for(source_asset, "segment")
    old_request = request.model_dump(exclude={"segmentation_context", "segmentation_view", "segmentation_parts", "bone_map"})
    revision, out = Store(tmp_path).new_revision(request.asset_id)
    write_json(out / "processing.json", {"request": old_request, "source_sha256": "unused"})
    seen = []

    def finish(root, recovered, new_revision, folder, *, resume=False):
        seen.append((recovered.provider, recovered.segmentation_context, recovered.bone_map, resume))
        assert new_revision == revision and folder == out
        return {"provider": recovered.provider, "revision": new_revision}

    monkeypatch.setattr(pipeline, "finish_postprocess", finish)
    result = pipeline.resume_postprocess(tmp_path, request.asset_id, revision)
    assert result["provider"] == "tripo"
    assert seen == [("tripo", None, None, True)]
