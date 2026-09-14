"""Detect unintended clip/timebase/model changes without running an exporter."""

import asyncio
import copy
import json
import math
import struct
import sys

import pytest
from test_animation_merge import append_accessor, fixture, write_glb

from asset_auto import animation_compare, animation_merge, cli
from asset_auto.models import AnimationComparisonRequest


def pair(tmp_path, *, morph=False):
    document, binary = fixture(morph=morph)
    before = write_glb(tmp_path / "before.glb", document, binary)
    after = tmp_path / "after.glb"
    return before, after, document, binary


def test_explicit_clip_replacement_keeps_other_clip_data_and_model(tmp_path):
    before, after, document, binary = pair(tmp_path)
    document["animations"].append(copy.deepcopy(document["animations"][0]))
    document["animations"][-1]["name"] = "wave"
    write_glb(before, document, binary)
    donor_doc, donor_bin = fixture(clip="wave", layout="interleaved")
    donor_doc["animations"][0]["samplers"][0]["interpolation"] = "STEP"
    donor = write_glb(tmp_path / "donor.glb", donor_doc, donor_bin)
    animation_merge.merge(before, [{"path": donor}], after, on_conflict="replace")
    original_files = {p: p.read_bytes() for p in (before, after)}
    result = animation_compare.compare(before, after, changed_clips=["wave"])
    assert result["preservation_status"] == "preserved"
    assert result["protected_clips"] == ["idle"]
    assert result["clips"]["wave"]["status"] == "changed"
    assert result["clips"]["idle"]["status"] == "identical"
    assert result["model_context"]["status"] == "identical"
    assert result["visual_review"] == "untested"
    assert all(p.read_bytes() == raw for p, raw in original_files.items())


@pytest.mark.parametrize("layout", ["packed", "sparse", "interleaved"])
def test_buffer_layout_is_not_a_motion_change(tmp_path, layout):
    before, after, _, _ = pair(tmp_path)
    doc, binary = fixture(layout=layout)
    write_glb(after, doc, binary)
    result = animation_compare.compare(before, after)
    assert result["preservation_status"] == "preserved"
    assert result["clips"]["idle"]["before"] == result["clips"]["idle"]["after"]


@pytest.mark.parametrize("change", ["retime", "resample", "pose", "interpolation"])
def test_same_clip_name_does_not_hide_changes(tmp_path, change):
    before, after, doc, binary = pair(tmp_path)
    sampler = doc["animations"][0]["samplers"][0]
    if change in {"retime", "resample"}:
        times = [0, 2] if change == "retime" else [0, 0.5, 1]
        sampler["input"] = append_accessor(doc, binary, times, "SCALAR")
        doc["accessors"][sampler["input"]].update(min=[0], max=[times[-1]])
        if change == "resample":
            sampler["output"] = append_accessor(doc, binary, [
                0, 0, 0, 1, 0, 0, math.sin(math.pi / 8), math.cos(math.pi / 8),
                0, 0, math.sqrt(0.5), math.sqrt(0.5),
            ], "VEC4")
    elif change == "pose":
        sampler["output"] = append_accessor(doc, binary, [0, 0, 0, 1] * 2, "VEC4")
    else:
        sampler["interpolation"] = "STEP"
    write_glb(after, doc, binary)
    result = animation_compare.compare(before, after)
    assert result["preservation_status"] == "changed"
    assert result["unexpected_changed_clips"] == ["idle"]
    clip = result["clips"]["idle"]
    assert clip["status"] == "changed"
    if change == "retime":
        assert clip["before"]["end_seconds"] == 1
        assert clip["after"]["end_seconds"] == 2
    if change == "resample":
        assert clip["before"]["key_count"] == 2
        assert clip["after"]["key_count"] == 3


