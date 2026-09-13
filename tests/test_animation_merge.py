"""Binary merge contracts: real accessor data, rig compatibility and clip preservation."""

import copy
import hashlib
import json
import math
import struct

import pytest

from asset_auto import animation_merge

IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
INVERSE_BONE = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -1, 0, 1]


def append_view(document, binary, payload, **extra):
    binary.extend(b"\x00" * (-len(binary) % 4))
    view = len(document["bufferViews"])
    document["bufferViews"].append({
        "buffer": 0, "byteOffset": len(binary), "byteLength": len(payload), **extra,
    })
    binary.extend(payload)
    return view


def append_accessor(document, binary, values, kind, component_type=5126):
    widths = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    codes = {5126: "f", 5123: "H"}
    view = append_view(document, binary, struct.pack(f"<{len(values)}{codes[component_type]}", *values))
    result = len(document["accessors"])
    document["accessors"].append({
        "bufferView": view, "componentType": component_type, "count": len(values) // widths[kind],
        "type": kind,
    })
    return result


def fixture(*, clip="idle", node_order=("Root", "Bone", "Mesh"), layout="packed", morph=False):
    document = {
        "asset": {"version": "2.0", "generator": "animation merge regression fixture"},
        "scene": 0, "scenes": [{"nodes": [node_order.index("Root")]}],
        "nodes": [], "meshes": [], "skins": [], "animations": [],
        "buffers": [{"byteLength": 0}], "bufferViews": [], "accessors": [],
        "materials": [{"name": "OriginalPaint", "pbrMetallicRoughness": {"baseColorFactor": [0.2, 0.6, 0.8, 1]}}],
        "extras": {"must_survive": "base metadata"},
    }
    binary = bytearray()
    for name in node_order:
        node = {"name": name}
        if name == "Root":
            node["children"] = [node_order.index("Bone"), node_order.index("Mesh")]
        elif name == "Bone":
            node["translation"] = [0, 1, 0]
        else:
            node.update(mesh=0, skin=0)
        document["nodes"].append(node)
    positions = append_accessor(document, binary, [0, 0, 0, 1, 0, 0, 0, 1, 0], "VEC3")
    document["accessors"][positions].update(min=[0, 0, 0], max=[1, 1, 0])
    joints = append_accessor(document, binary, [0] * 12, "VEC4", 5123)
    weights = append_accessor(document, binary, [1, 0, 0, 0] * 3, "VEC4")
    indices = append_accessor(document, binary, [0, 1, 2], "SCALAR", 5123)
    inverse_bind = append_accessor(document, binary, INVERSE_BONE, "MAT4")
    primitive = {"attributes": {"POSITION": positions, "JOINTS_0": joints, "WEIGHTS_0": weights},
                 "indices": indices, "material": 0}
    mesh = {"name": "OriginalGeometry", "primitives": [primitive]}
    if morph:
        zero = append_accessor(document, binary, [0] * 9, "VEC3")
        primitive["targets"] = [{"POSITION": zero}, {"POSITION": zero}]
        mesh.update(weights=[0, 0], extras={"targetNames": ["Smile", "Blink"]})
    document["meshes"].append(mesh)
    document["skins"].append({"name": "Rig", "joints": [node_order.index("Bone")],
                              "skeleton": node_order.index("Root"), "inverseBindMatrices": inverse_bind})
    times = append_accessor(document, binary, [0, 1], "SCALAR")
    document["accessors"][times].update(min=[0], max=[1])
    rotations = [0, 0, 0, 1, 0, 0, math.sqrt(0.5), math.sqrt(0.5)]
    if morph:
        output = append_accessor(document, binary, [0, 0.25, 1, 0.75], "SCALAR")
    elif layout == "interleaved":
        payload = struct.pack("<12f", 91, *rotations[:4], 92, 93, *rotations[4:], 94)
        view = append_view(document, binary, payload, byteStride=24)
        output = len(document["accessors"])
        document["accessors"].append({"bufferView": view, "byteOffset": 4,
                                      "componentType": 5126, "count": 2, "type": "VEC4"})
    elif layout == "sparse":
        index_view = append_view(document, binary, b"\x00\x01")
        value_view = append_view(document, binary, struct.pack("<8f", *rotations))
        output = len(document["accessors"])
        document["accessors"].append({
            "componentType": 5126, "count": 2, "type": "VEC4",
            "sparse": {"count": 2, "indices": {"bufferView": index_view, "componentType": 5121},
                       "values": {"bufferView": value_view}},
        })
    else:
        output = append_accessor(document, binary, rotations, "VEC4")
    if clip is not None:
        document["animations"].append({
            "name": clip, "samplers": [{"input": times, "output": output, "interpolation": "LINEAR"}],
            "channels": [{"sampler": 0, "target": {
                "node": node_order.index("Mesh" if morph else "Bone"),
                "path": "weights" if morph else "rotation",
            }}], "extras": {"origin": clip},
        })
    return document, binary


