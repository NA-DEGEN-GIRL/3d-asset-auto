"""Executed by portable Blender, never imported by the controller Python."""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def meshes():
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def bounds(objects):
    points = [o.matrix_world @ Vector(v) for o in objects for v in o.bound_box]
    return (
        Vector(tuple(min(v[i] for v in points) for i in range(3))),
        Vector(tuple(max(v[i] for v in points) for i in range(3))),
    )


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def material(name, spec):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = spec["color"]
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    mat.diffuse_color = spec["color"]
    return mat


def create(recipe):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = {name: material(name, spec) for name, spec in recipe["materials"].items()}
    for part in recipe["parts"]:
        primitive = part["primitive"]
        if primitive == "box":
            bpy.ops.mesh.primitive_cube_add(size=1)
        elif primitive == "cylinder":
            bpy.ops.mesh.primitive_cylinder_add(vertices=part["segments"], radius=0.5, depth=1)
        elif primitive == "cone":
            bpy.ops.mesh.primitive_cone_add(vertices=part["segments"], radius1=0.5, radius2=0, depth=1)
        else:
            bpy.ops.mesh.primitive_uv_sphere_add(segments=part["segments"], ring_count=12, radius=0.5)
        obj = bpy.context.object
        obj.name = part["name"]
        obj["asset_part"] = part["name"]
        obj.dimensions = part["dimensions"]
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.location = part["location"]
        obj.rotation_euler = [math.radians(v) for v in part["rotation_degrees"]]
        obj.data.materials.append(materials[part["material"]])
        if part["bevel"]:
            modifier = obj.modifiers.new("edge_bevel", "BEVEL")
            modifier.width = part["bevel"]
            modifier.segments = 2
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        if primitive in ("sphere", "cylinder"):
            for poly in obj.data.polygons:
                poly.use_smooth = True
        # Explicit UVs are useful for later baking and engine import.
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(island_margin=0.03)
        bpy.ops.object.mode_set(mode="OBJECT")


def load(source):
    if Path(source).suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=source, load_ui=False)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=source)
    if not meshes():
        raise ValueError("Input contains no mesh objects")


def normalize(height):
    objects = meshes()
    if any(o.type == "ARMATURE" for o in bpy.context.scene.objects):
        raise ValueError("Static asset pipeline cannot normalize a rigged asset")
    # Bake existing world transforms before changing global scale/origin.
    for obj in objects:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    low, high = bounds(objects)
    extent = high - low
    if min(extent) < 1e-8:
        raise ValueError("Degenerate bounding box")
    factor = height / extent.z if height else 1
    center = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    for obj in objects:
        obj.location = (obj.location - center) * factor
        obj.scale *= factor
        activate(obj)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()


def edit(changes):
    available = {o.name: o for o in meshes()}
    for change in changes:
        if change["part"] not in available and change["part"] != "*":
            raise ValueError(f"Unknown part {change['part']}; available: {list(available)}")
        objects = list(available.values()) if change["part"] == "*" else [available[change["part"]]]
        for obj in objects:
            if change.get("scale"):
                for i, factor in enumerate(change["scale"]):
                    obj.scale[i] *= factor
            if change.get("offset"):
                obj.location += Vector(change["offset"])
            if any(change.get(key) is not None for key in ("color", "metallic", "roughness")):
                for slot in obj.material_slots:
                    if not slot.material:
                        continue
                    slot.material = slot.material.copy()
                    shader = slot.material.node_tree.nodes.get("Principled BSDF")
                    if not shader:
                        raise ValueError(f"Unsupported material on {obj.name}")
                    for key, socket in (
                        ("color", "Base Color"),
                        ("metallic", "Metallic"),
                        ("roughness", "Roughness"),
                    ):
                        if change.get(key) is not None:
                            for link in list(shader.inputs[socket].links):
                                slot.material.node_tree.links.remove(link)
                            shader.inputs[socket].default_value = change[key]
            activate(obj)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()


def triangle_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def optimize(budget):
    objects = meshes()
    total = sum(triangle_count(o) for o in objects)
    if total <= budget:
        return
    # Apply a margin because topology constraints can prevent exact target counts.
    ratio = budget / total * 0.95
    for obj in objects:
        activate(obj)
        modifier = obj.modifiers.new("budget_decimate", "DECIMATE")
        modifier.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=modifier.name)


