"""Exercise authored rig edits and custom clips with real Blender, without model inference."""

import hashlib
import json
import math
import sys
import textwrap
import uuid
from pathlib import Path


def make_fixtures(sandbox):
    import bpy
    from smoke_character import make_fixture

    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = bpy.data.objects.new("door_root", None)
    bpy.context.scene.collection.objects.link(root)
    root.location = (2, -1, .4)
    root.scale = (1.3,) * 3
    root.rotation_euler.z = .3
    mesh = bpy.data.meshes.new("hinged_panel_mesh")
    mesh.from_pydata([(x, y, z) for z in (0, 2) for y in (-.05, .05) for x in (0, 1)], [],
                     [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
                      (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)])
    door = bpy.data.objects.new("hinged_panel", mesh)
    bpy.context.scene.collection.objects.link(door)
    door.parent = root
    door.location = (.25, .1, 0)
    door.rotation_mode = "XYZ"
    material = bpy.data.materials.new("door_brown")
    material.diffuse_color = (.32, .12, .03, 1)
    door.data.materials.append(material)
    bpy.context.scene.render.fps = 24
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 0, 24
    for frame in (0, 24):
        door.rotation_euler.z = 0
        door.keyframe_insert(data_path="rotation_euler", frame=frame)
    action = door.animation_data.action
    action.name = "closed"
    action.use_fake_user = True
    track = door.animation_data.nla_tracks.new()
    track.name, track.mute = "closed", True
    strip = track.strips.new("closed", 0, action)
    strip.action_slot = door.animation_data.action_slot
    door.animation_data.action = None
    bpy.ops.wm.save_as_mainfile(filepath=str(sandbox / "door.blend"))
    curves = action.layers[0].strips[0].channelbags[0].fcurves
    curve = next(curve for curve in curves if curve.data_path == "rotation_euler" and curve.array_index == 2)
    curve.modifiers.new("NOISE").strength = 1
    bpy.ops.wm.save_as_mainfile(filepath=str(sandbox / "door-noise.blend"))
    character = sandbox / "character-fixtures"
    character.mkdir()
    make_fixture(character)


def snapshot(source, destination, clip_names, kind):
    import bpy

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    from blender_character_worker import load_character, meshes, select_preview_clip

    load_character(source)
    select_preview_clip(None)
    bpy.context.view_layer.update()

    def points():
        result = []
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for obj in meshes():
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            result.extend(list(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices)
            evaluated.to_mesh_clear()
        return result

    def extents(vertices):
        return [[reduce(point[axis] for point in vertices) for axis in range(3)]
                for reduce in (min, max)]

    rest = points()
    result = {"rest_bounds": extents(rest), "clips": {}}
    if kind == "door":
        assert not any(obj.type == "ARMATURE" for obj in bpy.context.scene.objects)
        door = bpy.data.objects["hinged_panel"]
        assert door.parent.name == "door_root"
        root = bpy.data.objects["door_root"]
        assert all(math.isclose(a, b, abs_tol=1e-5)
                   for a, b in zip(root.location, (2, -1, .4), strict=True))
        assert all(math.isclose(value, 1.3, abs_tol=1e-5) for value in root.scale)
        if "baked_open" in clip_names:
            assert not door.constraints
            assert bpy.data.objects.get("temporary_motion_driver") is None
        result["rigs"] = 0
    else:
        rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        assert len(rigs) == 1
        rig = rigs[0]
        assert {bone.name for bone in rig.data.bones} == {"base", "tip"}
        assert rig.data.bones["tip"].parent.name == "base"
        assert rig.parent.name == "motion" and rig.parent.parent.name == "fill"
        obj = next(obj for obj in meshes() if obj.data.shape_keys)
        assert math.isclose(obj.data.shape_keys.key_blocks["wide"].value, .2, abs_tol=1e-6)
        result["morph_default"] = obj.data.shape_keys.key_blocks["wide"].value
        if kind == "edited" and source.suffix == ".blend":
            tail = rig.data.bones["tip"].tail_local
            assert math.isclose(tail.x, .2, abs_tol=1e-6)
            assert math.isclose(tail.z, 2.2, abs_tol=1e-6)
            assert math.isclose(obj.vertex_groups["base"].weight(4), .2, abs_tol=1e-6)
            assert math.isclose(obj.vertex_groups["tip"].weight(4), .8, abs_tol=1e-6)
            result["rig_and_weight_edit"] = True
        if kind == "edited":
            material = obj.data.materials[0]
            color = material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value
            assert all(math.isclose(a, b, abs_tol=1e-5)
                       for a, b in zip(color, (.65, .08, .02, 1), strict=True))
            result["material_edit"] = True
    for name in clip_names:
        assert select_preview_clip(name), f"Missing exported clip: {name}"
        samples = []
        for frame in (0, 12, 24):
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            samples.append(points())
        movement = max(math.dist(a, b) for a, b in zip(samples[0], samples[1], strict=True))
        if name != "closed":
            assert movement > .1, f"{name} does not actually move/deform the mesh ({movement:.6g} m)"
        else:
            assert movement < 1e-6
        result["clips"][name] = {"movement": movement, "bounds": [extents(sample) for sample in samples]}
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")


def near(left, right, tolerance=1e-4):
    if isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right, strict=True):
            near(a, b, tolerance)
    else:
        assert math.isclose(left, right, abs_tol=tolerance), (left, right)