def write_glb(path, document, binary):
    document = copy.deepcopy(document)
    document["buffers"][0]["byteLength"] = len(binary)
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    payload = bytes(binary) + b"\x00" * (-len(binary) % 4)
    chunks = struct.pack("<I4s", len(encoded), b"JSON") + encoded
    chunks += struct.pack("<I4s", len(payload), b"BIN\x00") + payload
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks)
    return path


def test_text_motion_keeps_original_samplers_instead_of_rebaked_parent_clips(tmp_path):
    from asset_auto.text_motion import merge_generated_clip

    base_doc, base_binary = fixture(clip="idle")
    base_path = write_glb(tmp_path / "input.glb", base_doc, base_binary)
    source_doc, source_binary = fixture(clip="wave")
    rebaked = copy.deepcopy(source_doc["animations"][0])
    rebaked["name"] = "idle"
    rebaked["samplers"][0]["input"] = append_accessor(source_doc, source_binary, [0, .5, 1], "SCALAR")
    rebaked["samplers"][0]["output"] = append_accessor(source_doc, source_binary, [0, 0, 0, 1] * 3, "VEC4")
    source_doc["animations"].append(rebaked)
    draft_path = write_glb(tmp_path / "asset.glb", source_doc, source_binary)
    base_bytes, draft_bytes = base_path.read_bytes(), draft_path.read_bytes()

    result = merge_generated_clip(tmp_path, "wave")

    merged_doc, merged_binary = read_glb(tmp_path / "generated.glb")
    original_doc, original_binary = read_glb(base_path)
    assert [clip["name"] for clip in merged_doc["animations"]] == ["idle", "wave"]
    assert merged_doc["animations"][0] == original_doc["animations"][0]
    assert merged_doc["accessors"][:len(original_doc["accessors"])] == original_doc["accessors"]
    assert merged_binary[:len(original_binary)] == original_binary
    assert base_path.read_bytes() == base_bytes
    assert (tmp_path / "retargeted.glb").read_bytes() == draft_bytes
    assert result["preservation"]["base_binary_prefix_unchanged"]


def read_glb(path):
    raw = path.read_bytes()
    assert struct.unpack_from("<4sII", raw) == (b"glTF", 2, len(raw))
    size, kind = struct.unpack_from("<I4s", raw, 12)
    assert kind == b"JSON"
    document = json.loads(raw[20:20 + size])
    offset = 20 + size
    binary_size, kind = struct.unpack_from("<I4s", raw, offset)
    assert kind == b"BIN\x00"
    return document, raw[offset + 8:offset + 8 + binary_size]


def accessor_values(document, binary, index):
    """Independent reader supports both packed output and preserved sparse/stride encodings."""
    accessor = document["accessors"][index]
    width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[accessor["type"]]
    assert accessor["componentType"] == 5126
    result = [[0.0] * width for _ in range(accessor["count"])]
    if "bufferView" in accessor:
        view = document["bufferViews"][accessor["bufferView"]]
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        stride = view.get("byteStride", width * 4)
        result = [list(struct.unpack_from(f"<{width}f", binary, offset + i * stride))
                  for i in range(accessor["count"])]
    if "sparse" in accessor:
        sparse = accessor["sparse"]
        indices, values = sparse["indices"], sparse["values"]
        index_view = document["bufferViews"][indices["bufferView"]]
        value_view = document["bufferViews"][values["bufferView"]]
        index_offset = index_view.get("byteOffset", 0) + indices.get("byteOffset", 0)
        value_offset = value_view.get("byteOffset", 0) + values.get("byteOffset", 0)
        code, size = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}[indices["componentType"]]
        for i in range(sparse["count"]):
            target = struct.unpack_from(f"<{code}", binary, index_offset + i * size)[0]
            result[target] = list(struct.unpack_from(f"<{width}f", binary, value_offset + i * width * 4))
    return [value for row in result for value in row]


