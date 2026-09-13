"""Real Blender retarget/clip recovery smoke with synthetic SOMA data; no inference/API."""

import json
import math
import shutil
import sys
import uuid
from pathlib import Path


def fixture(out, yaw):
    import bpy
    from mathutils import Matrix, Vector

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src/asset_auto"))
    import blender_character_worker as character
    from blender_authoring_tools import AuthoringContext
    from io_scene_gltf2.blender.com.gltf2_blender_ui import anim_ui_register

    anim_ui_register()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = bpy.data.armatures.new("test_skeleton")
    rig = bpy.data.objects.new("test_rig", data)
    bpy.context.scene.collection.objects.link(rig)
    rig.location, rig.scale, rig.rotation_euler.z = (.7, -.2, .3), (1.3,) * 3, yaw
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    definitions = [("Hips", (0, 0, 0), None), ("Chest", (0, .4, 0), "Hips"), ("Head", (0, .7, 0), "Chest")]
    for side, sign in (("Left", 1), ("Right", -1)):
        definitions.extend([(side + "Arm", (.2 * sign, .4, 0), "Chest"),
                            (side + "ForeArm", (.5 * sign, .4, 0), side + "Arm"),
                            (side + "Hand", (.8 * sign, .4, 0), side + "ForeArm"),
                            (side + "Leg", (.15 * sign, 0, 0), "Hips"),
                            (side + "Shin", (.15 * sign, -.45, 0), side + "Leg"),
                            (side + "Foot", (.15 * sign, -.9, 0), side + "Shin")])
    mapping = {name: f"joint_{index}" for index, (name, _, _) in enumerate(definitions)}
    convert = Matrix.Rotation(math.pi / 2, 3, "X")
    for name, point, parent in definitions:
        bone = data.edit_bones.new(mapping[name])
        bone.head = convert @ Vector(point) + Vector((0, 0, 1))
        # A-pose reference plus arbitrary display tails/rolls catch naive local Euler transfer.
        if name.endswith("ForeArm"):
            bone.head.z -= .2
        if name.endswith("Hand"):
            bone.head.z -= .4
        bone.tail = bone.head + Vector((.08, .1, .12))
        bone.roll = .63
        if parent:
            bone.parent = data.edit_bones[mapping[parent]]
    bpy.ops.object.mode_set(mode="OBJECT")
    vertices, faces, assignments = [], [], []
    for name, _, _ in definitions:
        center = rig.data.bones[mapping[name]].head_local
        first = len(vertices)
        vertices.extend(tuple(center[axis] + sign[axis] * .1 for axis in range(3)) for sign in
                        ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                         (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)))
        faces.extend(tuple(first + index for index in face) for face in
                     ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)))
        assignments.append((mapping[name], list(range(first, first + 8))))
    mesh = bpy.data.meshes.new("weighted_test_mesh")
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new("weighted_test_mesh", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = rig
    obj.modifiers.new("skin", "ARMATURE").object = rig
    for name, indices in assignments:
        obj.vertex_groups.new(name=name).add(indices, 1, "REPLACE")
    character.capture_preview_defaults()
    context = AuthoringContext(out / "fixture.blend", out, {})
    bpy.context.scene.render.fps = 24
    context.new_action(rig, "existing_idle")
    bone = rig.pose.bones[mapping["Head"]]
    bone.rotation_mode = "QUATERNION"
    for frame, angle in ((1, 0), (25, .2), (49, 0)):
        bone.rotation_quaternion = Matrix.Rotation(angle, 3, "X").to_quaternion()
        bone.keyframe_insert("rotation_quaternion", frame=frame)
    context.stash_action(rig)
    context.reset_pose()
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "fixture.blend"))
    character.export_character(out / "fixture.glb")
    rotations, positions = [], []
    for index in range(60):
        rotation = Matrix.Rotation(.4 * math.sin(index / 59 * math.pi), 3, "X")
        rotations.append([[list(row) for row in (rotation if name in ("LeftArm", "LeftForeArm", "LeftHand")
                                               else Matrix.Identity(3))] for name, _, _ in definitions])
        positions.append([0, 1 + .05 * index / 59, .6 * index / 59])
    (out / "motion-data.json").write_text(json.dumps({
        "fps": 30, "joint_names": [name for name, _, _ in definitions],
        "neutral_joints": [point for _, point, _ in definitions],
        "global_rotations": rotations, "root_positions": positions,
    }), encoding="utf-8")
    (out / "map.json").write_text(json.dumps(mapping), encoding="utf-8")