def skeletal_bake_probe(source, output):
    """Check evaluated pose-constraint baking directly, without rendering fixtures again."""
    import bpy

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    from blender_authoring_tools import AuthoringContext
    from blender_character_worker import export_character, glb_document, load_character

    load_character(source)
    context = AuthoringContext(source, output, {})
    context.reset_pose()
    rig = context.armatures[0]
    driver = bpy.data.objects.new("temporary_retarget_driver", None)
    bpy.context.scene.collection.objects.link(driver)
    driver.rotation_mode = "XYZ"
    driver_action = context.new_action(driver, "temporary_retarget_source")
    for frame, angle in ((0, 0), (12, .9), (24, 0)):
        driver.rotation_euler.x = math.pi / 2 + angle
        driver.keyframe_insert(data_path="rotation_euler", frame=frame)
    constraint = rig.pose.bones["tip"].constraints.new("COPY_ROTATION")
    constraint.target = driver
    constraint.owner_space = "WORLD"
    constraint.target_space = "WORLD"
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    start_matrix = rig.pose.bones["tip"].matrix.copy()
    bpy.context.scene.frame_set(12)
    bpy.context.view_layer.update()
    middle_matrix = rig.pose.bones["tip"].matrix.copy()
    assert max(abs(start_matrix[row][column] - middle_matrix[row][column])
               for row in range(4) for column in range(4)) > .1, (
                   "Source pose constraint did not evaluate motion", tuple(driver.rotation_euler),
                   rig.data.pose_position, constraint.is_valid, constraint.influence)
    context.bake_action(rig, "retarget_probe", 0, 24)
    assert not rig.pose.bones["tip"].constraints
    bpy.data.objects.remove(driver, do_unlink=True)
    bpy.data.actions.remove(driver_action, do_unlink=True)
    context.reset_pose()
    output.mkdir()
    export_character(output / "asset.glb")
    exported = glb_document(output / "asset.glb")
    assert {clip["name"] for clip in exported["animations"]} == {"bend", "sway", "retarget_probe"}
    assert len(exported["skins"]) == 1 and len(exported["skins"][0]["joints"]) == 2
    snapshot(output / "asset.glb", output / "poses.json", ["bend", "sway", "retarget_probe"], "original")