def paths(tmp_path, *, donor_options=None, base_options=None):
    base_doc, base_bin = fixture(**(base_options or {}))
    donor_doc, donor_bin = fixture(clip="walk", **(donor_options or {}))
    base = write_glb(tmp_path / "base.glb", base_doc, base_bin)
    donor = write_glb(tmp_path / "donor.glb", donor_doc, donor_bin)
    return base, donor, tmp_path / "merged.glb", donor_doc, donor_bin


def merge(base, donor, output, **kwargs):
    return animation_merge.merge(base, [{"path": str(donor), "clips": None, "rename": {}}], output, **kwargs)


@pytest.mark.parametrize("bounds", [{"min": [0], "max": [2]}, {"min": [-1], "max": [1]}, {}])
def test_animation_time_bounds_must_match_real_payload(tmp_path, bounds):
    base, donor, output, donor_doc, donor_bin = paths(tmp_path)
    accessor = donor_doc["accessors"][donor_doc["animations"][0]["samplers"][0]["input"]]
    accessor.pop("min")
    accessor.pop("max")
    accessor.update(bounds)
    write_glb(donor, donor_doc, donor_bin)
    with pytest.raises(ValueError):
        merge(base, donor, output)
    assert not output.exists()


def test_merge_preserves_base_binary_geometry_skin_and_clips_with_reordered_donor(tmp_path):
    base, donor, output, donor_doc, donor_bin = paths(
        tmp_path, donor_options={"node_order": ("Bone", "Root", "Mesh")},
    )
    # Accessor IDs have no semantic relationship across the two files.
    old = donor_doc["accessors"]
    donor_doc["accessors"] = list(reversed(old))
    remap = lambda index: len(old) - index - 1
    primitive = donor_doc["meshes"][0]["primitives"][0]
    primitive["attributes"] = {key: remap(value) for key, value in primitive["attributes"].items()}
    primitive["indices"] = remap(primitive["indices"])
    donor_doc["skins"][0]["inverseBindMatrices"] = remap(donor_doc["skins"][0]["inverseBindMatrices"])
    for sampler in donor_doc["animations"][0]["samplers"]:
        sampler["input"], sampler["output"] = remap(sampler["input"]), remap(sampler["output"])
    write_glb(donor, donor_doc, donor_bin)
    before_base, before_donor = base.read_bytes(), donor.read_bytes()
    base_doc, base_bin = read_glb(base)

    report = merge(base, donor, output)
    merged, binary = read_glb(output)

    assert base.read_bytes() == before_base
    assert donor.read_bytes() == before_donor
    assert binary[:len(base_bin)] == base_bin
    # One two-key sampler adds only 8 bytes of times and 32 bytes of rotations.
    assert len(binary) <= len(base_bin) + 40
    assert len(merged["accessors"]) <= len(base_doc["accessors"]) + 2
    for field in ("meshes", "skins", "materials", "nodes", "scenes", "extras"):
        assert merged[field] == base_doc[field]
    assert merged["accessors"][:len(base_doc["accessors"])] == base_doc["accessors"]
    assert merged["animations"][0] == base_doc["animations"][0]
    assert [clip["name"] for clip in merged["animations"]] == ["idle", "walk"]
    added = merged["animations"][1]
    assert added["channels"][0]["target"] == {"node": 1, "path": "rotation"}
    assert accessor_values(merged, binary, added["samplers"][0]["input"]) == [0, 1]
    assert accessor_values(merged, binary, added["samplers"][0]["output"]) == pytest.approx(
        [0, 0, 0, 1, 0, 0, math.sqrt(0.5), math.sqrt(0.5)],
    )
    assert report["base"]["sha256"] == hashlib.sha256(before_base).hexdigest()
    assert report["sources"][0]["sha256"] == hashlib.sha256(before_donor).hexdigest()
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert [clip["name"] for clip in report["clips"]] == ["idle", "walk"]
    assert all(clip["duration_seconds"] == 1 for clip in report["clips"])


