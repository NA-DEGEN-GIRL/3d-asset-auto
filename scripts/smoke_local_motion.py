"""Real Blender local-motion smoke with an isolated authored maintenance fixture."""

import hashlib
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace


def fixture(out):
    import bpy

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    import blender_character_worker as character

    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = bpy.data.armatures.new("fixture")
    rig = bpy.data.objects.new("fixture", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    definitions = [
        ("root", (0, 0, 0), (0, 0, .15), None),
        ("pelvis", (0, 0, .8), (0, 0, 1.0), "root"),
        ("chest", (0, 0, 1.0), (0, 0, 1.25), "pelvis"),
        ("head", (0, 0, 1.25), (0, 0, 1.5), "chest"),
    ]
    for side, sign in (("left", 1), ("right", -1)):
        definitions.extend([
            (f"{side}_thigh", (.13 * sign, 0, .8), (.13 * sign, 0, .42), "pelvis"),
            (f"{side}_shin", (.13 * sign, 0, .42), (.13 * sign, 0, .12), f"{side}_thigh"),
            (f"{side}_foot", (.13 * sign, 0, .12), (.13 * sign, -.18, .07), f"{side}_shin"),
            (f"{side}_upper_arm", (.22 * sign, 0, 1.17), (.43 * sign, 0, .92), "chest"),
        ])
    mapping = {}
    for index, (role, head, tail, parent) in enumerate(definitions):
        name = f"bone_{index}"
        mapping[role] = name
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if role.endswith("thigh"):
            # Real learned GLBs can orient the display tail away from the child
            # joint. Actual joint positions, not bone-local Y, define the limb.
            bone.tail = (head[0] + .2, head[1] + .1, head[2] - .05)
        if parent:
            bone.parent = data.edit_bones[mapping[parent]]
        bone.use_deform = role != "root"
    bpy.ops.object.mode_set(mode="OBJECT")
    vertices, faces, assignments = [], [], []
    for role, head, tail, _ in definitions:
        if role == "root":
            continue
        middle = [(head[i] + tail[i]) / 2 for i in range(3)]
        size = [.11, .12, max(.12, abs(head[2] - tail[2]))]
        if role == "chest":
            size = [.4, .18, .25]
        if role == "head":
            size = [.21, .2, .25]
        if role.endswith("foot"):
            size, middle = [.13, .28, .12], [head[0], -.08, .06]
        offset = len(vertices)
        vertices.extend(tuple(middle[axis] + sign[axis] * size[axis] / 2 for axis in range(3))
                        for sign in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                                     (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)))
        faces.extend(tuple(offset + index for index in face)
                     for face in ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
                                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)))
        assignments.append((mapping[role], list(range(offset, offset + 8))))
    mesh = bpy.data.meshes.new("fixture_skin")
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new("fixture_skin", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = rig
    for name, indices in assignments:
        obj.vertex_groups.new(name=name).add(indices, 1, "REPLACE")
    obj.modifiers.new("skin", "ARMATURE").object = rig
    material = bpy.data.materials.new("local_motion_fixture_blue")
    material.diffuse_color = (.05, .3, .6, 1)
    obj.data.materials.append(material)
    character.export_character(out / "fixture.glb")
    (out / "bone-map.json").write_text(json.dumps(mapping), encoding="utf-8")
    import blender_motion_worker as motion_worker
    from mathutils import Vector

    character.load_character(str(out / "fixture.glb"))
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    low, high = character.evaluated_bounds()
    motion = motion_worker.Motion(rig, mapping, Vector((0, -1, 0)), low.z, high.z - low.z)
    for side in ("left", "right"):
        name, child = mapping[f"{side}_thigh"], mapping[f"{side}_shin"]
        baseline = rig.pose.bones[name].matrix.copy()
        head, child_head = motion.rest[name].translation, motion.rest[child].translation
        motion.direction(name, head, child_head, child_head)
        assert all(abs(baseline[row][column] - rig.pose.bones[name].matrix[row][column]) < 1e-5
                   for row in range(4) for column in range(4))


def glb_document(path):
    import struct

    with path.open("rb") as stream:
        stream.read(12)
        length, kind = struct.unpack("<I4s", stream.read(8))
        assert kind == b"JSON"
        return json.loads(stream.read(length))


def clip_signatures(path):
    """Capture actual sampler bytes and targets, independent of accessor indexes."""
    import struct

    raw = path.read_bytes()
    length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20:20 + length])
    binary = raw[28 + length:]

    def accessor(index):
        item = document["accessors"][index]
        view = document["bufferViews"][item["bufferView"]]
        start = view.get("byteOffset", 0)
        return {"accessor": {key: value for key, value in item.items() if key != "bufferView"},
                "buffer_view": {key: value for key, value in view.items() if key not in ("byteOffset", "buffer")},
                "sha256": hashlib.sha256(binary[start:start + view["byteLength"]]).hexdigest()}

    return {animation["name"]: {
        "samplers": [{"interpolation": sampler.get("interpolation", "LINEAR"),
                      "input": accessor(sampler["input"]), "output": accessor(sampler["output"])}
                     for sampler in animation["samplers"]],
        "channels": [{"sampler": channel["sampler"], "path": channel["target"]["path"],
                      "node": document["nodes"][channel["target"]["node"]]["name"]}
                     for channel in animation["channels"]],
    } for animation in document.get("animations", [])}


