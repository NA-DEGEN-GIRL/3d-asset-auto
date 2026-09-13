"""Local authoring wrapper contracts using snapshots and mocked export workers."""

import hashlib
import json
import socket
import struct
from pathlib import Path

import pytest
from pydantic import ValidationError

from asset_auto import animation_merge, authoring, pipeline, tripo, tripo_process
from asset_auto.models import (
    AssetSpec,
    BlenderEditRequest,
    EditRequest,
    MergeAnimationsRequest,
    PostprocessRequest,
)
from asset_auto.store import Store, read_json, write_json


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def glb_bytes(label="original"):
    document = json.dumps({"asset": {"version": "2.0"}, "extras": {"fixture": label}}).encode()
    document += b" " * (-len(document) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(document)) + struct.pack("<I4s", len(document), b"JSON") + document


def completed_asset(root, asset_id="test-character", revision="r-original", provider="trellis"):
    folder = root / ".assets" / asset_id / revision
    folder.mkdir(parents=True)
    contents = {"asset.glb": glb_bytes(asset_id), "source.blend": b"original scene: " + asset_id.encode()}
    for name, raw in contents.items():
        (folder / name).write_bytes(raw)
    manifest = {
        "asset_id": asset_id, "revision": revision, "created_at": "2026-09-13T00:00:00Z", "provider": provider,
        "spec": AssetSpec(asset_id=asset_id, provider=provider, image="reference.png").model_dump(),
        "files": {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in contents.items()},
        "inspection": {"triangle_budget": 12000, "dimensions": [1, 1, 2], "parts": [{"name": "body"}]},
    }
    write_json(folder / "manifest.json", manifest)
    return folder, manifest