def inspect(budget):
    objects = meshes()
    low, high = bounds(objects)
    stats, errors, warnings = [], [], []
    for obj in objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        non_manifold = sum(not edge.is_manifold for edge in bm.edges)
        degenerate = sum(face.calc_area() < 1e-12 for face in bm.faces)
        bm.free()
        points = [obj.matrix_world @ v.co for v in obj.data.vertices]
        if any(not math.isfinite(component) for v in points for component in v):
            errors.append(f"Non-finite coordinates: {obj.name}")
        if degenerate:
            warnings.append(f"{obj.name}: {degenerate} zero-area faces")
        if non_manifold:
            warnings.append(f"{obj.name}: {non_manifold} non-manifold edges; inspect intent")
        if not obj.data.uv_layers:
            warnings.append(f"{obj.name}: no UV coordinates")
        stats.append(
            {
                "name": obj.name,
                "triangles": triangle_count(obj),
                "vertices": len(obj.data.vertices),
                "dimensions": list(obj.dimensions),
                "location": list(obj.location),
                "materials": [s.material.name for s in obj.material_slots if s.material],
                "non_manifold_edges": non_manifold,
                "degenerate_faces": degenerate,
                "has_uv": bool(obj.data.uv_layers),
            }
        )
    for img in bpy.data.images:
        if (
            img.source == "FILE"
            and not img.packed_file
            and not Path(bpy.path.abspath(img.filepath)).is_file()
        ):
            errors.append(f"Missing image: {img.name}")
    total = sum(s["triangles"] for s in stats)
    if total > budget:
        errors.append(f"Triangle count {total} exceeds budget {budget}")
    if not total:
        errors.append("No triangles")
    return {
        "triangles": total,
        "triangle_budget": budget,
        "dimensions": list(high - low),
        "bounds": {"min": list(low), "max": list(high)},
        "parts": stats,
        "errors": errors,
        "warnings": warnings,
        "passed": not errors,
        "blender_version": bpy.app.version_string,
    }


def render_views(out):
    scene = bpy.context.scene
    objects = meshes()
    low, high = bounds(objects)
    center = (low + high) / 2
    extent = max(high - low)
    for obj in list(scene.objects):
        if obj.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(obj, do_unlink=True)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.world = bpy.data.worlds.new("asset_preview_world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.25, 0.28, 0.35, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    for name, direction, energy, size in [
        ("key", (2, -3, 4), 450, 3),
        ("fill", (-3, -1, 2), 250, 4),
        ("rim", (1, 3, 3), 600, 2),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy * extent * extent
        data.shape = "DISK"
        data.size = size * extent
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = center + Vector(direction) * extent
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    data = bpy.data.cameras.new("asset_camera")
    data.type = "ORTHO"
    data.ortho_scale = extent * 1.55
    camera = bpy.data.objects.new("asset_camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    views = {
        "front": (0, -4, 0.4),
        "back": (0, 4, 0.4),
        "left": (-4, 0, 0.4),
        "right": (4, 0, 0.4),
        "perspective": (3, -4, 2.5),
    }
    for name, direction in views.items():
        camera.location = center + Vector(direction) * extent
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(out / f"{name}.png")
        bpy.ops.render.render(write_still=True)


def main():
    request = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    out = Path(request["output"])
    out.mkdir(parents=True, exist_ok=True)
    if request["operation"] == "create":
        create(request["recipe"])
    else:
        load(request["source"])
    # This worker is deliberately limited to static meshes.
    if any(o.type == "ARMATURE" for o in bpy.context.scene.objects):
        raise ValueError("Rigged meshes require a rig-aware workflow; static processing refused")
    if request.get("changes"):
        edit(request["changes"])
    else:
        normalize(request.get("target_height"))
    optimize(request["triangle_budget"])
    bpy.context.view_layer.update()
    report = inspect(request["triangle_budget"])
    (out / "inspection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.file.pack_all()
    # Save editable source before adding preview cameras/lights.
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "source.blend"))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes():
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(out / "asset.glb"),
        export_format="GLB",
        use_selection=True,
        export_image_format="AUTO",
        export_yup=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
    )
    render_views(out)


if __name__ == "__main__":
    main()