def verify_bundle(glb_path, blend_path, names):
    import bpy

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    import blender_character_worker as character

    for path in (glb_path, blend_path):
        character.load_character(str(path))
        assert len([obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]) == 1
        assert len(character.meshes()) == 1
        for name in names:
            assert character.select_preview_clip(name), f"{path}: cannot activate retained {name}"
            bpy.context.scene.frame_set(12)
            low, high = character.evaluated_bounds()
            assert high.z > low.z


def main():
    from asset_auto.glb_transform import rotate_scene_y
    from asset_auto.local_motion import generate
    from asset_auto.pipeline import run_logged
    from asset_auto.settings import executable
    from asset_auto.store import read_json, write_json

    repository = Path(__file__).resolve().parents[1]
    sandbox = repository / ".work" / f"smoke-local-motion-{uuid.uuid4().hex[:8]}"
    sandbox.mkdir(parents=True)
    run_logged([executable(repository, "blender"), "--background", "--factory-startup",
                "--disable-autoexec", "--python-exit-code", "1", "--python", str(Path(__file__)),
                "--", str(sandbox)], sandbox / "fixture.log", cwd=repository)
    source = sandbox / "fixture.glb"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    original = glb_document(source)
    mapping = read_json(sandbox / "bone-map.json")
    options = {"rig_forward_axis": "+z", "animate_in_place": True, "animation": "walk"}
    for label, invalid in (("missing-map", {}),
                           ("duplicate-map", {**mapping, "right_thigh": mapping["left_thigh"]}),
                           ("bad-chain", {**mapping, "left_thigh": mapping["left_shin"],
                                          "left_shin": mapping["left_thigh"]})):
        try:
            generate(repository, SimpleNamespace(**options, bone_map=invalid), sandbox / label, source)
        except RuntimeError as error:
            assert any(message in str(error) for message in ("observed bone_map", "distinct bones",
                                                              "ordered thigh/shin/foot"))
        else:
            raise AssertionError(f"Invalid mapping was accepted: {label}")
    outputs = []
    for animation, in_place in (("idle", True), ("walk", True), ("run", True), ("walk", False)):
        label = animation if in_place else "walk-travel"
        out = sandbox / label
        request = SimpleNamespace(animation=animation, bone_map=mapping,
                                  rig_forward_axis="+z", animate_in_place=in_place)
        result = generate(repository, request, out, source)
        document = glb_document(out / "generated.glb")
        assert len(document["animations"]) == 1
        assert document["animations"][0]["name"] == animation
        assert len(document["skins"][0]["joints"]) == len(original["skins"][0]["joints"])
        assert [item["name"] for item in document["materials"]] == [item["name"]
                                                                    for item in original["materials"]]
        assert result["ground_checks"]["samples"] == 2 * (result["authored_frames"] - 1) + 1
        assert result["ground_checks"]["below_floor_samples"] == 0
        assert result["ground_checks"]["maximum_penetration_m"] < .003
        if animation != "idle":
            feet = result["ground_checks"]["foot_joint_motion"]
            assert all(foot["joint_head_path_m"] > .2 for foot in feet.values())
            if not in_place:
                assert all(foot["joint_head_extent_xyz_m"][1] > .4 for foot in feet.values())
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        outputs.append(str(out))
    rotated = sandbox / "fixture-x-forward.glb"
    rotate_scene_y(source, rotated, 90)
    result = generate(repository, SimpleNamespace(animation="walk", bone_map=mapping,
                                                  rig_forward_axis="+x", animate_in_place=False),
                      sandbox / "walk-x-forward", rotated)
    assert result["ground_checks"]["below_floor_samples"] == 0
    for foot in result["ground_checks"]["foot_joint_motion"].values():
        assert foot["joint_head_extent_xyz_m"][0] > .4
        assert foot["joint_head_extent_xyz_m"][1] < .01
    outputs.append(str(sandbox / "walk-x-forward"))
    accumulated = source
    names = set()
    signatures = {}
    for animation in ("idle", "walk", "run", "walk"):
        replacing = animation in names
        label = f"accumulate-{animation}" if not replacing else "replace-walk"
        out = sandbox / label
        previous = accumulated
        previous_hash = hashlib.sha256(previous.read_bytes()).hexdigest()
        previous_document = glb_document(previous)
        request = SimpleNamespace(animation=animation, bone_map=mapping,
                                  rig_forward_axis="+z", animate_in_place=not replacing)
        result = generate(repository, request, out, previous)
        accumulated = out / "generated.glb"
        current = glb_document(accumulated)
        names.add(animation)
        assert {clip["name"] for clip in current["animations"]} == names
        assert len(current["animations"]) == len(names)
        for field in ("nodes", "meshes", "materials", "skins"):
            assert current[field] == previous_document[field], f"Merge changed base {field}"
        actual = clip_signatures(accumulated)
        for name, signature in signatures.items():
            if name != animation:
                assert actual[name] == signature, f"Existing clip {name} was modified"
        if replacing:
            assert actual[animation] != signatures[animation], "Requested replacement kept the old motion"
        signatures = actual
        assert result["clip_policy"] == "preserve_existing_replace_requested"
        assert result["ground_checks"]["below_floor_samples"] == 0
        assert hashlib.sha256(previous.read_bytes()).hexdigest() == previous_hash
        outputs.append(str(out))
    run_logged([executable(repository, "blender"), "--background", "--factory-startup",
                "--disable-autoexec", "--python-exit-code", "1", "--python", str(Path(__file__)),
                "--", "verify-bundle", str(accumulated), str(accumulated.with_suffix(".blend")),
                json.dumps(sorted(names))], sandbox / "verify-bundle.log", cwd=repository)
    report = {"passed": True, "sandbox": str(sandbox), "outputs": outputs,
              "checks": ["generic bone names require observed mapping",
                         "duplicate/incorrect hierarchy maps rejected",
                         "idle/walk/run and root-travel clips export with original skins/materials",
                         "all frames and half frames reimported with bounded floor penetration",
                         "rotated input hierarchy uses the requested forward axis for actual joint travel",
                         "skewed display bone axes preserve rest orientation using actual child joints",
                         "sequential idle/walk/run accumulate in one GLB without duplicated geometry or rigs",
                         "requested name replacement retains every other clip's original sampler bytes",
                         "merged GLB and editable blend both activate all retained clips",
                         "walk/run move real ankle joints", "source file remains unchanged"],
              "scope": "synthetic maintenance fixture; visual quality of real assets is separate"}
    write_json(sandbox / "result.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args[0] == "verify-bundle":
            verify_bundle(Path(args[1]), Path(args[2]), json.loads(args[3]))
        else:
            fixture(Path(args[0]))
    else:
        main()