def verify(out, source, options):
    import bpy
    from mathutils import Vector

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src/asset_auto"))
    import blender_character_worker as character
    from blender_authoring_worker import action_fingerprint

    character.load_character(source)
    old = action_fingerprint(bpy.data.actions["existing_idle"])
    character.load_character(out / "authored.blend")
    assert action_fingerprint(bpy.data.actions["existing_idle"]) == old
    for path in (out / "source.blend", out / "asset.glb"):
        character.load_character(path)
        rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
        assert character.select_preview_clip(options["clip_name"])
        start, end = rig.animation_data.action.frame_range
        fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
        character.frame_at(start / fps)
        hips = rig.matrix_world @ rig.pose.bones[options["bone_map"]["Hips"]].head
        # Rest pelvis was at .3 + 1.3; SOMA root height must not be added twice.
        assert abs(hips.z - 1.6) < .003, (path, hips)
        upper = rig.matrix_world @ rig.pose.bones[options["bone_map"]["LeftArm"]].head
        elbow = rig.matrix_world @ rig.pose.bones[options["bone_map"]["LeftForeArm"]].head
        assert abs(upper.z - elbow.z) < .003, "Reference A-pose was not aligned to SOMA T-pose"
        character.frame_at(end / fps)
        delta = rig.matrix_world @ rig.pose.bones[options["bone_map"]["Hips"]].head - hips
        expected = Vector((0, 0, .065)) if options["in_place"] else Vector((.78, 0, .065))
        assert (delta - expected).length < .006, (path, delta, expected)
        assert character.select_preview_clip("existing_idle")
        character.frame_at(1)


def main():
    from asset_auto import pipeline
    from asset_auto.settings import executable
    from asset_auto.store import read_json, write_json

    root = Path(__file__).resolve().parents[1]
    sandbox = root / ".work" / ("smoke-text-motion-" + uuid.uuid4().hex[:8])
    sandbox.mkdir()
    blender = executable(root, "blender")
    command = [blender, "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
               "--python", str(Path(__file__).resolve()), "--"]
    checks = []
    for label, yaw, in_place in (("in-place", 0, True), ("travel-x", math.pi / 2, False)):
        out = sandbox / label
        out.mkdir()
        pipeline.run_logged([*command, "fixture", str(out), str(yaw)], out / "fixture.log")
        options = {"bone_map": read_json(out / "map.json"), "forward_axis": "-y" if in_place else "+x",
                   "clip_name": "synthetic_transfer", "in_place": in_place}
        shutil.copyfile(root / "src/asset_auto/blender_kimodo_retarget.py", out / "retarget.py")
        worker = {"authoring": True, "source": str(out / "fixture.blend"), "output": str(out),
                  "script": str(out / "retarget.py"), "parameters": options, "preserve_animations": True,
                  "require_animation": True, "require_rig": True, "preview_clips": [options["clip_name"]],
                  "triangle_budget": 1000}
        pipeline.blender(root, worker, out)
        checkpoint = read_json(out / "authoring-executed.json")
        pipeline.blender(root, worker, out)
        assert read_json(out / "authoring-executed.json") == checkpoint, "Resume reran the authoring script"
        pipeline.run_logged([*command, "verify", str(out), str(out / "fixture.blend"), json.dumps(options)], out / "verify.log")
        inspection = read_json(out / "inspection.json")
        assert {clip["name"] for clip in inspection["animations"]["clips"]} == {"existing_idle", "synthetic_transfer"}
        timing = read_json(out / "retarget-map.json")
        assert abs(timing["duration_rounding_seconds"]) <= .5 / timing["target_scene_fps"]
        checks.append(label)
    report = {"passed": True, "sandbox": str(sandbox), "cases": checks,
              "checks": ["A-pose reference alignment with arbitrary bone rolls", "root height and uniform world scale",
                         "in-place and rotated world-axis travel", "existing action fingerprint preserved",
                         "both clips activate in the final GLB and editable Blend", "authoring checkpoint reused",
                         "nonintegral frame-rate conversion retains both endpoint poses"],
              "scope": "Synthetic maintenance fixture; not evidence of learned inference or real character quality"}
    write_json(sandbox / "result.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args[0] == "fixture":
            fixture(Path(args[1]), float(args[2]))
        else:
            verify(Path(args[1]), Path(args[2]), json.loads(args[3]))
    else:
        main()
