"""Real rig/animation roundtrip test under .work, using authored deterministic fixtures."""

import hashlib
import json
import math
import struct
import sys
import uuid
from pathlib import Path


def document(path):
    with path.open("rb") as stream:
        magic, version, length = struct.unpack("<4sII", stream.read(12))
        assert magic == b"glTF" and version == 2 and length == path.stat().st_size
        size, kind = struct.unpack("<I4s", stream.read(8))
        assert kind == b"JSON"
        return json.loads(stream.read(size))


def make_fixture(sandbox):
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = bpy.data.objects.new("fill", None)
    bpy.context.scene.collection.objects.link(root)
    root.location = (1, 2, 0.4)
    root.scale = (1.1,) * 3
    motion = bpy.data.objects.new("motion", None)
    bpy.context.scene.collection.objects.link(motion)
    motion.parent = root
    armature = bpy.data.armatures.new("fixture_skeleton")
    rig = bpy.data.objects.new("fixture_rig", armature)
    bpy.context.scene.collection.objects.link(rig)
    rig.parent = motion
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    base = armature.edit_bones.new("base")
    base.head, base.tail = (0, 0, 0), (0, 0, 1)
    tip = armature.edit_bones.new("tip")
    tip.head, tip.tail, tip.parent, tip.use_connect = (0, 0, 1), (0, 0, 2), base, True
    bpy.ops.object.mode_set(mode="OBJECT")
    vertices = [(x, y, z) for z in (0, 1, 2)
                for x, y in ((-.2, -.2), (.2, -.2), (.2, .2), (-.2, .2))]
    faces = [(3, 2, 1, 0), (8, 9, 10, 11)]
    for level in (0, 4):
        faces.extend((level + index, level + (index + 1) % 4,
                      level + 4 + (index + 1) % 4, level + 4 + index) for index in range(4))
    data = bpy.data.meshes.new("weighted_column")
    data.from_pydata(vertices, [], faces)
    mesh = bpy.data.objects.new("key", data)
    bpy.context.scene.collection.objects.link(mesh)
    mesh.parent = rig
    group = mesh.vertex_groups.new(name="base")
    group.add(list(range(4)), 1, "REPLACE")
    group.add(list(range(4, 8)), .5, "REPLACE")
    group = mesh.vertex_groups.new(name="tip")
    group.add(list(range(4, 8)), .5, "REPLACE")
    group.add(list(range(8, 12)), 1, "REPLACE")
    modifier = mesh.modifiers.new("skin", "ARMATURE")
    modifier.object = rig
    material = bpy.data.materials.new("fixture_blue")
    material.diffuse_color = (.05, .32, .65, 1)
    mesh.data.materials.append(material)
    mesh.shape_key_add(name="Basis")
    morph = mesh.shape_key_add(name="wide")
    for vertex in morph.data:
        vertex.co.x *= 2
    morph.value = .2
    bone = rig.pose.bones["tip"]
    bone.rotation_mode = "XYZ"
    bpy.context.scene.render.fps = 24
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 0, 24
    for name, axis in (("bend", 1), ("sway", 0)):
        rig.animation_data_create()
        rig.animation_data.action = None
        for frame, angle in ((0, 0), (12, 1.15), (24, 0)):
            bone.rotation_euler = (0, 0, 0)
            bone.rotation_euler[axis] = angle
            bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        action = rig.animation_data.action
        action.name = name
        action.use_fake_user = True
        slot = rig.animation_data.action_slot
        track = rig.animation_data.nla_tracks.new()
        track.name, track.mute = name, True
        strip = track.strips.new(name, 0, action)
        strip.action_slot = slot
        if name == "bend":
            # This clip animates channels intentionally omitted by the next clip.
            motion.animation_data_create()
            motion.animation_data.action = action
            motion.animation_data.action_slot = action.slots.new("OBJECT", motion.name)
            for frame, offset in ((0, .45), (12, 1.5), (24, .45)):
                motion.location.x = offset
                motion.location.z = -offset / 6
                motion.keyframe_insert(data_path="location", frame=frame)
            track = motion.animation_data.nla_tracks.new()
            track.name, track.mute = name, True
            strip = track.strips.new(name, 0, action)
            strip.action_slot = motion.animation_data.action_slot
            motion.animation_data.action = None
            keys = mesh.data.shape_keys
            keys.animation_data_create()
            keys.animation_data.action = action
            keys.animation_data.action_slot = action.slots.new("KEY", keys.name)
            for frame, value in ((0, .2), (12, .9), (24, .2)):
                morph.value = value
                morph.keyframe_insert(data_path="value", frame=frame)
            track = keys.animation_data.nla_tracks.new()
            track.name, track.mute = name, True
            strip = track.strips.new(name, 0, action)
            strip.action_slot = keys.animation_data.action_slot
            keys.animation_data.action = None
    rig.animation_data.action = None
    # The clip begins away from the default node transform. Reimport must not
    # accidentally save that first animated pose as the asset's rest default.
    motion.location = (0, 0, 0)
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(sandbox / "fixture.blend"))
    for track in list(rig.animation_data.nla_tracks):
        if track.name != "bend":
            rig.animation_data.nla_tracks.remove(track)
    bpy.data.actions.remove(bpy.data.actions["sway"])
    bpy.ops.wm.save_as_mainfile(filepath=str(sandbox / "fixture-single.blend"))
    extra_rig = rig.copy()
    extra_rig.data = rig.data.copy()
    bpy.context.scene.collection.objects.link(extra_rig)
    extra_modifier = mesh.modifiers.new("unsupported_second_skin", "ARMATURE")
    extra_modifier.object = extra_rig
    bpy.ops.wm.save_as_mainfile(filepath=str(sandbox / "fixture-multiple-armatures.blend"))
    mesh.modifiers.remove(extra_modifier)
    bpy.data.objects.remove(extra_rig, do_unlink=True)
    for group in mesh.vertex_groups:
        group.remove(list(range(len(mesh.data.vertices))))
        group.add(list(range(len(mesh.data.vertices))), .00001, "REPLACE")
    bpy.ops.wm.save_as_mainfile(filepath=str(sandbox / "fixture-near-zero-weights.blend"))


