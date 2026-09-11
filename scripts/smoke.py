"""Real Blender/Godot integration test, isolated under .work; no GPU required."""

import hashlib
import json
import uuid
from pathlib import Path

from asset_auto.models import AssetSpec, EditRequest
from asset_auto.pipeline import edit_asset, generate, validate_godot
from asset_auto.settings import executable
from asset_auto.store import Store, write_json


def main():
    repository = Path(__file__).resolve().parents[1]
    sandbox = repository / ".work" / f"smoke-{uuid.uuid4().hex[:8]}"
    sandbox.mkdir(parents=True)
    write_json(
        sandbox / "asset-system.local.json",
        {tool: executable(repository, tool) for tool in ("blender", "godot")},
    )
    spec = AssetSpec.model_validate_json((repository / "examples/sword.json").read_text())
    first = generate(sandbox, spec)
    store = Store(sandbox)
    source = store.revision(spec.asset_id, first["revision"]) / "source.blend"
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert first["inspection"]["passed"]
    second = edit_asset(
        sandbox,
        EditRequest(
            asset_id=spec.asset_id,
            revision=first["revision"],
            changes=[{"part": "grip", "color": [0.2, 0.01, 0.03, 1]}],
            description="Change grip material only",
        ),
    )
    assert second["parent"] == first["revision"]
    for before, after in zip(first["inspection"]["parts"], second["inspection"]["parts"], strict=True):
        assert before["name"] == after["name"]
        assert before["dimensions"] == after["dimensions"]
        assert before["triangles"] == after["triangles"]
    third = edit_asset(
        sandbox,
        EditRequest(
            asset_id=spec.asset_id,
            revision=second["revision"],
            changes=[{"part": "grip", "scale": [1, 1, 1.2]}],
            description="Lengthen grip by 20 percent",
        ),
    )
    parts = {p["name"]: p for p in third["inspection"]["parts"]}
    previous = {p["name"]: p for p in second["inspection"]["parts"]}
    assert abs(parts["grip"]["dimensions"][2] / previous["grip"]["dimensions"][2] - 1.2) < 1e-5
    assert parts["blade"]["dimensions"] == previous["blade"]["dimensions"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
    try:
        edit_asset(
            sandbox,
            EditRequest(
                asset_id=spec.asset_id,
                revision=third["revision"],
                changes=[{"part": "absent_part", "scale": [1, 1, 2]}],
            ),
        )
        raise AssertionError("Unknown part was accepted")
    except RuntimeError as error:
        assert "Unknown part" in str(error)
    assert len(store.list()) == 3
    imported = generate(
        sandbox,
        AssetSpec(
            asset_id="roundtrip",
            provider="import",
            source=str(store.revision(spec.asset_id, third["revision"]) / "asset.glb"),
            target_height=0.5,
            triangle_budget=1200,
        ),
    )
    assert imported["inspection"]["passed"]
    assert abs(imported["inspection"]["dimensions"][2] - 0.5) < 1e-5
    assert abs(imported["inspection"]["bounds"]["min"][2]) < 1e-5
    godot = validate_godot(sandbox, spec.asset_id, third["revision"])
    assert godot["passed"] and godot["meshes"] == len(third["inspection"]["parts"])
    report = {
        "passed": True,
        "checks": [
            "procedural generation",
            "material-only edit preserves geometry",
            "second edit scales only selected part",
            "parent source unchanged",
            "failed edit isolated",
            "GLB reimport and decimation",
            "exact final height and bottom pivot",
            "real Godot import",
        ],
        "blender": first["inspection"]["blender_version"],
        "godot": godot["godot_version"],
        "sandbox": str(sandbox),
    }
    write_json(sandbox / "result.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