def main():
    from smoke_character import document

    from asset_auto.pipeline import run_logged
    from asset_auto.settings import executable
    from asset_auto.store import read_json, write_json

    repository = Path(__file__).resolve().parents[1]
    sandbox = repository / ".work" / f"smoke-authoring-{uuid.uuid4().hex[:8]}"
    sandbox.mkdir(parents=True)
    worker = repository / "src" / "asset_auto" / "blender_authoring_worker.py"
    command = [executable(repository, "blender"), "--background", "--factory-startup",
               "--disable-autoexec", "--python-exit-code", "1"]
    self_script = str(Path(__file__).resolve())
    run_logged(command + ["--python", self_script, "--", "fixture", str(sandbox)],
               sandbox / "fixtures.log", cwd=repository)
    door_source = sandbox / "door.blend"
    character_source = sandbox / "character-fixtures" / "fixture.blend"
    noise_source = sandbox / "door-noise.blend"
    sources = {source: hashlib.sha256(source.read_bytes()).hexdigest()
               for source in (door_source, character_source, noise_source)}
    run_logged(command + ["--python", self_script, "--", "skeletal-bake", str(character_source),
                          str(sandbox / "skeletal-bake")], sandbox / "skeletal-bake.log", cwd=repository)

    def author(label, source, code, *, preserve=True, expected_failure=False, require_rig=False,
               failure_text=None):
        out = sandbox / label
        out.mkdir()
        script = out / "author.py"
        script.write_text(textwrap.dedent(code), encoding="utf-8")
        write_json(out / "request.json", {"source": str(source), "script": str(script),
                   "output": str(out), "parameters": {"angle": 1.2}, "preserve_animations": preserve,
                   "binding_sha256": hashlib.sha256(label.encode()).hexdigest(),
                   "triangle_budget": 100, "require_animation": True, "require_rig": require_rig})
        try:
            run_logged(command + ["--python", str(worker), "--", str(out / "request.json")],
                       out / "blender.log", cwd=repository)
        except RuntimeError as error:
            if not expected_failure:
                raise
            if failure_text is not None:
                assert failure_text in str(error), str(error)
            assert not (out / "asset.glb").exists() and not (out / "source.blend").exists()
            return out
        assert not expected_failure, f"Invalid authoring unexpectedly succeeded: {label}"
        report = read_json(out / "inspection.json")
        assert report["passed"]
        assert (out / "authoring.json").is_file()
        assert report["normalization"]["mode"] == "preserve"
        assert all((out / f"{view}.png").is_file()
                   for view in ("front", "back", "left", "right", "perspective"))
        previews = read_json(out / "animation-previews.json")
        assert previews["sampled_clips"] == report["animations"]["count"]
        assert all(len(clip["samples"]) == 3 and
                   all((out / sample["file"]).is_file() for sample in clip["samples"])
                   for clip in previews["clips"])
        return out

    open_script = """
        import bpy
        context.reset_pose()
        door = context.objects["hinged_panel"]
        assert context.parameters["angle"] == 1.2
        assert str(context.source).endswith(".blend")
        marker = context.output / "script-count.txt"
        assert not marker.exists(), "The authoring script was executed more than once"
        marker.write_text("1", encoding="utf-8")
        context.new_action(door, "open")
        for frame, angle in ((0, 0), (12, context.parameters["angle"]), (24, 1.2)):
            door.rotation_euler.z = angle
            door.keyframe_insert(data_path="rotation_euler", frame=frame)
        context.stash_action(door)
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = 0, 24
    """
    door_out = author("door-open", door_source, open_script)
    assert {clip["name"] for clip in document(door_out / "asset.glb")["animations"]} == {"closed", "open"}
    assert not document(door_out / "asset.glb").get("skins")
    # A completed execution checkpoint resumes export/review without running arbitrary
    # authoring code again. Its saved source/script/binding are independently checked.
    authored_hash = hashlib.sha256((door_out / "authored.blend").read_bytes()).hexdigest()
    run_logged(command + ["--python", str(worker), "--", str(door_out / "request.json")],
               door_out / "resume.log", cwd=repository)
    assert (door_out / "script-count.txt").read_text(encoding="utf-8") == "1"
    assert hashlib.sha256((door_out / "authored.blend").read_bytes()).hexdigest() == authored_hash
    stable_request = read_json(door_out / "request.json")
    tampered_source = sandbox / "tampered-source.blend"
    tampered_source.write_bytes(door_source.read_bytes() + b"tampered fixture input")
    tampered_script = sandbox / "tampered-script.py"
    tampered_script.write_text((door_out / "author.py").read_text(encoding="utf-8") + "\n# changed\n",
                               encoding="utf-8")
    for field, replacement in (("binding_sha256", "changed"), ("source", str(tampered_source)),
                                ("script", str(tampered_script))):
        request_path = door_out / f"tamper-{field}.json"
        write_json(request_path, {**stable_request, field: replacement})
        try:
            run_logged(command + ["--python", str(worker), "--", str(request_path)],
                       request_path.with_suffix(".log"), cwd=repository)
        except RuntimeError as error:
            assert "checkpoint" in str(error).lower()
        else:
            raise AssertionError(f"Changed checkpoint {field} was accepted")
    baked_out = author("door-baked", door_out / "asset.glb", """
        import bpy
        context.reset_pose()
        door = context.objects["hinged_panel"]
        driver = bpy.data.objects.new("temporary_motion_driver", None)
        bpy.context.scene.collection.objects.link(driver)
        driver.parent = door.parent
        driver.rotation_mode = "XYZ"
        context.capture_rest()
        action = context.new_action(driver, "temporary_driver_action")
        for frame, angle in ((0, 0), (12, .9), (24, .3)):
            driver.rotation_euler.z = angle
            driver.keyframe_insert(data_path="rotation_euler", frame=frame)
        constraint = door.constraints.new("COPY_ROTATION")
        constraint.target = driver
        constraint.owner_space = "LOCAL"
        constraint.target_space = "LOCAL"
        context.bake_action(door, "baked_open", 0, 24)
        assert not door.constraints
        bpy.data.objects.remove(driver, do_unlink=True)
        bpy.data.actions.remove(action, do_unlink=True)
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = 0, 24
    """)
    assert {clip["name"] for clip in document(baked_out / "asset.glb")["animations"]} == {
        "closed", "open", "baked_open"}
    pivot_out = author("new-pivot-rest", door_source, """
        import bpy
        if __name__ == "__main__":
            context.reset_pose()
            pivot = bpy.data.objects.new("new_animated_pivot", None)
            bpy.context.scene.collection.objects.link(pivot)
            pivot.location = (3, 4, 5)
            door = context.objects["hinged_panel"]
            pivot.parent = door.parent
            door.parent = pivot
            door.matrix_parent_inverse = pivot.matrix_basis.inverted()
            context.new_action(pivot, "pivot_motion")
            for frame, x in ((0, 3.5), (12, 4), (24, 3.5)):
                pivot.location = (x, 4, 5)
                pivot.keyframe_insert(data_path="location", frame=frame)
            context.stash_action(pivot)
    """)
    pivot_document = document(pivot_out / "asset.glb")
    assert {clip["name"] for clip in pivot_document["animations"]} == {"closed", "pivot_motion"}
    pivot_node = next(node for node in pivot_document["nodes"] if node.get("name") == "new_animated_pivot")
    near(pivot_node["translation"], [3, 5, -4])  # Blender Z-up to glTF Y-up.
    character_out = author("character-edit", character_source, """
        import bpy
        context.reset_pose()
        rig = context.armatures[0]
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        rig.data.edit_bones["tip"].tail = (.2, 0, 2.2)
        bpy.ops.object.mode_set(mode="OBJECT")
        mesh = context.objects["key"]
        mesh.vertex_groups["base"].add(list(range(4, 8)), .2, "REPLACE")
        mesh.vertex_groups["tip"].add(list(range(4, 8)), .8, "REPLACE")
        material = mesh.data.materials[0]
        material.use_nodes = True
        material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (.65, .08, .02, 1)
        context.capture_rest()
        context.new_action(rig, "custom_wave")
        bone = rig.pose.bones["tip"]
        bone.rotation_mode = "XYZ"
        for frame, angle in ((0, 0), (12, .8), (24, 0)):
            bone.rotation_euler = (0, angle, angle / 3)
            bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        context.stash_action(rig)
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = 0, 24
    """, require_rig=True)
    exported = document(character_out / "asset.glb")
    assert {clip["name"] for clip in exported["animations"]} == {"bend", "sway", "custom_wave"}
    assert len(exported["skins"]) == 1 and len(exported["skins"][0]["joints"]) == 2
    assert all("JOINTS_0" in primitive["attributes"] and "WEIGHTS_0" in primitive["attributes"]
               for mesh in exported["meshes"] for primitive in mesh["primitives"])

    def inspect_scene(source, destination, names, kind):
        run_logged(command + ["--python", self_script, "--", "snapshot", str(source),
                              str(destination), json.dumps(names), kind],
                   destination.with_suffix(".log"), cwd=repository)
        return read_json(destination)

    baseline = inspect_scene(character_source, sandbox / "character-before.json", ["bend", "sway"], "original")
    door_baseline = inspect_scene(door_source, sandbox / "door-before.json", ["closed"], "door")
    for out, names, kind, before in (
        (door_out, ["closed", "open"], "door", door_baseline),
        (baked_out, ["closed", "open", "baked_open"], "door", door_baseline),
        (character_out, ["bend", "sway", "custom_wave"], "edited", baseline),
    ):
        inspected = {}
        for extension, filename in (("blend", "source.blend"), ("glb", "asset.glb")):
            inspected[extension] = inspect_scene(out / filename, out / f"poses-{extension}.json", names, kind)
            near(before["rest_bounds"], inspected[extension]["rest_bounds"])
        for name in names:
            near(inspected["blend"]["clips"][name]["bounds"], inspected["glb"]["clips"][name]["bounds"])
        if kind == "edited":
            before_bounds = baseline["clips"]["bend"]["bounds"][1]
            after_bounds = inspected["glb"]["clips"]["bend"]["bounds"][1]
            assert max(abs(a - b) for left, right in zip(before_bounds, after_bounds, strict=True)
                       for a, b in zip(left, right, strict=True)) > .01

    author("script-error", door_source, "raise RuntimeError('intentional smoke script failure')",
           expected_failure=True)
    author("changed-original-curve", door_source, """
        import bpy
        from blender_authoring_tools import action_curves
        _, curve = next(action_curves(bpy.data.actions["closed"]))
        curve.keyframe_points[0].co.y += .2
    """, expected_failure=True, failure_text="removed or changed existing actions")
    author("changed-noise-strength", noise_source, """
        import bpy
        from blender_authoring_tools import action_curves
        curve = next(curve for _, curve in action_curves(bpy.data.actions["closed"])
                     if curve.modifiers)
        curve.modifiers[0].strength = 9
    """, expected_failure=True, failure_text="removed or changed existing actions")
    author("muted-original-curve", noise_source, """
        import bpy
        from blender_authoring_tools import action_curves
        curve = next(curve for _, curve in action_curves(bpy.data.actions["closed"])
                     if curve.modifiers)
        curve.mute = True
    """, expected_failure=True, failure_text="removed or changed existing actions")
    author("changed-playback-fps", door_source, """
        import bpy
        bpy.context.scene.render.fps = 30
    """, expected_failure=True, failure_text="timebase")
    replace_script = textwrap.dedent("""
        import bpy
        context.reset_pose()
        for action in list(bpy.data.actions):
            bpy.data.actions.remove(action, do_unlink=True)
    """) + textwrap.dedent(open_script)
    author("lost-original-clip", door_source, replace_script, expected_failure=True)
    replacement = author("explicit-replacement", door_source, replace_script, preserve=False)
    assert {clip["name"] for clip in document(replacement / "asset.glb")["animations"]} == {"open"}

    # The separate character processing path supports a deliberate byte-identical
    # GLB copy after inspection; it must reject requests that would alter that GLB.
    character_worker = repository / "src" / "asset_auto" / "blender_character_worker.py"
    copied = sandbox / "character-copy"
    copied.mkdir()
    copy_request = {"source": str(character_out / "asset.glb"), "output": str(copied),
                    "triangle_budget": 100, "target_height": None, "require_rig": True,
                    "require_animation": True, "preserve_input_glb": True, "rename_animation": False}
    write_json(copied / "request.json", copy_request)
    run_logged(command + ["--python", str(character_worker), "--", str(copied / "request.json")],
               copied / "blender.log", cwd=repository)
    assert (copied / "asset.glb").read_bytes() == (character_out / "asset.glb").read_bytes()
    assert read_json(copied / "inspection.json")["passed"]
    for label, changes in (
        ("blend", {"source": str(character_out / "source.blend")}),
        ("normalization", {"target_height": 3}),
        ("yaw", {"input_yaw_degrees": 90}),
        ("rename", {"source": str(replacement / "asset.glb"), "animation_name": "renamed",
                    "rename_animation": True, "require_rig": False}),
    ):
        rejected = sandbox / f"copy-rejected-{label}"
        rejected.mkdir()
        write_json(rejected / "request.json", {**copy_request, **changes, "output": str(rejected)})
        try:
            run_logged(command + ["--python", str(character_worker), "--", str(rejected / "request.json")],
                       rejected / "blender.log", cwd=repository)
        except RuntimeError as error:
            assert "preserve_input_glb" in str(error)
            assert not (rejected / "asset.glb").exists() and not (rejected / "source.blend").exists()
        else:
            raise AssertionError(f"Incompatible exact-copy {label} request was accepted")
    assert all(hashlib.sha256(source.read_bytes()).hexdigest() == digest for source, digest in sources.items())
    result = {"passed": True, "sandbox": str(sandbox),
              "outputs": [str(door_out), str(baked_out), str(pivot_out), str(character_out),
                          str(replacement), str(copied)],
              "visual_review": "Not asserted by smoke; inspect emitted preview images separately.",
              "checks": ["custom rigid hinge motion without adding a skeleton",
                         "offset and nonunit-scale rest geometry and parent hierarchy preserved",
                         "authored rest bone, weights and material edits survive export",
                         "custom animation and existing clips in the same GLB",
                         "constraint-driven object motion baked to a standalone clip on GLB input",
                         "evaluated skeletal pose constraints bake to an independently deforming GLB clip",
                         "main-guarded scripts execute and new animated pivots retain their pre-key rest defaults",
                         "morph defaults and bone hierarchy preserved",
                         "actual Blender/GLB deformation agrees for all clips",
                         "old clip deforms differently after intentional rig/weight edits",
                         "script exception and removed/modified original clip failures leave no final files",
                         "explicit preservation opt-out permits deliberate replacement",
                         "execution checkpoint resumes without running the script twice",
                         "source, script and binding checkpoint tampering rejected",
                         "original Noise strength, curve mute and clip playback timing changes rejected",
                         "explicit GLB copy is byte-identical and incompatible transforms/renames rejected",
                         "five rest previews and three images for every exported clip",
                         "source fixture hashes unchanged"]}
    write_json(sandbox / "result.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if "--" not in sys.argv:
        main()
    else:
        arguments = sys.argv[sys.argv.index("--") + 1:]
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        if arguments[0] == "fixture":
            make_fixtures(Path(arguments[1]))
        elif arguments[0] == "snapshot":
            snapshot(Path(arguments[1]), Path(arguments[2]), json.loads(arguments[3]), arguments[4])
        elif arguments[0] == "skeletal-bake":
            skeletal_bake_probe(Path(arguments[1]), Path(arguments[2]))
