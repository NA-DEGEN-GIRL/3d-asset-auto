import json
import os
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from asset_auto.jobs import status
from asset_auto.models import AssetSpec, EditRequest
from asset_auto.pipeline import review, validate_glb
from asset_auto.store import Store, child, read_json, write_json
from asset_auto.web import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_recipe_and_partial_edit_validation():
    value = json.loads((ROOT / "examples/sword.json").read_text())
    assert AssetSpec.model_validate(value).recipe.parts[0].name == "blade"
    value["recipe"]["parts"][1]["name"] = "blade"
    with pytest.raises(ValidationError):
        AssetSpec.model_validate(value)
    with pytest.raises(ValidationError):
        EditRequest.model_validate({"asset_id": "sword", "revision": "r1", "changes": [{"part": "grip"}]})


@pytest.mark.parametrize("value", ["..", "../outside", "a/b", "a\\b", "C:\\outside", "/tmp"])
def test_store_path_containment(tmp_path, value):
    with pytest.raises(ValueError):
        child(tmp_path, value)


def test_glb_rejects_truncated_payload(tmp_path):
    path = tmp_path / "x.glb"
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 100))
    with pytest.raises(ValueError):
        validate_glb(path)


def test_failed_revision_does_not_replace_completed_one(tmp_path):
    store = Store(tmp_path)
    first, folder = store.new_revision("sword")
    write_json(folder / "manifest.json", {"asset_id": "sword", "revision": first, "created_at": "2026"})
    second, _ = store.new_revision("sword")
    assert [r["revision"] for r in store.list()] == [first]
    with pytest.raises(FileNotFoundError):
        store.revision("sword", second)


def test_review_is_separate_from_immutable_manifest(tmp_path):
    revision, folder = Store(tmp_path).new_revision("sword")
    write_json(folder / "manifest.json", {"state": "numeric_checks_passed"})
    before = (folder / "manifest.json").read_bytes()
    review(tmp_path, "sword", revision, False, "Blade tip is disconnected")
    assert (folder / "manifest.json").read_bytes() == before
    assert not read_json(folder / "review.json")["passed"]


def test_viewer_does_not_expose_logs_or_allow_cross_origin_writes(tmp_path):
    revision, folder = Store(tmp_path).new_revision("sword")
    write_json(folder / "manifest.json", {"state": "numeric_checks_passed"})
    (folder / "private.log").write_text("private")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/assets/sword/{revision}/private.log").status_code == 404
        assert client.get("/api/assets", headers={"Host": "untrusted.example"}).status_code == 400
        response = client.post(
            f"/api/assets/sword/{revision}/browser-report",
            headers={"Origin": "https://untrusted.example"},
            json={"meshes": 1, "triangles": 12, "draw_calls": 1, "three_version": "183"},
        )
        assert response.status_code == 403


def test_exited_or_reused_worker_is_reported_as_interrupted(tmp_path):
    path = tmp_path / ".assets/jobs/testjob/job.json"
    write_json(path, {"state": "running", "pid": os.getpid(), "process_created_at": 0.1})
    assert status(tmp_path, "testjob")["state"] == "interrupted"