def verify_scene(source, destination, names=("bend", "sway")):
    import bpy
    from mathutils import Vector

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    from blender_character_worker import load_character, select_preview_clip

    load_character(source)
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    assert len(rigs) == 1
    assert {bone.name for bone in rigs[0].data.bones} == {"base", "tip"}
    assert rigs[0].data.bones["tip"].parent.name == "base"
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    assert objects and rigs[0].parent is not None
    results = {}
    select_preview_clip(None)
    bpy.context.view_layer.update()
    default_root = bpy.data.objects["motion"].matrix_basis.copy()
    for name in names:
        assert select_preview_clip(name)
        snapshots = []
        for frame in (0, 12, 24):
            bpy.context.scene.frame_set(frame)
            if name == "sway":
                assert bpy.data.objects["motion"].matrix_basis == default_root
                assert math.isclose(objects[0].data.shape_keys.key_blocks["wide"].value,
                                    .2, abs_tol=1e-6)
            dependency_graph = bpy.context.evaluated_depsgraph_get()
            points = []
            for obj in objects:
                evaluated = obj.evaluated_get(dependency_graph)
                mesh = evaluated.to_mesh()
                points.extend(list(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices)
                evaluated.to_mesh_clear()
            snapshots.append(points)
        assert len(snapshots[0]) == len(snapshots[1])
        displacement = max((Vector(left) - Vector(right)).length
                           for left, right in zip(snapshots[0], snapshots[1], strict=True))
        assert displacement > .2, f"{name} did not deform the mesh"
        results[name] = {"max_displacement": displacement, "snapshots": snapshots}
    destination.write_text(json.dumps(results), encoding="utf-8")


def verify_preview_collisions(source, out):
    import bpy

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    from blender_character_worker import (
        animation_previews,
        animation_summary,
        load_character,
        render_views,
        select_preview_clip,
    )

    load_character(source)
    collision_mesh = next(obj for obj in bpy.context.scene.objects if obj.type == "MESH")
    if bpy.data.objects.get("key") != collision_mesh:
        if bpy.data.objects.get("key"):
            bpy.data.objects["key"].name = "original_key_transform"
        collision_mesh.name = "key"
    select_preview_clip(None)
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    protected = {name: bpy.data.objects[name].matrix_basis.copy() for name in ("key", "fill")}
    vertices = [tuple(vertex.co) for vertex in bpy.data.objects["key"].data.vertices]
    out.mkdir()
    render_views(out)
    animation_previews(out, animation_summary(document(source)))
    assert all(math.isclose(bpy.data.objects[name].matrix_basis[row][column], matrix[row][column],
                            abs_tol=1e-6) for name, matrix in protected.items()
               for row in range(4) for column in range(4))
    assert vertices == [tuple(vertex.co) for vertex in bpy.data.objects["key"].data.vertices]
    preview_lights = [obj for obj in bpy.context.scene.objects
                      if obj.type == "LIGHT" and obj.get("asset_preview_light")]
    assert len(preview_lights) == 3
    assert bpy.data.objects["key"].type == "MESH" and bpy.data.objects["fill"].type == "EMPTY"


def main():
    from asset_auto.pipeline import run_logged
    from asset_auto.settings import executable
    from asset_auto.store import read_json, write_json

    repository = Path(__file__).resolve().parents[1]
    sandbox = repository / ".work" / f"smoke-character-{uuid.uuid4().hex[:8]}"
    sandbox.mkdir(parents=True)
    blender = executable(repository, "blender")
    script = str(Path(__file__).resolve())
    worker = repository / "src" / "asset_auto" / "blender_character_worker.py"
    command = [blender, "--background", "--factory-startup", "--disable-autoexec",
               "--python-exit-code", "1"]
    run_logged(command + ["--python", script, "--", "fixture", str(sandbox)],
               sandbox / "fixture.log", cwd=repository)
    original = sandbox / "fixture.blend"
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    for label, expected in (("multiple-armatures", "Multiple armature modifiers"),
                             ("near-zero-weights", "only near-zero skin weights")):
        bad_source = sandbox / f"fixture-{label}.blend"
        bad_hash = hashlib.sha256(bad_source.read_bytes()).hexdigest()
        rejected = sandbox / f"rejected-{label}"
        rejected.mkdir()
        write_json(rejected / "request.json", {"source": str(bad_source), "output": str(rejected),
                                               "triangle_budget": 100, "require_rig": True})
        try:
            run_logged(command + ["--python", str(worker), "--", str(rejected / "request.json")],
                       rejected / "blender.log", cwd=repository)
            raise AssertionError(f"Unsupported {label} was silently accepted")
        except RuntimeError as error:
            assert expected in str(error)
        assert not (rejected / "asset.glb").exists() and not (rejected / "source.blend").exists()
        assert hashlib.sha256(bad_source.read_bytes()).hexdigest() == bad_hash
    previous = original
    outputs = []
    for label, height, names in (("blend-import", 3, ["bend", "sway"]),
                                 ("glb-roundtrip", None, ["bend", "sway"]),
                                 ("single-clip", None, ["walk"])):
        out = sandbox / label
        out.mkdir()
        source = sandbox / "fixture-single.blend" if label == "single-clip" else previous
        request = {"source": str(source), "output": str(out), "triangle_budget": 100,
                   "target_height": height, "require_rig": True, "require_animation": True}
        if label == "single-clip":
            request["animation_name"] = "walk"
        if label == "glb-roundtrip":
            request["input_yaw_degrees"] = 90
        write_json(out / "request.json", request)
        run_logged(command + ["--python", str(worker), "--", str(out / "request.json")],
                   out / "blender.log", cwd=repository)
        report = read_json(out / "inspection.json")
        assert report["passed"]
        assert report["rigging"]["bones"] == 2
        assert report["rigging"]["unweighted_vertices"] == 0
        assert report["rigging"]["exported_skins"] == 1
        assert report["normalization"]["input_yaw_degrees"] == (90 if label == "glb-roundtrip" else 0)
        exported = document(out / "asset.glb")
        motion_node = next(node for node in exported["nodes"] if node.get("name") == "motion")
        assert all(abs(value) < 1e-6 for value in motion_node.get("translation", (0, 0, 0)))
        assert len(exported["skins"]) == 1 and len(exported["skins"][0]["joints"]) == 2
        assert exported["skins"][0].get("inverseBindMatrices") is not None
        assert {clip["name"] for clip in exported["animations"]} == set(names)
        for animation in exported["animations"]:
            assert any(channel["target"]["path"] == "rotation" for channel in animation["channels"])
        for mesh in exported["meshes"]:
            for primitive in mesh["primitives"]:
                assert "JOINTS_0" in primitive["attributes"]
                assert "WEIGHTS_0" in primitive["attributes"]
        preview = read_json(out / "animation-previews.json")
        assert preview["sampled_clips"] == len(names)
        quality = preview["quality_checks"]
        assert quality["scope"] == "preview_samples_only"
        assert quality["floor_reference"] == ("ground_plane" if height else "rest_pose_bounds")
        assert any("below the" in warning for warning in quality["warnings"])
        assert report["animation_quality"] == quality
        assert all(warning in report["warnings"] for warning in quality["warnings"])
        for clip in preview["clips"]:
            if clip["name"] in ("bend", "walk"):
                assert clip["floor_check"]["below_floor_samples"] >= 1
                assert clip["floor_check"]["maximum_penetration_m"] > .1
            elif clip["name"] == "sway":
                assert clip["floor_check"]["below_floor_samples"] == 0
        for clip in preview["clips"]:
            assert len(clip["samples"]) == 3
            assert all((out / sample["file"]).is_file() for sample in clip["samples"])
        assert all((out / f"{view}.png").is_file()
                   for view in ("front", "back", "left", "right", "perspective"))
        for suffix in ("glb", "blend"):
            source = out / ("asset.glb" if suffix == "glb" else "source.blend")
            run_logged(command + ["--python", script, "--", "verify", str(source),
                                  str(out / f"poses-{suffix}.json"), json.dumps(names)],
                       out / f"verify-{suffix}.log", cwd=repository)
        # GLB duplicates UV/normal seams, so compare deformed extents, not vertex indices.
        blend_poses, glb_poses = (read_json(out / f"poses-{kind}.json") for kind in ("blend", "glb"))
        for name in names:
            for left, right in zip(blend_poses[name]["snapshots"], glb_poses[name]["snapshots"], strict=True):
                for axis in range(3):
                    for reduce in (min, max):
                        assert math.isclose(reduce(point[axis] for point in left),
                                            reduce(point[axis] for point in right), abs_tol=1e-4)
        if label == "glb-roundtrip":
            before_rotation = read_json(sandbox / "blend-import" / "poses-glb.json")
            for name in names:
                for before, after in zip(before_rotation[name]["snapshots"],
                                         glb_poses[name]["snapshots"], strict=True):
                    expected = [(-point[1], point[0], point[2]) for point in before]
                    for axis in range(3):
                        for reduce in (min, max):
                            assert math.isclose(reduce(point[axis] for point in expected),
                                                reduce(point[axis] for point in after), abs_tol=1e-4)
        outputs.append(str(out))
        previous = out / "asset.glb"
    run_logged(command + ["--python", script, "--", "verify-preview-collisions", str(previous),
                          str(sandbox / "preview-name-collisions")],
               sandbox / "preview-name-collisions.log", cwd=repository)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == original_hash
    report = {"passed": True, "sandbox": str(sandbox), "outputs": outputs,
              "checks": ["two-bone hierarchy and inverse bind matrices preserved",
                         "skin weights and deformed poses survive GLB and blend roundtrip",
                         "both animation clips/channels preserved",
                         "single-clip rename matches source and GLB",
                         "shared-parent size normalization",
                         "90-degree input yaw preserves skins and rotates every deformed pose",
                         "multiple armature modifiers rejected before saving or exporting",
                         "near-zero weights rejected before GLB can replace bone influences",
                         "five static views and three samples per clip",
                         "preview lights preserve assets named key and fill",
                         "clip switching restores root transforms and nonzero morph defaults",
                         "first animated root pose does not replace GLB rest node defaults",
                         "sampled below-floor motion is reported without shifting animation",
                         "input source hash unchanged"]}
    write_json(sandbox / "result.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if "--" not in sys.argv:
        main()
    else:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args[0] == "fixture":
            make_fixture(Path(args[1]))
        elif args[0] == "verify":
            verify_scene(Path(args[1]), Path(args[2]), json.loads(args[3]))
        elif args[0] == "verify-preview-collisions":
            verify_preview_collisions(Path(args[1]), Path(args[2]))