@pytest.fixture(autouse=True)
def isolated_authoring_environment(monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "test-key-must-not-select-a-paid-provider")

    def denied(*args, **kwargs):
        raise AssertionError("Local authoring tests must not call a paid provider, network or process")

    monkeypatch.setattr(tripo, "api_key", denied)
    monkeypatch.setattr(tripo, "TripoClient", denied)
    monkeypatch.setattr(tripo_process, "TripoClient", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(pipeline, "run_logged", denied)
    monkeypatch.setattr(authoring, "executable", lambda *args: "test-blender")


@pytest.fixture
def source_asset(tmp_path):
    return completed_asset(tmp_path)


def edit_request(root, **changes):
    script = root / "scripts/edit-local.py"
    script.parent.mkdir(exist_ok=True)
    script.write_text("# original trusted authoring script\n", encoding="utf-8")
    return BlenderEditRequest.model_validate({
        "asset_id": "test-character", "revision": "r-original", "script": "scripts/edit-local.py",
        "parameters": {"distance": 0.5},
    } | changes)


def merge_request(root, **changes):
    source = root / "external-animation.glb"
    source.write_bytes(glb_bytes("external clip"))
    return MergeAnimationsRequest.model_validate({
        "asset_id": "test-character", "revision": "r-original",
        "sources": [{"path": "external-animation.glb", "clips": ["Walk"], "rename": {"Walk": "walk"}}],
    } | changes)


class ExportWorker:
    def __init__(self, *, fail_count=0, mutate_delivery=False):
        self.calls = []
        self.fail_count = fail_count
        self.mutate_delivery = mutate_delivery

    def __call__(self, root, request, out):
        self.calls.append(json.loads(json.dumps(request)))
        assert request["target_height"] is None
        assert request["rename_animation"] is False
        assert Path(request["source"]).parent == out
        if request.get("authoring"):
            assert Path(request["source"]).name == "input.blend"
            assert Path(request["script"]) == out / "script.py"
            exported = glb_bytes("authored export")
            write_json(out / "authoring.json", {
                "backend": "mock-local-authoring-worker", "script_sha256": digest((out / "script.py").read_bytes()),
            })
        else:
            assert request["preserve_input_glb"] is True
            assert request["require_animation"] is True
            exported = (out / "generated.glb").read_bytes()
        (out / "asset.glb").write_bytes(glb_bytes("incorrectly reexported") if self.mutate_delivery else exported)
        (out / "source.blend").write_bytes(b"mock exported scene")
        if len(self.calls) <= self.fail_count:
            raise RuntimeError("mock Blender export failed")
        write_json(out / "inspection.json", {
            "passed": True, "errors": [], "warnings": [], "triangle_budget": request["triangle_budget"],
            "parts": [{"name": "body"}], "rigging": {"armatures": []},
        })


class MergeWorker:
    def __init__(self):
        self.calls = []

    def __call__(self, base, sources, target, *, on_conflict):
        self.calls.append((base, sources, target, on_conflict))
        assert Path(base) == target.parent / "input.glb"
        assert all(Path(source["path"]).parent == target.parent for source in sources)
        target.write_bytes(glb_bytes("merged clips"))
        return {"backend": "mock-clip-merger", "output_sha256": digest(target.read_bytes()),
                "sources": [{"clips": [{"source": name, "name": source["rename"].get(name, name)}
                                        for name in source["clips"] or ["Walk"]]} for source in sources],
                "clips": [{"name": "walk"}], "preservation": {"model_copies_added": 0}}


def install_workers(monkeypatch, **options):
    export, merge = ExportWorker(**options), MergeWorker()
    monkeypatch.setattr(pipeline, "blender", export)
    monkeypatch.setattr(animation_merge, "merge", merge)
    return export, merge


@pytest.mark.parametrize("operation", ["blender-edit", "merge-animations"])
def test_authoring_schema_defaults_preserve_explicit_local_scope(tmp_path, operation):
    request = edit_request(tmp_path) if operation == "blender-edit" else merge_request(tmp_path)
    assert "provider" not in request.model_dump()
    assert "max_credits" not in request.model_dump()
    if operation == "blender-edit":
        assert request.preserve_animations is True
        assert request.require_animation is False
    else:
        assert request.on_conflict == "error"


@pytest.mark.parametrize("changes", [
    {"script": ""}, {"revision": "../parent"}, {"provider": "tripo"}, {"max_credits": 100},
    {"triangle_budget": 11}, {"preview_clips": []}, {"parameters": {"value": object()}},
])
def test_blender_authoring_schema_rejects_invalid_inputs(tmp_path, changes):
    with pytest.raises(ValidationError):
        edit_request(tmp_path, **changes)


@pytest.mark.parametrize("sources", [
    [], [{}], [{"asset_id": "test-character"}], [{"revision": "r-original"}],
    [{"path": "clip.glb", "asset_id": "test-character", "revision": "r-original"}],
    [{"path": "clip.glb", "clips": ["Walk", "Walk"]}],
])
def test_merge_schema_requires_unambiguous_sources_and_unique_clip_selections(tmp_path, sources):
    with pytest.raises(ValidationError):
        merge_request(tmp_path, sources=sources)


@pytest.mark.parametrize("filename", ["asset.glb", "source.blend"])
def test_changed_completed_authoring_source_rejected_before_revision_allocation(
    tmp_path, source_asset, monkeypatch, filename
):
    folder, _ = source_asset
    request = edit_request(tmp_path)
    (folder / filename).write_bytes(glb_bytes("changed") if filename.endswith(".glb") else b"changed scene")

    def denied(*args, **kwargs):
        raise AssertionError("Corrupt completed input must be rejected before allocating a partial revision")

    monkeypatch.setattr(Store, "new_revision", denied)
    with pytest.raises(ValueError, match="changed"):
        authoring.edit_in_blender(tmp_path, request)


def test_invalid_external_merge_glb_rejected_before_revision_allocation(tmp_path, source_asset, monkeypatch):
    request = merge_request(tmp_path)
    (tmp_path / "external-animation.glb").write_bytes(b"not a glb")

    def denied(*args, **kwargs):
        raise AssertionError("Invalid external clip must fail before revision allocation")

    monkeypatch.setattr(Store, "new_revision", denied)
    with pytest.raises(ValueError, match="GLB"):
        authoring.merge_animations(tmp_path, request)


@pytest.mark.parametrize("provider", ["trellis", "tripo"])
@pytest.mark.parametrize("operation", ["blender-edit", "merge-animations"])
def test_authoring_is_local_and_preserves_original_asset_for_any_generation_provider(
    tmp_path, monkeypatch, provider, operation
):
    source, parent = completed_asset(tmp_path, provider=provider)
    original = {path.name: path.read_bytes() for path in source.iterdir()}
    export, merge = install_workers(monkeypatch)
    request = edit_request(tmp_path) if operation == "blender-edit" else merge_request(tmp_path)
    start = authoring.edit_in_blender if operation == "blender-edit" else authoring.merge_animations
    recovery = []
    result = start(tmp_path, request, on_revision=recovery.append)
    assert result["parent"] == parent["revision"] and result["revision"] != parent["revision"]
    assert result["provider"] == provider
    assert result["local_processing"]["provider"] == "local"
    assert result["local_processing"]["operation"] == operation
    assert "remote_processing" not in result
    assert result["visual_review"] == "pending"
    assert {path.name: path.read_bytes() for path in source.iterdir()} == original
    assert len(export.calls) == 1
    assert recovery == [{"asset_id": request.asset_id, "revision": result["revision"], "operation": f"resume-{operation}"}]
    out = source.parent / result["revision"]
    record = read_json(out / "authoring-request.json")
    assert record["binding_sha256"] == authoring.binding(record)
    assert export.calls[0]["binding_sha256"] == record["binding_sha256"]
    if operation == "blender-edit":
        assert export.calls[0]["parameters"] == {"distance": 0.5}
        assert export.calls[0]["preserve_animations"] is True
        assert (out / "input.blend").read_bytes() == original["source.blend"]
    else:
        assert len(merge.calls) == 1
        assert merge.calls[0][1][0]["clips"] == ["Walk"]
        assert merge.calls[0][1][0]["rename"] == {"Walk": "walk"}
        assert result["files"]["asset.glb"]["sha256"] == result["local_processing"]["output_sha256"]
        assert (out / "asset.glb").read_bytes() == (out / "generated.glb").read_bytes()


@pytest.mark.parametrize("operation", ["blender-edit", "merge-animations"])
def test_failed_export_resumes_same_revision_using_external_input_snapshots(tmp_path, source_asset, monkeypatch, operation):
    export, merge = install_workers(monkeypatch, fail_count=1)
    request = edit_request(tmp_path) if operation == "blender-edit" else merge_request(tmp_path)
    external = tmp_path / (request.script if operation == "blender-edit" else request.sources[0].path)
    external_before = external.read_bytes()
    start = authoring.edit_in_blender if operation == "blender-edit" else authoring.merge_animations
    recovery = []
    with pytest.raises(RuntimeError, match=f"resume-{operation}"):
        start(tmp_path, request, on_revision=recovery.append)
    revision = recovery[0]["revision"]
    out = tmp_path / ".assets" / request.asset_id / revision
    assert not (out / "manifest.json").exists()
    assert len(Store(tmp_path).list()) == 1
    external.write_bytes(b"external source changed after snapshot")
    snapshot_name = "script.py" if operation == "blender-edit" else "animation-0.glb"
    assert (out / snapshot_name).read_bytes() == external_before
    result = authoring.resume_authoring(tmp_path, request.asset_id, revision, operation=operation)
    assert result["revision"] == revision
    assert len(export.calls) == 2
    assert (out / snapshot_name).read_bytes() == external_before
    assert len(Store(tmp_path).list()) == 2
    assert authoring.resume_authoring(tmp_path, request.asset_id, revision, operation=operation) == result
    assert len(export.calls) == 2
    if operation == "merge-animations":
        assert len(merge.calls) == 2
        assert merge.calls[0][1] == merge.calls[1][1]


def interrupted_edit(tmp_path, source_asset, monkeypatch):
    export, _ = install_workers(monkeypatch, fail_count=1)
    request = edit_request(tmp_path)
    recovery = []
    with pytest.raises(RuntimeError, match="mock Blender export failed"):
        authoring.edit_in_blender(tmp_path, request, on_revision=recovery.append)
    out = tmp_path / ".assets" / request.asset_id / recovery[0]["revision"]
    return request, out, export


@pytest.mark.parametrize("mutation", ["request", "input-hash", "binding", "snapshot", "snapshot-path"])
def test_authoring_resume_rejects_changed_binding_or_snapshot_before_worker(tmp_path, source_asset, monkeypatch, mutation):
    request, out, export = interrupted_edit(tmp_path, source_asset, monkeypatch)
    record = read_json(out / "authoring-request.json")
    if mutation == "snapshot":
        (out / "script.py").write_text("# changed snapshot", encoding="utf-8")
    else:
        if mutation == "request":
            record["request"]["parameters"] = {"distance": 999}
        elif mutation == "input-hash":
            record["inputs"][0]["sha256"] = "0" * 64
        elif mutation == "binding":
            record["binding_sha256"] = "0" * 64
        else:
            record["inputs"][0]["file"] = "../outside.glb"
            record["binding_sha256"] = authoring.binding(record)
        write_json(out / "authoring-request.json", record)
    with pytest.raises(ValueError, match="changed|Invalid identifier"):
        authoring.resume_authoring(tmp_path, request.asset_id, out.name)
    assert len(export.calls) == 1
    assert not (out / "manifest.json").exists()


@pytest.mark.parametrize("filename", ["asset.glb", "source.blend"])
def test_authoring_resume_rejects_completed_origin_mutation(tmp_path, source_asset, monkeypatch, filename):
    request, out, export = interrupted_edit(tmp_path, source_asset, monkeypatch)
    original = source_asset[0] / filename
    original.write_bytes(glb_bytes("source changed") if filename.endswith(".glb") else b"source scene changed")
    with pytest.raises(ValueError, match="changed"):
        authoring.resume_authoring(tmp_path, request.asset_id, out.name)
    assert len(export.calls) == 1
    assert not (out / "manifest.json").exists()


def test_authoring_resume_rejects_wrong_operation(tmp_path, source_asset, monkeypatch):
    request, out, export = interrupted_edit(tmp_path, source_asset, monkeypatch)
    with pytest.raises(ValueError, match="does not match this authoring operation"):
        authoring.resume_authoring(tmp_path, request.asset_id, out.name, operation="merge-animations")
    assert len(export.calls) == 1


def test_merge_resume_preserves_exact_completed_clip_origin(tmp_path, source_asset, monkeypatch):
    clip_source, _ = completed_asset(tmp_path, "walk-source", "r-walk")
    request = merge_request(tmp_path, sources=[{"asset_id": "walk-source", "revision": "r-walk"}])
    export, _ = install_workers(monkeypatch, fail_count=1)
    recovery = []
    with pytest.raises(RuntimeError, match="mock Blender export failed"):
        authoring.merge_animations(tmp_path, request, on_revision=recovery.append)
    (clip_source / "asset.glb").write_bytes(glb_bytes("changed completed animation"))
    with pytest.raises(ValueError, match="changed"):
        authoring.resume_authoring(tmp_path, request.asset_id, recovery[0]["revision"])
    assert len(export.calls) == 1


def test_merge_cannot_publish_reexported_delivery_with_a_different_hash(tmp_path, source_asset, monkeypatch):
    install_workers(monkeypatch, mutate_delivery=True)
    request = merge_request(tmp_path)
    recovery = []
    with pytest.raises(RuntimeError, match="Final delivery GLB differs"):
        authoring.merge_animations(tmp_path, request, on_revision=recovery.append)
    out = tmp_path / ".assets" / request.asset_id / recovery[0]["revision"]
    assert not (out / "manifest.json").exists()
    assert len(Store(tmp_path).list()) == 1


def test_script_snapshot_mutation_during_worker_is_detected_before_publication(tmp_path, source_asset, monkeypatch):
    worker = ExportWorker()

    def mutating_worker(root, request, out):
        worker(root, request, out)
        (out / "script.py").write_text("# accidental script snapshot edit", encoding="utf-8")

    monkeypatch.setattr(pipeline, "blender", mutating_worker)
    recovery = []
    with pytest.raises(RuntimeError, match="Saved input snapshot changed"):
        authoring.edit_in_blender(tmp_path, edit_request(tmp_path), on_revision=recovery.append)
    out = tmp_path / ".assets/test-character" / recovery[0]["revision"]
    assert not (out / "manifest.json").exists()


@pytest.mark.parametrize("kind", ["animated", "character"])
def test_animated_and_character_import_use_preserving_worker_with_distinct_requirements(tmp_path, monkeypatch, kind):
    source = tmp_path / "existing.glb"
    source.write_bytes(glb_bytes("existing motion"))
    calls = []

    def worker(root, request, out):
        calls.append(request)
        assert request["character"] is True
        assert request["require_rig"] is (kind == "character")
        assert request["require_animation"] is (kind == "animated")
        assert Path(request["source"]) == out / "input.glb"
        (out / "asset.glb").write_bytes(source.read_bytes())
        (out / "source.blend").write_bytes(b"mock-preserved-animation-scene")
        write_json(out / "inspection.json", {
            "passed": True, "errors": [], "triangle_budget": 12000,
            "rigging": {"armatures": [{"name": "Rig"}] if kind == "character" else []},
            "animations": {"count": 1 if kind == "animated" else 0},
        })

    monkeypatch.setattr(pipeline, "blender", worker)
    result = pipeline.generate(tmp_path, AssetSpec(
        asset_id="imported-model", provider="import", source=str(source), asset_kind=kind,
    ))
    assert len(calls) == 1
    assert result["asset_type"] == kind
    assert source.read_bytes() == glb_bytes("existing motion")


def test_static_edit_rejects_object_animation_without_an_armature(tmp_path, source_asset, monkeypatch):
    source, manifest = source_asset
    manifest["inspection"]["animations"] = {"count": 1}
    write_json(source / "manifest.json", manifest)

    def denied(*args, **kwargs):
        raise AssertionError("Animated objects must not enter the destructive static editing worker")

    monkeypatch.setattr(pipeline, "blender", denied)
    request = EditRequest(asset_id="test-character", revision="r-original", changes=[{"part": "body", "scale": [2, 2, 2]}])
    with pytest.raises(ValueError, match="rigged or animated asset.*blender-edit"):
        pipeline.edit_asset(tmp_path, request)
    assert len(Store(tmp_path).list()) == 1


def test_animated_asset_kind_does_not_select_a_generation_provider():
    with pytest.raises(ValidationError, match="requires provider: import"):
        AssetSpec(asset_id="generated-model", image="reference.png", asset_kind="animated")


@pytest.mark.parametrize("operation", ["rig", "segment"])
@pytest.mark.parametrize("provider", ["local", "tripo"])
def test_static_processing_rejects_animated_unrigged_source_before_tools_or_revision(
    tmp_path, source_asset, monkeypatch, operation, provider
):
    source, manifest = source_asset
    manifest["inspection"].update(animations={"count": 2}, rigging={"armatures": []})
    write_json(source / "manifest.json", manifest)
    original = {path.name: path.read_bytes() for path in source.iterdir()}
    payload = {"asset_id": "test-character", "revision": "r-original", "operation": operation, "provider": provider}
    if operation == "segment" and provider == "local":
        payload.update(segmentation_context="unused-context.json",
                       segmentation_parts=[{"name": "body", "positive_points": [[0, 0]]}])
    request = PostprocessRequest.model_validate(payload)

    def denied(*args, **kwargs):
        raise AssertionError("Animated source must be rejected before tool discovery or allocating a revision")

    monkeypatch.setattr(pipeline, "executable", denied)
    monkeypatch.setattr(Store, "new_revision", denied)
    for invoke in (pipeline.postprocess_plan, pipeline.postprocess):
        with pytest.raises(ValueError, match="require a static source"):
            invoke(tmp_path, request)
    assert {path.name: path.read_bytes() for path in source.iterdir()} == original


def test_prepare_segmentation_rejects_animated_unrigged_source_before_context_render(tmp_path, source_asset, monkeypatch):
    from asset_auto import local_parts

    source, manifest = source_asset
    manifest["inspection"].update(animations={"count": 2}, rigging={"armatures": []})
    write_json(source / "manifest.json", manifest)

    def denied(*args, **kwargs):
        raise AssertionError("Segmentation preparation must not render or load tools for animated input")

    monkeypatch.setattr(pipeline, "executable", denied)
    monkeypatch.setattr(local_parts, "prepare", denied)
    with pytest.raises(ValueError, match="preserved static revision"):
        pipeline.prepare_segmentation(tmp_path, "test-character", "r-original")
    assert not (tmp_path / ".work").exists()
