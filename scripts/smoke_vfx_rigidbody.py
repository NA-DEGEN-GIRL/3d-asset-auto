"""Probe cut fragments, rigid-body playback and the existing GLB exporter.

This procedural maintenance fixture is not a generated ice asset, a fracture
solver, an engine adapter or visual approval of a finished spell.
"""

import json
import sys
import uuid
from pathlib import Path


def probe(output):
    import addon_utils
    import bmesh
    import bpy
    from mathutils import Vector

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    from blender_authoring_tools import action_curves, stash_action
    from blender_character_worker import export_character, glb_document, load_character, select_preview_clip

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 96
    source = bmesh.new()
    bmesh.ops.create_icosphere(source, subdivisions=2, radius=0.8)
    source_volume = abs(source.calc_volume(signed=True))
    fragments, centers, volumes = [], {}, []
    for index, (side_x, side_y) in enumerate(((True, True), (True, False), (False, True), (False, False))):
        fragment = source.copy()
        for normal, side in (((1, 0.2, 0), side_x), ((0.1, 1, 0.2), side_y)):
            bmesh.ops.bisect_plane(
                fragment, geom=list(fragment.verts) + list(fragment.edges) + list(fragment.faces),
                dist=1e-6, plane_co=(0, 0, 0), plane_no=normal,
                clear_inner=side, clear_outer=not side,
            )
            bmesh.ops.holes_fill(fragment, edges=[edge for edge in fragment.edges if edge.is_boundary])
            bmesh.ops.recalc_face_normals(fragment, faces=list(fragment.faces))
        assert all(edge.is_manifold for edge in fragment.edges), "Open fracture fixture"
        volume = abs(fragment.calc_volume(signed=True))
        assert volume > 0
        volumes.append(volume)
        center = sum((vertex.co for vertex in fragment.verts), Vector()) / len(fragment.verts)
        for vertex in fragment.verts:
            vertex.co -= center
        mesh = bpy.data.meshes.new(f"fragment_mesh_{index}")
        fragment.to_mesh(mesh)
        fragment.free()
        obj = bpy.data.objects.new(f"fragment_{index}", mesh)
        scene.collection.objects.link(obj)
        fragments.append(obj)
        centers[obj.name] = center.copy()
        obj.location = center + Vector((0, 0, 3.2))
        obj.rotation_mode = "QUATERNION"
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.rigidbody.object_add()
        obj.rigid_body.mass = volume
        obj.rigid_body.collision_shape = "CONVEX_HULL"
        obj.rigid_body.use_margin = True
        obj.rigid_body.collision_margin = 0.001
        obj.rigid_body.friction = 0.65
        obj.rigid_body.restitution = 0.15
        obj.rigid_body.linear_damping = 0.25
        obj.rigid_body.angular_damping = 0.3
        direction = Vector((center.x, center.y, 0)).normalized()
        # Controlled approach and short authored launch, then actual rigid-body motion.
        for frame, height, outward in ((1, 3.2, 0), (12, 2.3, 0), (18, 0.8, 0),
                                       (19, 0.85, 0.02), (20, 0.94, 0.09)):
            obj.location = center + Vector((0, 0, height)) + direction * outward
            obj.keyframe_insert(data_path="location", frame=frame)
        for frame, kinematic in ((1, True), (20, True), (21, False)):
            obj.rigid_body.kinematic = kinematic
            obj.keyframe_insert(data_path="rigid_body.kinematic", frame=frame)
        for _, curve in action_curves(obj.animation_data.action):
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT" if curve.data_path == "rigid_body.kinematic" else "LINEAR"
        obj.select_set(False)
    source.free()
    assert abs(sum(volumes) - source_volume) < 1e-4, "Cuts lost source volume"

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.25))
    ground = bpy.context.object
    ground.name = "collision_ground"
    ground.scale = (20, 20, 0.5)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.rigidbody.object_add()
    ground.rigid_body.type = "PASSIVE"
    ground.rigid_body.collision_shape = "BOX"
    scene.rigidbody_world.substeps_per_frame = 10
    scene.rigidbody_world.solver_iterations = 20
    scene.rigidbody_world.point_cache.frame_start = 1
    scene.rigidbody_world.point_cache.frame_end = 96
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "simulation.blend"))

    samples = {}
    minimum_dynamic_z = float("inf")
    for frame in range(1, 97):
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        samples[frame] = {obj.name: obj.evaluated_get(depsgraph).matrix_world.copy() for obj in fragments}
        if frame >= 21:
            minimum_dynamic_z = min(minimum_dynamic_z, min(
                (samples[frame][obj.name] @ vertex.co).z for obj in fragments for vertex in obj.data.vertices
            ))
    assert minimum_dynamic_z > -0.05, minimum_dynamic_z
    for obj in fragments:
        assert samples[1][obj.name].translation.z > samples[18][obj.name].translation.z + 1.5
    assert any((samples[40][obj.name].translation - samples[21][obj.name].translation).length > 0.1
               for obj in fragments), "No simulated movement after release"

    # Snapshot evaluated matrices before removing simulation. One shared slotted
    # action keeps every fragment on the same exported clock with ACTIONS mode.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in fragments:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = fragments[0]
    bpy.ops.rigidbody.objects_remove()
    bpy.data.objects.remove(ground, do_unlink=True)
    action = bpy.data.actions.new("fall_break")
    for obj in fragments:
        obj.animation_data_clear()
        animation = obj.animation_data_create()
        animation.action = action
        animation.action_slot = action.slots.new("OBJECT", obj.name)
        for frame, matrices in samples.items():
            location, rotation, _ = matrices[obj.name].decompose()
            obj.location, obj.rotation_quaternion = location, rotation
            obj.keyframe_insert(data_path="location", frame=frame)
            obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    for _, curve in action_curves(action):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    scene.frame_set(1)
    for obj in fragments:
        stash_action(obj)
    for old in list(bpy.data.actions):
        if old != action and old.users == 0:
            bpy.data.actions.remove(old)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "baked.blend"))
    export_character(output / "asset.glb")
    document = glb_document(output / "asset.glb")
    assert [clip["name"] for clip in document["animations"]] == ["fall_break"]
    clip = document["animations"][0]
    animated = {document["nodes"][channel["target"]["node"]]["name"] for channel in clip["channels"]}
    assert animated == set(centers), animated

    load_character(output / "asset.glb")
    select_preview_clip("fall_break")
    maximum_error = 0
    # Exporter/importer retain this positive start frame; compare actual times.
    for frame in (1, 12, 18, 21, 32, 48, 72, 96):
        scene = bpy.context.scene
        scene.render.fps = 24
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for name in centers:
            actual, expected = bpy.data.objects[name].matrix_world, samples[frame][name]
            maximum_error = max(maximum_error, max(abs(actual[row][col] - expected[row][col])
                                                   for row in range(4) for col in range(4)))
    assert maximum_error < 1e-4, maximum_error
    report = {
        "passed": True, "blender": bpy.app.version_string, "fragments": len(centers),
        "source_volume": source_volume, "fragment_volume_sum": sum(volumes),
        "minimum_dynamic_vertex_z": minimum_dynamic_z,
        "roundtrip_max_matrix_error": maximum_error,
        "clips": [clip["name"]], "animated_nodes": sorted(animated),
        "cell_fracture_module_available": any("fracture" in module.__name__ for module in addon_utils.modules()),
        "method": "Closed mesh cuts, authored release, rigid-body evaluation, shared-action matrix bake",
        "not_proven": ["learned ice generation", "natural fracture timing", "stress-based fracture",
                       "ice shading", "visual quality", "engine collisions or gameplay", "full CLI revision workflow"],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main():
    from asset_auto.pipeline import run_logged
    from asset_auto.settings import executable

    repository = Path(__file__).resolve().parents[1]
    output = repository / ".work" / f"smoke-vfx-rigidbody-{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True)
    command = [executable(repository, "blender"), "--background", "--factory-startup", "--disable-autoexec",
               "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--", str(output)]
    run_logged(command, output / "blender.log", cwd=repository)
    print((output / "report.json").read_text(encoding="utf-8"))
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    if "--" in sys.argv:
        probe(Path(sys.argv[sys.argv.index("--") + 1]))
    else:
        main()