@pytest.mark.parametrize("change,section", [
    ("rest", "nodes"), ("weight", "meshes"), ("bind", "skins"), ("material", "materials"),
])
def test_identical_curves_do_not_hide_changed_deformation_context(tmp_path, change, section):
    before, after, doc, binary = pair(tmp_path)
    if change == "rest":
        doc["nodes"][1]["translation"][1] = 2
    elif change == "weight":
        accessor = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["WEIGHTS_0"]]
        struct.pack_into("<f", binary, doc["bufferViews"][accessor["bufferView"]]["byteOffset"], 0.5)
    elif change == "bind":
        doc["skins"][0].pop("inverseBindMatrices")
    else:
        doc["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"][0] = 0.9
    write_glb(after, doc, binary)
    result = animation_compare.compare(before, after)
    assert result["clips"]["idle"]["status"] == "identical"
    assert result["model_context"]["changed_sections"] == [section]
    assert result["preservation_status"] == "changed"


def test_morph_values_and_target_order_are_checked(tmp_path):
    before, after, doc, binary = pair(tmp_path, morph=True)
    doc["meshes"][0]["extras"]["targetNames"].reverse()
    write_glb(after, doc, binary)
    result = animation_compare.compare(before, after)
    assert result["clips"]["idle"]["channel_differences"][0]["changed"] == ["morph_targets"]
    assert result["preservation_status"] == "changed"


def test_cubic_tangents_are_part_of_the_motion(tmp_path):
    before, after, doc, binary = pair(tmp_path)
    sampler = doc["animations"][0]["samplers"][0]
    values = [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0] * 2
    sampler["interpolation"] = "CUBICSPLINE"
    sampler["output"] = append_accessor(doc, binary, values, "VEC4")
    write_glb(before, doc, binary)
    values[8] = 0.5
    sampler["output"] = append_accessor(doc, binary, values, "VEC4")
    write_glb(after, doc, binary)
    result = animation_compare.compare(before, after)
    assert result["clips"]["idle"]["channel_differences"][0]["changed"] == ["values"]


def test_added_and_removed_clips_are_not_silently_ignored(tmp_path):
    before, after, doc, binary = pair(tmp_path)
    doc["animations"][0]["name"] = "wave"
    write_glb(after, doc, binary)
    result = animation_compare.compare(before, after)
    assert result["unexpected_changed_clips"] == ["idle", "wave"]
    assert result["clips"]["idle"]["status"] == "removed"
    assert result["clips"]["wave"]["status"] == "added"
    with pytest.raises(ValueError, match="do not exist"):
        animation_compare.compare(before, after, changed_clips=["typo"])
    result = animation_compare.compare(before, after, changed_clips=["idle", "wave"])
    assert result["preservation_status"] == "no_protected_clips"


def test_ambiguous_targets_and_unsupported_context_cannot_pass(tmp_path):
    before, after, doc, binary = pair(tmp_path)
    doc["materials"][0]["extensions"] = {"KHR_materials_unlit": {}}
    write_glb(after, doc, binary)
    result = animation_compare.compare(before, after)
    assert result["preservation_status"] == "unverified"
    doc["nodes"].append({"name": "Bone"})
    doc["nodes"][0]["children"].append(3)
    write_glb(after, doc, binary)
    with pytest.raises(ValueError, match="unambiguous"):
        animation_compare.compare(before, after)


def test_cli_and_mcp_share_read_only_comparison(tmp_path, monkeypatch, capsys):
    before, after, doc, binary = pair(tmp_path)
    write_glb(after, doc, binary)
    request = {"before": before.name, "after": after.name, "changed_clips": []}
    spec = tmp_path / "compare.json"
    spec.write_text(json.dumps(request), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "assetctl", "--root", str(tmp_path), "compare-animations", str(spec),
    ])
    assert cli.main() == 0
    expected = json.loads(capsys.readouterr().out)
    assert expected["preservation_status"] == "preserved"
    pytest.importorskip("mcp")
    from asset_auto.mcp_server import build_server

    server = build_server(tmp_path)

    async def invoke():
        content = await server.call_tool("compare_asset_animations", {"request": request})
        assert json.loads(content[0].text) == expected

    asyncio.run(invoke())
    assert not (tmp_path / ".assets").exists()


@pytest.mark.parametrize("names", [["idle", "idle"], [" "]])
def test_declared_changes_cannot_be_ambiguous(names):
    with pytest.raises(ValueError):
        AnimationComparisonRequest(before="before.glb", after="after.glb", changed_clips=names)