@pytest.mark.parametrize("layout", ["interleaved", "sparse"])
def test_imports_actual_interleaved_and_sparse_accessor_values(tmp_path, layout):
    base, donor, output, _, _ = paths(tmp_path, donor_options={"layout": layout})
    merge(base, donor, output)
    document, binary = read_glb(output)
    sampler = document["animations"][1]["samplers"][0]
    assert accessor_values(document, binary, sampler["output"]) == pytest.approx(
        [0, 0, 0, 1, 0, 0, math.sqrt(0.5), math.sqrt(0.5)],
    )


def test_clip_filter_rename_and_explicit_replacement(tmp_path):
    base, donor, output, document, binary = paths(tmp_path)
    run = copy.deepcopy(document["animations"][0])
    run["name"] = "run"
    document["animations"].append(run)
    write_glb(donor, document, binary)
    sources = [{"path": str(donor), "clips": ["run"], "rename": {"run": "idle"}}]
    with pytest.raises(ValueError):
        animation_merge.merge(base, sources, output)
    report = animation_merge.merge(base, sources, output, on_conflict="replace")
    merged, _ = read_glb(output)
    assert [clip["name"] for clip in merged["animations"]] == ["idle"]
    assert merged["animations"][0]["extras"]["origin"] == "walk"
    assert report["sources"][0]["clips"] == [{"source": "run", "name": "idle"}]


def test_duplicate_names_across_donors_rejected(tmp_path):
    base, donor, output, _, _ = paths(tmp_path)
    sources = [{"path": str(donor), "clips": None, "rename": {}}] * 2
    with pytest.raises(ValueError):
        animation_merge.merge(base, sources, output)


@pytest.mark.parametrize("selection", [["missing"], ["walk", "walk"]])
def test_unknown_or_repeated_clip_selection_rejected(tmp_path, selection):
    base, donor, output, _, _ = paths(tmp_path)
    with pytest.raises(ValueError):
        animation_merge.merge(base, [{"path": str(donor), "clips": selection, "rename": {}}], output)


def test_equivalent_rest_matrix_and_trs_are_compatible(tmp_path):
    base, donor, output, document, binary = paths(tmp_path)
    # An animated node must use TRS, but its unanimated ancestors may use matrices.
    base_document, base_binary = read_glb(base)
    base_document["nodes"][0]["translation"] = [0, 1, 0]
    write_glb(base, base_document, base_binary)
    document["nodes"][0]["matrix"] = IDENTITY[:12] + [0, 1, 0, 1]
    write_glb(donor, document, binary)
    merge(base, donor, output)
    assert [clip["name"] for clip in read_glb(output)[0]["animations"]] == ["idle", "walk"]


@pytest.mark.parametrize("change", ["rest", "hierarchy", "name", "duplicate_path", "bind"])
def test_incompatible_or_ambiguous_rig_is_rejected(tmp_path, change):
    base, donor, output, document, binary = paths(tmp_path)
    if change == "rest":
        document["nodes"][1]["translation"] = [0, 2, 0]
    elif change == "hierarchy":
        document["nodes"][0]["children"] = [2]
        document["nodes"][2]["children"] = [1]
    elif change == "name":
        document["nodes"][1]["name"] = "UnmappedBone"
    elif change == "duplicate_path":
        document["nodes"].append(copy.deepcopy(document["nodes"][1]))
        document["nodes"][0]["children"].append(3)
    else:
        accessor = document["accessors"][document["skins"][0]["inverseBindMatrices"]]
        offset = document["bufferViews"][accessor["bufferView"]]["byteOffset"]
        struct.pack_into("<f", binary, offset + 13 * 4, -2)
    write_glb(donor, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


def test_matching_morph_semantics_merge_weights(tmp_path):
    base, donor, output, _, _ = paths(tmp_path, base_options={"morph": True}, donor_options={"morph": True})
    merge(base, donor, output)
    document, binary = read_glb(output)
    clip = document["animations"][1]
    assert clip["channels"][0]["target"] == {"node": 2, "path": "weights"}
    assert accessor_values(document, binary, clip["samplers"][0]["output"]) == [0, 0.25, 1, 0.75]


@pytest.mark.parametrize("names", [["Blink", "Smile"], ["Smile", "Smile"], None])
def test_morph_target_names_must_identify_same_ordered_shapes(tmp_path, names):
    base, donor, output, document, binary = paths(
        tmp_path, base_options={"morph": True}, donor_options={"morph": True},
    )
    if names is None:
        document["meshes"][0].pop("extras")
    else:
        document["meshes"][0]["extras"]["targetNames"] = names
    write_glb(donor, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


@pytest.mark.parametrize("times", [[0, 0], [1, 0], [-1, 1], [0, math.nan], [0, math.inf]])
def test_animation_times_are_finite_nonnegative_and_strictly_increasing(tmp_path, times):
    base, donor, output, document, binary = paths(tmp_path)
    index = document["animations"][0]["samplers"][0]["input"]
    view = document["bufferViews"][document["accessors"][index]["bufferView"]]
    struct.pack_into("<2f", binary, view["byteOffset"], *times)
    write_glb(donor, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


@pytest.mark.parametrize("change", ["nan", "quaternion", "count", "bounds", "path", "extension"])
def test_invalid_animation_payload_rejected(tmp_path, change):
    base, donor, output, document, binary = paths(tmp_path)
    animation = document["animations"][0]
    accessor = document["accessors"][animation["samplers"][0]["output"]]
    view = document["bufferViews"][accessor["bufferView"]]
    if change in {"nan", "quaternion"}:
        struct.pack_into("<f", binary, view["byteOffset"], math.nan if change == "nan" else 4)
    elif change == "count":
        accessor["count"] = 1
    elif change == "bounds":
        view["byteLength"] = 4
    elif change == "path":
        animation["channels"][0]["target"]["path"] = "unsupported"
    else:
        animation["channels"][0]["target"]["extensions"] = {
            "KHR_animation_pointer": {"pointer": "/materials/0/pbrMetallicRoughness/baseColorFactor"},
        }
        document["extensionsUsed"] = ["KHR_animation_pointer"]
    write_glb(donor, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


def test_cubic_spline_rotation_values_and_tangents_survive(tmp_path):
    base, donor, output, document, binary = paths(tmp_path)
    sampler = document["animations"][0]["samplers"][0]
    # Tangents are derivatives, not unit quaternions; only each middle VEC4 is a rotation.
    values = [0] * 4 + [0, 0, 0, 1] + [0, 0, 2, -2]
    values += [0, 0, 2, -2] + [0, 0, 1, 0] + [0] * 4
    sampler["output"] = append_accessor(document, binary, values, "VEC4")
    sampler["interpolation"] = "CUBICSPLINE"
    write_glb(donor, document, binary)
    merge(base, donor, output)
    merged, payload = read_glb(output)
    copied = merged["animations"][1]["samplers"][0]
    assert copied["interpolation"] == "CUBICSPLINE"
    assert accessor_values(merged, payload, copied["output"]) == values


@pytest.mark.parametrize("damage", ["magic", "version", "length", "truncated", "external"])
def test_invalid_or_external_glb_is_rejected_without_modifying_inputs(tmp_path, damage):
    base, donor, output, document, binary = paths(tmp_path)
    if damage == "external":
        document["buffers"][0]["uri"] = "external.bin"
        write_glb(donor, document, binary)
    else:
        raw = bytearray(donor.read_bytes())
        if damage == "magic":
            raw[:4] = b"BAD!"
        elif damage == "version":
            struct.pack_into("<I", raw, 4, 1)
        elif damage == "length":
            struct.pack_into("<I", raw, 8, len(raw) + 4)
        else:
            del raw[-3:]
        donor.write_bytes(raw)
    base_before, donor_before = base.read_bytes(), donor.read_bytes()
    with pytest.raises(ValueError):
        merge(base, donor, output)
    assert base.read_bytes() == base_before
    assert donor.read_bytes() == donor_before


def test_output_cannot_overwrite_source_asset(tmp_path):
    base, donor, _, _, _ = paths(tmp_path)
    base_before, donor_before = base.read_bytes(), donor.read_bytes()
    for output in (base, donor):
        with pytest.raises(ValueError):
            merge(base, donor, output)
    assert base.read_bytes() == base_before
    assert donor.read_bytes() == donor_before


@pytest.mark.parametrize("which", ["base", "donor"])
@pytest.mark.parametrize("invalid_name", ["", None, "duplicate"])
def test_clip_names_are_nonempty_and_unambiguous_within_each_input(tmp_path, which, invalid_name):
    base, donor, output, _, _ = paths(tmp_path)
    target = base if which == "base" else donor
    document, binary = read_glb(target)
    if invalid_name == "duplicate":
        document["animations"].append(copy.deepcopy(document["animations"][0]))
    elif invalid_name is None:
        document["animations"][0].pop("name")
    else:
        document["animations"][0]["name"] = invalid_name
    write_glb(target, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


def test_invalid_base_animation_cannot_be_silently_preserved(tmp_path):
    base, donor, output, _, _ = paths(tmp_path)
    document, binary = read_glb(base)
    sampler = document["animations"][0]["samplers"][0]
    document["accessors"][sampler["input"]]["count"] = 1
    write_glb(base, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


def multiply_matrix(left, right):
    """Column-major multiplication independent of the production matrix helper."""
    return [sum(left[k * 4 + row] * right[column * 4 + k] for k in range(4))
            for column in range(4) for row in range(4)]


def transformed_point(matrix, point):
    return [sum(matrix[column * 4 + row] * point[column] for column in range(3)) + matrix[12 + row]
            for row in range(3)]


def bind_space_fixture(tmp_path, correction, inverse_correction, *, seam_duplicate=False):
    base_document, base_binary = fixture()
    base_document["nodes"][1]["children"] = [3]
    base_document["nodes"].append({"name": "Tip", "translation": [0, 1, 0]})
    base_document["skins"][0]["joints"] = [1, 3]
    second_bind = IDENTITY[:12] + [0, -2, 0, 1]
    base_binds = [INVERSE_BONE, second_bind]
    base_document["skins"][0]["inverseBindMatrices"] = append_accessor(
        base_document, base_binary, INVERSE_BONE + second_bind, "MAT4",
    )
    donor_document, donor_binary = copy.deepcopy(base_document), bytearray(base_binary)
    donor_document["animations"][0]["name"] = "walk"
    donor_binds = [value for matrix in base_binds for value in multiply_matrix(matrix, correction)]
    donor_document["skins"][0]["inverseBindMatrices"] = append_accessor(
        donor_document, donor_binary, donor_binds, "MAT4",
    )
    points = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    if seam_duplicate:
        points.append(points[1])
    points = [value for point in points for value in transformed_point(inverse_correction, point)]
    primitive = donor_document["meshes"][0]["primitives"][0]
    primitive["attributes"]["POSITION"] = append_accessor(donor_document, donor_binary, points, "VEC3")
    if seam_duplicate:
        primitive["attributes"]["JOINTS_0"] = append_accessor(
            donor_document, donor_binary, [0] * 16, "VEC4", 5123,
        )
        primitive["attributes"]["WEIGHTS_0"] = append_accessor(
            donor_document, donor_binary, [1, 0, 0, 0] * 4, "VEC4",
        )
        primitive["indices"] = append_accessor(donor_document, donor_binary, [0, 3, 2], "SCALAR", 5123)
    base = write_glb(tmp_path / "base.glb", base_document, base_binary)
    donor = write_glb(tmp_path / "donor.glb", donor_document, donor_binary)
    return base, donor, tmp_path / "merged.glb", donor_document, donor_binary


@pytest.mark.parametrize("correction,inverse_correction", [
    (IDENTITY[:12] + [2, -3, 4, 1], IDENTITY[:12] + [-2, 3, -4, 1]),
    ([0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
     [0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
])
@pytest.mark.parametrize("seam_duplicate", [False, True])
def test_common_bind_space_change_accepts_equivalent_mesh_positions(
    tmp_path, correction, inverse_correction, seam_duplicate,
):
    base, donor, output, _, _ = bind_space_fixture(
        tmp_path, correction, inverse_correction, seam_duplicate=seam_duplicate,
    )
    original_document, original_binary = read_glb(base)
    merge(base, donor, output)
    document, binary = read_glb(output)
    assert [clip["name"] for clip in document["animations"]] == ["idle", "walk"]
    assert document["skins"] == original_document["skins"]
    assert document["meshes"] == original_document["meshes"]
    assert binary[:len(original_binary)] == original_binary


@pytest.mark.parametrize("mismatch", ["positions", "second_joint"])
def test_common_bind_space_change_rejects_different_geometry_or_individual_bind(tmp_path, mismatch):
    correction = IDENTITY[:12] + [2, -3, 4, 1]
    inverse_correction = IDENTITY[:12] + [-2, 3, -4, 1]
    base, donor, output, document, binary = bind_space_fixture(tmp_path, correction, inverse_correction)
    if mismatch == "positions":
        index = document["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
        accessor = document["accessors"][index]
        offset = document["bufferViews"][accessor["bufferView"]]["byteOffset"]
        struct.pack_into("<f", binary, offset, -1.5)
    else:
        index = document["skins"][0]["inverseBindMatrices"]
        accessor = document["accessors"][index]
        offset = document["bufferViews"][accessor["bufferView"]]["byteOffset"]
        # All local joints and the first bind still match; only the second bind differs.
        struct.pack_into("<f", binary, offset + (16 + 12) * 4, 2.5)
    write_glb(donor, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


def test_equivalent_rest_matrix_with_different_animated_trs_decomposition_is_rejected(tmp_path):
    base, donor, output, document, binary = paths(tmp_path)
    base_document, base_binary = read_glb(base)
    # Both rest matrices rotate 180 degrees about Z, but a copied rotation track
    # replaces only rotation and retains scale. Thus the decompositions are not interchangeable.
    base_document["nodes"][1]["scale"] = [-1, -1, 1]
    document["nodes"][1]["rotation"] = [0, 0, 1, 0]
    inverse_bind = [-1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1]
    for model, payload in ((base_document, bytearray(base_binary)), (document, binary)):
        accessor = model["accessors"][model["skins"][0]["inverseBindMatrices"]]
        offset = model["bufferViews"][accessor["bufferView"]]["byteOffset"]
        struct.pack_into("<16f", payload, offset, *inverse_bind)
        if model is base_document:
            base_binary = payload
    write_glb(base, base_document, base_binary)
    write_glb(donor, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


def test_rest_quaternion_sign_equivalence_is_accepted(tmp_path):
    base, donor, output, document, binary = paths(tmp_path)
    base_document, base_binary = read_glb(base)
    rotation = [0, 0, math.sqrt(0.5), math.sqrt(0.5)]
    base_document["nodes"][1]["rotation"] = [-value for value in rotation]
    document["nodes"][1]["rotation"] = rotation
    write_glb(base, base_document, base_binary)
    write_glb(donor, document, binary)
    merge(base, donor, output)
    assert [clip["name"] for clip in read_glb(output)[0]["animations"]] == ["idle", "walk"]


@pytest.mark.parametrize("uri", ["textures/base.png", "https://example.invalid/base.png"])
def test_external_image_uri_cannot_be_relocated_into_merged_glb(tmp_path, uri):
    base, donor, output, _, _ = paths(tmp_path)
    document, binary = read_glb(base)
    document["images"] = [{"uri": uri}]
    write_glb(base, document, binary)
    with pytest.raises(ValueError):
        merge(base, donor, output)


def test_embedded_data_image_uri_is_preserved(tmp_path):
    base, donor, output, _, _ = paths(tmp_path)
    document, binary = read_glb(base)
    document["images"] = [{
        "uri": "data:image/png;base64,"
               "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==",
    }]
    write_glb(base, document, binary)
    merge(base, donor, output)
    assert read_glb(output)[0]["images"] == document["images"]
